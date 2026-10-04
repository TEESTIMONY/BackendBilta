import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.core import signing
from django.db import transaction
from django.http import FileResponse
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import decorators, permissions, response, serializers, status, throttling, viewsets
from rest_framework.authtoken.models import Token

from .models import (
    Announcement,
    AuditLog,
    Customer,
    DailyCashCount,
    Expense,
    Job,
    JobAttachment,
    JobStatusHistory,
    MessageTemplate,
    Order,
    OrderMessageLog,
    PaymentRecord,
    PhotocopySession,
    Product,
    StaffInvitation,
    SystemSetting,
)
from .serializers import (
    person_name,
    ATTACHMENT_LINK_MAX_AGE_SECONDS,
    ATTACHMENT_LINK_SALT,
    AnnouncementSerializer,
    AuditLogSerializer,
    AuthLoginSerializer,
    CustomerSerializer,
    DailyCashCountSerializer,
    ExpenseSerializer,
    CurrentUserSerializer,
    JobSerializer,
    MessageTemplateSerializer,
    OrderMessageLogSerializer,
    OrderSerializer,
    PaymentRecordSerializer,
    PhotocopySessionSerializer,
    ProductSerializer,
    PublicCheckoutRequestSerializer,
    PublicDesignRequestSerializer,
    StaffAccountSerializer,
    StaffInvitationAcceptSerializer,
    StaffInvitationCreateSerializer,
    StaffInvitationDetailSerializer,
    StaffInvitationSerializer,
    StaffPasswordResetSerializer,
    SystemSettingSerializer,
)

User = get_user_model()

MAX_PUBLIC_UPLOAD_FILES = 6
MAX_PUBLIC_UPLOAD_FILE_SIZE_BYTES = 8 * 1024 * 1024
MAX_PUBLIC_UPLOAD_TOTAL_SIZE_BYTES = 20 * 1024 * 1024


def is_owner_user(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def is_staff_user(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_owner_user(request.user)


class IsStaffUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return is_staff_user(request.user)


class IsOwnerUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return is_owner_user(request.user)


class IsStaffWriteOwnerDelete(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method == 'DELETE':
            return is_owner_user(request.user)
        return is_staff_user(request.user)


class IsStaffCreateOwnerManage(permissions.BasePermission):
    """Staff may only add records (POST); everything else (list, view, edit, delete) is owner-only."""

    def has_permission(self, request, view):
        if request.method == 'POST':
            return is_staff_user(request.user)
        return is_owner_user(request.user)


def phone_key(value):
    """0803 123 4567, +2348031234567 and 2348031234567 all become 8031234567."""
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if digits.startswith('234'):
        return digits[3:]
    if digits.startswith('0'):
        return digits[1:]
    return digits


class IsStaffReadOwnerWrite(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return is_staff_user(request.user)
        return is_owner_user(request.user)


class LoginRateThrottle(throttling.SimpleRateThrottle):
    """Limits sign-in attempts per username, or per client when no username is sent."""

    scope = 'login'

    def get_cache_key(self, request, view):
        data = request.data if hasattr(request.data, 'get') else {}
        username = str(data.get('username', '') or '').strip().lower()
        return self.cache_format % {'scope': self.scope, 'ident': username or self.get_ident(request)}


def write_audit(action, model_name, object_id='', user=None, reason='', metadata=None):
    AuditLog.objects.create(
        action=action,
        model_name=model_name,
        object_id=str(object_id or ''),
        performed_by=user if getattr(user, 'is_authenticated', False) else None,
        reason=reason or '',
        metadata=metadata or {},
    )


def only_own(queryset, user, field):
    """Owners see every record; staff see only records where `field` is themselves."""
    if is_owner_user(user):
        return queryset
    return queryset.filter(**{field: user})


class OneDayFilterMixin:
    """`?date=YYYY-MM-DD` limits a history list to records created that day (Africa/Lagos)."""

    def get_queryset(self):
        queryset = super().get_queryset()
        date_value = self.request.query_params.get('date')
        if date_value:
            queryset = queryset.filter(created_at__date=parse_date_param(date_value, 'date'))
        return queryset


def money(value):
    return str(Decimal(str(value if value is not None else '0')).quantize(Decimal('0.01')))


def parse_date_param(value, name):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError({name: 'Invalid date format. Use YYYY-MM-DD.'}) from exc


def parse_public_payload(request):
    if isinstance(request.data, dict) and 'payload' in request.data:
        try:
            return json.loads(request.data.get('payload') or '{}')
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError({'detail': 'Invalid submission payload.'}) from exc
    return request.data


def validate_uploaded_files(files):
    if len(files) > MAX_PUBLIC_UPLOAD_FILES:
        raise serializers.ValidationError(
            {'detail': f'You can upload up to {MAX_PUBLIC_UPLOAD_FILES} files at a time.'}
        )

    total_size = sum(getattr(upload, 'size', 0) or 0 for upload in files)
    if total_size > MAX_PUBLIC_UPLOAD_TOTAL_SIZE_BYTES:
        raise serializers.ValidationError(
            {'detail': 'Total uploaded files are too large. Please reduce them and try again.'}
        )

    for upload in files:
        if (getattr(upload, 'size', 0) or 0) > MAX_PUBLIC_UPLOAD_FILE_SIZE_BYTES:
            raise serializers.ValidationError(
                {'detail': f'{upload.name} is too large. Please keep each file under 8 MB.'}
            )


def create_job_attachments(job, files):
    validate_uploaded_files(files)
    for upload in files:
        JobAttachment.objects.create(
            job=job,
            file=upload,
            original_name=upload.name,
            content_type=getattr(upload, 'content_type', '') or '',
            size_bytes=getattr(upload, 'size', 0) or 0,
        )


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    search_fields = ['title', 'category', 'description', 'details']
    ordering_fields = ['title', 'created_at', 'updated_at']
    permission_classes = [IsOwnerOrReadOnly]


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().prefetch_related('jobs')
    serializer_class = CustomerSerializer
    search_fields = ['full_name', 'phone', 'email', 'city']
    ordering_fields = ['full_name', 'created_at', 'updated_at']
    # Staff can add customers but not browse, view or edit the customer list.
    permission_classes = [IsStaffCreateOwnerManage]

    def create(self, request, *args, **kwargs):
        # A phone number already on file means a returning customer: reuse them instead of
        # adding a duplicate. Staff only learn the id and name, not the rest of the record.
        key = phone_key(request.data.get('phone'))
        if len(key) >= 7:
            for customer in Customer.objects.exclude(phone=''):
                if phone_key(customer.phone) == key:
                    return response.Response(
                        {'id': customer.id, 'full_name': customer.full_name, 'existing': True},
                        status=status.HTTP_200_OK,
                    )
        return super().create(request, *args, **kwargs)

    @decorators.action(detail=False, methods=['post'], url_path='walk-in', permission_classes=[IsStaffUser])
    def walk_in(self, request):
        """The one shared customer record for anonymous walk-in jobs."""
        customer = (
            Customer.objects.filter(customer_type=Customer.CustomerType.WALK_IN, phone='')
            .filter(full_name__in=['Walk-in', 'Walk-in Customer'])
            .order_by('id')
            .first()
        )
        if not customer:
            customer = Customer.objects.create(
                full_name='Walk-in Customer',
                customer_type=Customer.CustomerType.WALK_IN,
                notes='Shared record for walk-in jobs.',
            )
        return response.Response({'id': customer.id, 'full_name': customer.full_name})

    def perform_create(self, serializer):
        customer = serializer.save()
        write_audit('create', 'Customer', customer.id, self.request.user, metadata={'name': customer.full_name})

    def perform_update(self, serializer):
        customer = serializer.save()
        write_audit('update', 'Customer', customer.id, self.request.user, metadata={'name': customer.full_name})


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().select_related('customer').prefetch_related('items')
    serializer_class = OrderSerializer
    search_fields = ['code', 'customer__full_name', 'customer__phone', 'internal_notes']
    ordering_fields = ['created_at', 'updated_at', 'payment_date', 'due_date', 'total_amount']
    permission_classes = [IsStaffWriteOwnerDelete]

    @decorators.action(detail=False, methods=['get'])
    def monthly_report(self, request):
        month_param = request.query_params.get('month')
        queryset = self.get_queryset()

        if month_param:
            try:
                selected = datetime.strptime(month_param, '%Y-%m').date()
                queryset = queryset.filter(created_at__year=selected.year, created_at__month=selected.month)
            except ValueError:
                return response.Response({'detail': 'Invalid month format. Use YYYY-MM.'}, status=400)

        total_jobs = queryset.count()
        total_revenue = queryset.aggregate(total=Sum('total_amount')).get('total') or 0
        paid_revenue = queryset.filter(payment_status=Order.PaymentStatus.PAID).aggregate(total=Sum('amount_paid')).get('total') or 0
        delivered_count = queryset.filter(status=Order.OrderStatus.DELIVERED).count()
        pending_count = queryset.exclude(status=Order.OrderStatus.DELIVERED).count()

        by_status = list(
            queryset.values('status').annotate(count=Count('id')).order_by('status')
        )

        by_source = list(
            queryset.values('source').annotate(count=Count('id')).order_by('source')
        )

        monthly_breakdown = list(
            queryset.annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(
                jobs=Count('id'),
                revenue=Sum('total_amount'),
            )
            .order_by('month')
        )

        return response.Response(
            {
                'generated_at': timezone.now(),
                'filters': {'month': month_param or 'all'},
                'summary': {
                    'total_jobs': total_jobs,
                    'total_revenue': total_revenue,
                    'paid_revenue': paid_revenue,
                    'delivered_count': delivered_count,
                    'pending_count': pending_count,
                },
                'by_status': by_status,
                'by_source': by_source,
                'monthly_breakdown': monthly_breakdown,
            }
        )


class MessageTemplateViewSet(viewsets.ModelViewSet):
    queryset = MessageTemplate.objects.all()
    serializer_class = MessageTemplateSerializer
    search_fields = ['name', 'stage', 'body']
    ordering_fields = ['stage', 'name', 'updated_at']
    permission_classes = [IsStaffReadOwnerWrite]


class OrderMessageLogViewSet(viewsets.ModelViewSet):
    queryset = OrderMessageLog.objects.all().select_related('order', 'customer', 'template')
    serializer_class = OrderMessageLogSerializer
    search_fields = ['order__code', 'customer__full_name', 'stage', 'message_body']
    ordering_fields = ['sent_at', 'created_at']
    permission_classes = [IsStaffWriteOwnerDelete]


class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    search_fields = ['title', 'message']
    ordering_fields = ['created_at', 'starts_at', 'ends_at']

    def get_permissions(self):
        # Only the currently live announcement is public; drafts and history stay internal.
        if self.action == 'active':
            return [permissions.AllowAny()]
        return [IsStaffReadOwnerWrite()]

    @decorators.action(detail=False, methods=['get'])
    def active(self, request):
        now = timezone.now()
        current = self.get_queryset().filter(
            is_active=True,
        ).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        ).order_by('-created_at').first()

        if not current:
            return response.Response({'detail': 'No active announcement.'}, status=404)

        return response.Response(self.get_serializer(current).data)


# Only the owner can close a job (Completed / Cancelled) or reopen a closed one.
OWNER_ONLY_JOB_STATUSES = {Job.JobStatus.COMPLETED, Job.JobStatus.CANCELLED}


def check_staff_status_change(user, new_status, old_status=None):
    if is_owner_user(user) or new_status is None or new_status == old_status:
        return
    if new_status in OWNER_ONLY_JOB_STATUSES:
        raise serializers.ValidationError(
            {'status': f'Only the owner can mark a job as {Job.JobStatus(new_status).label}.'}
        )
    if old_status in OWNER_ONLY_JOB_STATUSES:
        raise serializers.ValidationError(
            {'status': f'This job is {Job.JobStatus(old_status).label}. Only the owner can reopen it.'}
        )


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all().select_related('customer', 'created_by', 'updated_by').prefetch_related('status_history', 'attachments', 'items')
    serializer_class = JobSerializer
    search_fields = ['customer__full_name', 'job_type', 'description', 'special_instructions']
    ordering_fields = ['created_at', 'deadline', 'updated_at', 'total']
    permission_classes = [IsStaffWriteOwnerDelete]

    def _log_amount_paid_change(self, job, delta, note):
        # Money entered directly on a job ("Amount paid now", owner corrections) gets a
        # matching PaymentRecord so the payment log and daily revenue agree with the job.
        if not delta:
            return
        PaymentRecord.objects.create(
            job=job,
            amount=delta,
            source=PaymentRecord.PaymentSource.JOB,
            recorded_by=self.request.user if self.request.user.is_authenticated else None,
            note=note,
        )

    def perform_create(self, serializer):
        check_staff_status_change(self.request.user, serializer.validated_data.get('status'))
        with transaction.atomic():
            job = serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)
            self._log_amount_paid_change(job, job.amount_paid, 'Paid when the job was created.')
        discount = getattr(serializer, 'applied_discount', None)
        if discount:
            write_audit('discount', 'Job', job.id, self.request.user, reason=job.discount_reason, metadata=discount)
        job.customer.last_job_date = timezone.now()
        job.customer.save(update_fields=['last_job_date', 'updated_at'])
        JobStatusHistory.objects.create(job=job, from_status='', to_status=job.status, changed_by=self.request.user if self.request.user.is_authenticated else None)
        write_audit(
            'create',
            'Job',
            job.id,
            self.request.user,
            metadata={'customer_name': job.customer.full_name, 'total': money(job.amount_due), 'paid': money(job.amount_paid)},
        )

    def perform_update(self, serializer):
        previous = self.get_object()
        if not is_owner_user(self.request.user):
            protected_fields = {'unit_price', 'quantity', 'amount_paid', 'items'}
            attempted = protected_fields.intersection(set(self.request.data.keys()))
            if attempted:
                raise serializers.ValidationError(
                    {
                        'detail': 'Only the owner/admin can change job pricing, quantity, or saved payment amounts after creation.'
                    }
                )
        correction_fields = {'customer', 'job_type', 'description', 'quantity', 'unit_price', 'amount_paid', 'items', 'deadline', 'fulfilment', 'special_instructions', 'project_scope_note'}
        def snapshot(job):
            data = {field: str(getattr(job, field + '_id' if field == 'customer' else field)) for field in correction_fields - {'items'}}
            for field in ('unit_price', 'amount_paid'):
                data[field] = money(getattr(job, field))
            data['items'] = list(job.items.order_by('id').values('description', 'quantity', 'rate'))
            for item in data['items']:
                item['rate'] = money(item['rate'])
            return data
        before = snapshot(previous)
        old_status = previous.status
        check_staff_status_change(self.request.user, serializer.validated_data.get('status'), old_status)
        old_amount_paid = previous.amount_paid
        with transaction.atomic():
            job = serializer.save(updated_by=self.request.user if self.request.user.is_authenticated else None)
            self._log_amount_paid_change(
                job,
                job.amount_paid - old_amount_paid,
                f'Owner adjusted amount paid from {old_amount_paid} to {job.amount_paid}.',
            )
            after = snapshot(job)
            corrected = {field: {'before': before[field], 'after': after[field]} for field in correction_fields if before[field] != after[field]}
            if corrected and is_owner_user(self.request.user):
                write_audit('correction', 'Job', job.id, self.request.user, metadata={'changes': corrected})
        job.customer.last_job_date = timezone.now()
        job.customer.save(update_fields=['last_job_date', 'updated_at'])
        if old_status != job.status:
            JobStatusHistory.objects.create(job=job, from_status=old_status, to_status=job.status, changed_by=self.request.user if self.request.user.is_authenticated else None)
        changes = {'customer_name': job.customer.full_name}
        if old_status != job.status:
            changes.update({'status_from': old_status, 'status_to': job.status})
        if old_amount_paid != job.amount_paid:
            changes.update({'paid_from': money(old_amount_paid), 'paid_to': money(job.amount_paid)})
        write_audit('update', 'Job', job.id, self.request.user, metadata=changes)

    def get_queryset(self):
        # Staff work only with jobs they added; website orders (no creator) are owner-only.
        queryset = only_own(super().get_queryset(), self.request.user, 'created_by')
        created_on = self.request.query_params.get('created_on')
        if created_on:
            queryset = queryset.filter(created_at__date=parse_date_param(created_on, 'created_on'))
        return queryset

    @decorators.action(detail=False, methods=['get'])
    def queue(self, request):
        # The desk only works on the current day's jobs (Africa/Lagos); earlier days
        # are reviewed from the Records page via ?created_on=.
        now = timezone.now()
        date_param = request.query_params.get('date')
        target = parse_date_param(date_param, 'date') if date_param else timezone.localdate()
        qs = self.get_queryset().filter(created_at__date=target).exclude(status=Job.JobStatus.CANCELLED)
        data = self.get_serializer(qs, many=True).data
        for row in data:
            deadline = row.get('deadline')
            if deadline:
                parsed_deadline = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                row['is_overdue'] = parsed_deadline < now
            else:
                row['is_overdue'] = False
        return response.Response(data)


class PaymentRecordViewSet(OneDayFilterMixin, viewsets.ModelViewSet):
    queryset = PaymentRecord.objects.all().select_related('job', 'job__customer', 'recorded_by')
    serializer_class = PaymentRecordSerializer
    search_fields = ['service_label', 'job__job_type', 'job__customer__full_name']
    ordering_fields = ['created_at', 'amount']
    permission_classes = [IsStaffWriteOwnerDelete]

    def get_queryset(self):
        return only_own(super().get_queryset(), self.request.user, 'recorded_by')

    @staticmethod
    def _adjust_job_paid(job_id, delta):
        if not job_id or not delta:
            return
        job = Job.objects.select_for_update().get(pk=job_id)
        job.amount_paid = max(Decimal('0.00'), (job.amount_paid or Decimal('0.00')) + delta)
        job.save()

    def perform_create(self, serializer):
        job = serializer.validated_data.get('job')
        if job and not is_owner_user(self.request.user) and job.created_by_id != self.request.user.id:
            raise serializers.ValidationError(
                {'job': "Only the owner can take payment on another staff member's job or a website order."}
            )
        agreed_total = serializer.validated_data.pop('agreed_total', None)
        discount_reason = str(serializer.validated_data.pop('discount_reason', '') or '').strip()
        discount = None
        with transaction.atomic():
            if agreed_total is not None:
                job = Job.objects.select_for_update().get(pk=serializer.validated_data['job'].pk)
                previous_discount = job.discount_amount
                job.discount_amount = job.total - agreed_total
                job.discount_reason = discount_reason
                job.save()
                discount = {
                    'job_id': job.id,
                    'job_total': str(job.total),
                    'agreed_total': str(agreed_total),
                    'discount_amount': str(job.discount_amount),
                    'previous_discount': str(previous_discount),
                }
            payment = serializer.save(recorded_by=self.request.user if self.request.user.is_authenticated else None)
            self._adjust_job_paid(payment.job_id, payment.amount)
        if discount:
            write_audit('discount', 'Job', discount['job_id'], self.request.user, reason=discount_reason, metadata=discount)
        write_audit('create', 'PaymentRecord', payment.id, self.request.user, metadata=payment_details(payment))

    def perform_update(self, serializer):
        reason = str(self.request.data.get('edit_reason', '') or '').strip()
        if not reason:
            raise serializers.ValidationError({'edit_reason': 'edit_reason is required when editing a payment'})
        with transaction.atomic():
            previous = PaymentRecord.objects.select_for_update().get(pk=serializer.instance.pk)
            old_job_id, old_amount = previous.job_id, previous.amount
            payment = serializer.save()
            if old_job_id == payment.job_id:
                self._adjust_job_paid(payment.job_id, payment.amount - old_amount)
            else:
                self._adjust_job_paid(old_job_id, -old_amount)
                self._adjust_job_paid(payment.job_id, payment.amount)
        write_audit(
            'update',
            'PaymentRecord',
            payment.id,
            self.request.user,
            reason=reason,
            metadata={**payment_details(payment), 'amount_from': money(old_amount)},
        )

    def perform_destroy(self, instance):
        payment_id = instance.id
        details = payment_details(instance)
        with transaction.atomic():
            self._adjust_job_paid(instance.job_id, -instance.amount)
            instance.delete()
        write_audit('delete', 'PaymentRecord', payment_id, self.request.user, metadata=details)


def payment_details(payment):
    return {
        'amount': money(payment.amount),
        'job_id': payment.job_id,
        'source': payment.source,
        'service_label': payment.service_label,
        'customer_name': payment.job.customer.full_name if payment.job_id else '',
    }


class PhotocopySessionViewSet(OneDayFilterMixin, viewsets.ModelViewSet):
    queryset = PhotocopySession.objects.all().select_related('staff')
    serializer_class = PhotocopySessionSerializer
    ordering_fields = ['created_at', 'updated_at', 'expected_revenue', 'actual_cash_collected']
    permission_classes = [IsStaffWriteOwnerDelete]

    def get_queryset(self):
        return only_own(super().get_queryset(), self.request.user, 'staff')

    def perform_create(self, serializer):
        session = serializer.save(staff=self.request.user if self.request.user.is_authenticated else None)
        write_audit(
            'create',
            'PhotocopySession',
            session.id,
            self.request.user,
            metadata={
                'copies': session.total_copies,
                'expected': money(session.expected_revenue),
                'collected': money(session.actual_cash_collected),
                'gap': money(session.revenue_gap),
            },
        )


class DailyCashCountViewSet(viewsets.ModelViewSet):
    """Only owners view or enter one combined shop count per day."""

    queryset = DailyCashCount.objects.all().select_related('recorded_by')
    serializer_class = DailyCashCountSerializer
    permission_classes = [IsOwnerUser]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        queryset = super().get_queryset()
        date_value = self.request.query_params.get('date')
        if date_value:
            queryset = queryset.filter(date=parse_date_param(date_value, 'date'))
        return queryset

    def _audit_count(self, count, action):
        data = self.get_serializer(count).data
        write_audit(action, 'DailyCashCount', count.id, self.request.user, reason=count.note,
                    metadata={'date': str(count.date), 'cash': data['cash_amount'], 'transfer': data['transfer_amount'],
                              'recorded': data['recorded_total'], 'difference': data['difference']})

    def create(self, request, *args, **kwargs):
        today = timezone.localdate()
        with transaction.atomic():
            existing = DailyCashCount.objects.select_for_update().filter(date=today).first()
            serializer = self.get_serializer(existing, data=request.data, partial=bool(existing))
            serializer.is_valid(raise_exception=True)
            count = serializer.save(recorded_by=request.user, date=today)
            self._audit_count(count, 'update' if existing else 'create')
        return response.Response(self.get_serializer(count).data,
                                 status=status.HTTP_200_OK if existing else status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        with transaction.atomic():
            count = serializer.save(recorded_by=self.request.user)
            self._audit_count(count, 'update')

    def perform_destroy(self, instance):
        self._audit_count(instance, 'delete')
        instance.delete()


class ExpenseViewSet(viewsets.ModelViewSet):
    """Expenses are owner-only. They are taken off the day's takings in the money statement."""

    queryset = Expense.objects.all().select_related('recorded_by', 'paid_by')
    serializer_class = ExpenseSerializer
    permission_classes = [IsOwnerUser]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        queryset = only_own(super().get_queryset(), self.request.user, 'recorded_by')
        date_value = self.request.query_params.get('date')
        if date_value:
            queryset = queryset.filter(date=parse_date_param(date_value, 'date'))
        return queryset

    def _checked_date(self, serializer, instance=None):
        today = timezone.localdate()
        day = serializer.validated_data.get('date') or (instance.date if instance else today)
        if not is_owner_user(self.request.user) and day != today:
            raise serializers.ValidationError({'date': 'Staff can only record expenses for today.'})
        if day > today:
            raise serializers.ValidationError({'date': "Expenses can't be recorded for a future day."})
        return day

    def perform_create(self, serializer):
        expense = serializer.save(recorded_by=self.request.user, date=self._checked_date(serializer))
        write_audit('create', 'Expense', expense.id, self.request.user, metadata=expense_details(expense))

    def perform_update(self, serializer):
        if not is_owner_user(self.request.user) and serializer.instance.date != timezone.localdate():
            raise serializers.ValidationError({'detail': "You can only change today's expenses."})
        expense = serializer.save(date=self._checked_date(serializer, serializer.instance))
        write_audit('update', 'Expense', expense.id, self.request.user, metadata=expense_details(expense))

    def perform_destroy(self, instance):
        details = expense_details(instance)
        expense_id = instance.id
        instance.delete()
        write_audit('delete', 'Expense', expense_id, self.request.user, metadata=details)


def expense_details(expense):
    return {
        'date': str(expense.date),
        'category': expense.category,
        'description': expense.description,
        'amount': money(expense.amount),
        'paid_from_takings': expense.paid_from_takings,
        'paid_by': person_name(expense.paid_by) if expense.paid_by_id else '',
    }


@decorators.api_view(['GET'])
@decorators.permission_classes([IsOwnerUser])
def money_statement(request):
    """All recorded shop collections and expenses, with manual counts for reconciliation."""
    start = parse_date_param(request.query_params.get('start'), 'start')
    end = parse_date_param(request.query_params.get('end'), 'end')
    if end < start:
        raise serializers.ValidationError({'end': 'end must be on or after start.'})
    if (end - start).days > 92:
        raise serializers.ValidationError({'end': 'Choose a period of at most 3 months.'})

    zero = Decimal('0.00')
    counts = (
        DailyCashCount.objects.filter(date__range=(start, end))
        .values('date')
        .annotate(cash=Sum('cash_amount'), transfer=Sum('transfer_amount'), entries=Count('id'))
    )
    expenses = Expense.objects.filter(date__range=(start, end))
    spent = expenses.values('date').annotate(total=Sum('amount'))
    by_category = expenses.values('category').annotate(total=Sum('amount')).order_by('-total')

    # Received comes from all collectors' records, never from the manual cash count.
    payments_by_day = {
        row['day']: row['total'] or zero
        for row in PaymentRecord.objects.filter(created_at__date__range=(start, end))
        .annotate(day=TruncDate('created_at', tzinfo=timezone.get_current_timezone()))
        .values('day').annotate(total=Sum('amount'))
    }
    copies_by_day = {
        row['day']: row['total'] or zero
        for row in PhotocopySession.objects.filter(created_at__date__range=(start, end))
        .annotate(day=TruncDate('created_at', tzinfo=timezone.get_current_timezone()))
        .values('day').annotate(total=Sum('actual_cash_collected'))
    }

    counts_by_day = {row['date']: row for row in counts}
    spent_by_day = {row['date']: row['total'] for row in spent}

    days = []
    totals = {'cash': zero, 'transfer': zero, 'received': zero, 'expenses': zero}
    day = start
    while day <= end:
        count = counts_by_day.get(day, {})
        cash = count.get('cash') or zero
        transfer = count.get('transfer') or zero
        received = payments_by_day.get(day, zero) + copies_by_day.get(day, zero)
        spent_today = spent_by_day.get(day) or zero
        days.append({
            'date': str(day),
            'cash': money(cash),
            'transfer': money(transfer),
            'count_entered': bool(count),
            'received': money(received),
            'expenses': money(spent_today),
            'remaining': money(received - spent_today),
        })
        for key, value in (('cash', cash), ('transfer', transfer), ('received', received), ('expenses', spent_today)):
            totals[key] += value
        day += timedelta(days=1)

    labels = dict(Expense.Category.choices)
    return response.Response({
        'start': str(start),
        'end': str(end),
        'days': days,
        'totals': {**{key: money(value) for key, value in totals.items()},
                   'remaining': money(totals['received'] - totals['expenses'])},
        'expenses_by_category': [
            {'category': row['category'], 'label': labels.get(row['category'], row['category']), 'total': money(row['total'])}
            for row in by_category
        ],
    })


class AuditLogViewSet(OneDayFilterMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().select_related('performed_by')
    serializer_class = AuditLogSerializer
    search_fields = ['action', 'model_name', 'performed_by__username']
    ordering_fields = ['created_at']
    permission_classes = [IsOwnerUser]


class SystemSettingViewSet(viewsets.ModelViewSet):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer
    permission_classes = [IsStaffReadOwnerWrite]


class StaffAccountViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).order_by('username')
    permission_classes = [IsOwnerUser]
    search_fields = ['username', 'first_name', 'last_name', 'email']
    ordering_fields = ['username', 'date_joined', 'last_login', 'is_active']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_serializer_class(self):
        return StaffAccountSerializer

    def perform_update(self, serializer):
        user = serializer.save()
        write_audit('update', 'StaffAccount', user.id, self.request.user, metadata={'username': user.username})

    @decorators.action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        account = self.get_object()
        serializer = StaffPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account.set_password(serializer.validated_data['new_password'])
        account.save(update_fields=['password'])
        write_audit(
            'reset_password',
            'StaffAccount',
            account.id,
            self.request.user,
            metadata={'username': account.username},
        )
        return response.Response({'detail': 'Password reset successfully.'}, status=status.HTTP_200_OK)


class StaffInvitationViewSet(viewsets.ModelViewSet):
    queryset = StaffInvitation.objects.all().select_related('invited_by', 'accepted_user').order_by('-created_at')
    permission_classes = [IsOwnerUser]
    http_method_names = ['get', 'post', 'head', 'options']
    search_fields = ['first_name', 'last_name', 'email']
    ordering_fields = ['created_at', 'expires_at', 'accepted_at', 'email']

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffInvitationCreateSerializer
        return StaffInvitationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = serializer.save()
        write_audit(
            'create',
            'StaffInvitation',
            invitation.id,
            request.user,
            metadata={'email': invitation.email, 'role': invitation.role},
        )
        output = StaffInvitationSerializer(invitation, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return response.Response(output.data, status=status.HTTP_201_CREATED, headers=headers)


@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.AllowAny])
@decorators.throttle_classes([LoginRateThrottle])
def auth_login(request):
    serializer = AuthLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data['user']
    token, _ = Token.objects.get_or_create(user=user)
    update_last_login(None, user)
    return response.Response(
        {
            'token': token.key,
            'user': CurrentUserSerializer(user).data,
        },
        status=status.HTTP_200_OK,
    )


@decorators.api_view(['GET'])
@decorators.permission_classes([permissions.AllowAny])
def health_check(request):
    return response.Response({'status': 'ok'}, status=status.HTTP_200_OK)


@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.IsAuthenticated])
def auth_logout(request):
    Token.objects.filter(user=request.user).delete()
    return response.Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)


@decorators.api_view(['GET'])
@decorators.permission_classes([permissions.IsAuthenticated])
def auth_me(request):
    if not is_staff_user(request.user):
        return response.Response({'detail': 'This account does not have CMS access.'}, status=status.HTTP_403_FORBIDDEN)
    return response.Response(CurrentUserSerializer(request.user).data, status=status.HTTP_200_OK)


@decorators.api_view(['GET'])
@decorators.permission_classes([permissions.AllowAny])
def staff_invitation_detail(request, token):
    invitation = StaffInvitation.objects.filter(token=token).first()
    if not invitation:
        return response.Response({'detail': 'This invitation link is invalid.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = StaffInvitationDetailSerializer(invitation)
    return response.Response(serializer.data, status=status.HTTP_200_OK)


@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.AllowAny])
@decorators.throttle_classes([LoginRateThrottle])
def staff_invitation_accept(request):
    serializer = StaffInvitationAcceptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    token, _ = Token.objects.get_or_create(user=user)
    return response.Response(
        {
            'detail': 'Your account has been set up successfully.',
            'token': token.key,
            'user': CurrentUserSerializer(user).data,
        },
        status=status.HTTP_200_OK,
    )


@decorators.api_view(['GET'])
@decorators.permission_classes([permissions.AllowAny])
def job_attachment_download(request, pk):
    # Staff open attachments through plain links (no auth header), so accept either a
    # logged-in staff user or a short-lived signature issued by JobAttachmentSerializer.
    if not is_staff_user(request.user):
        try:
            signed_pk = signing.TimestampSigner(salt=ATTACHMENT_LINK_SALT).unsign(
                request.query_params.get('sig', ''),
                max_age=ATTACHMENT_LINK_MAX_AGE_SECONDS,
            )
        except signing.BadSignature:
            signed_pk = None
        if signed_pk != str(pk):
            return response.Response(
                {'detail': 'This download link is invalid or has expired.'},
                status=status.HTTP_403_FORBIDDEN,
            )
    attachment = get_object_or_404(JobAttachment, pk=pk)
    return FileResponse(
        attachment.file.open('rb'),
        as_attachment=True,
        filename=attachment.original_name or attachment.file.name.rsplit('/', 1)[-1],
    )


@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.AllowAny])
def public_checkout_request(request):
    payload = parse_public_payload(request)
    serializer = PublicCheckoutRequestSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    job = serializer.save()
    files = request.FILES.getlist('files')
    if files:
        create_job_attachments(job, files)
    job.customer.last_job_date = timezone.now()
    job.customer.save(update_fields=['last_job_date', 'updated_at'])
    JobStatusHistory.objects.create(job=job, from_status='', to_status=job.status, changed_by=None)
    write_audit(
        'create',
        'Job',
        job.id,
        metadata={
            'source': 'website_checkout',
            'customer_name': job.customer.full_name,
            'job_type': job.job_type,
        },
    )
    return response.Response(
        {
            'detail': 'Your order request has been submitted successfully.',
            'job_id': job.id,
            'status': job.status,
        },
        status=status.HTTP_201_CREATED,
    )


@decorators.api_view(['POST'])
@decorators.permission_classes([permissions.AllowAny])
def public_design_request(request):
    payload = parse_public_payload(request)
    serializer = PublicDesignRequestSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    job = serializer.save()
    files = request.FILES.getlist('files')
    if files:
        create_job_attachments(job, files)
    job.customer.last_job_date = timezone.now()
    job.customer.save(update_fields=['last_job_date', 'updated_at'])
    JobStatusHistory.objects.create(job=job, from_status='', to_status=job.status, changed_by=None)
    write_audit(
        'create',
        'Job',
        job.id,
        metadata={
            'source': 'website_design_request',
            'customer_name': job.customer.full_name,
            'job_type': job.job_type,
        },
    )
    return response.Response(
        {
            'detail': 'Your design request has been submitted successfully.',
            'job_id': job.id,
            'status': job.status,
        },
        status=status.HTTP_201_CREATED,
    )


@decorators.api_view(['GET'])
@decorators.permission_classes([IsStaffUser])
def daily_summary(request):
    date_param = request.query_params.get('date')
    target = timezone.localdate()
    if date_param:
        try:
            target = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            return response.Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    start_of_day = timezone.make_aware(datetime.combine(target, datetime.min.time()))
    end_of_day = start_of_day + timedelta(days=1)

    # Staff get totals for their own work only; owners get the whole shop.
    user = request.user
    jobs = only_own(Job.objects.all(), user, 'created_by')
    jobs_created = jobs.filter(created_at__gte=start_of_day, created_at__lt=end_of_day)
    jobs_completed = jobs.filter(
        status=Job.JobStatus.COMPLETED,
        updated_at__gte=start_of_day,
        updated_at__lt=end_of_day,
    )
    payments = only_own(PaymentRecord.objects.all(), user, 'recorded_by').filter(
        created_at__gte=start_of_day, created_at__lt=end_of_day
    )
    photocopy = only_own(PhotocopySession.objects.all(), user, 'staff').filter(
        created_at__gte=start_of_day, created_at__lt=end_of_day
    )

    outstanding_balances = jobs_created.aggregate(total=Sum('balance_due')).get('total') or Decimal('0.00')
    total_revenue = payments.aggregate(total=Sum('amount')).get('total') or Decimal('0.00')
    photocopy_revenue = photocopy.aggregate(total=Sum('actual_cash_collected')).get('total') or Decimal('0.00')

    anomalies = {
        'completed_unpaid_jobs': jobs_completed.exclude(payment_status=Job.PaymentStatus.PAID).count(),
        'photocopy_discrepancies': photocopy.filter(has_discrepancy=True).count(),
    }

    return response.Response(
        {
            'date': str(target),
            'jobs_created': jobs_created.count(),
            'jobs_completed': jobs_completed.count(),
            'payments_received': payments.count(),
            'photocopy_sessions': photocopy.count(),
            'total_revenue': total_revenue,
            'photocopy_revenue': photocopy_revenue,
            'outstanding_balances': outstanding_balances,
            'anomalies': anomalies,
        }
    )
