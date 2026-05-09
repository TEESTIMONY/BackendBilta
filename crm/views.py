import json
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import FileResponse
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import decorators, permissions, response, serializers, status, viewsets
from rest_framework.authtoken.models import Token

from .models import (
    Announcement,
    AuditLog,
    Customer,
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
    AnnouncementSerializer,
    AuditLogSerializer,
    AuthLoginSerializer,
    CustomerSerializer,
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


class IsStaffReadOwnerWrite(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return is_staff_user(request.user)
        return is_owner_user(request.user)


def write_audit(action, model_name, object_id='', user=None, reason='', metadata=None):
    AuditLog.objects.create(
        action=action,
        model_name=model_name,
        object_id=str(object_id or ''),
        performed_by=user if getattr(user, 'is_authenticated', False) else None,
        reason=reason or '',
        metadata=metadata or {},
    )


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
    queryset = Customer.objects.all().prefetch_related('orders')
    serializer_class = CustomerSerializer
    search_fields = ['full_name', 'phone', 'email', 'city']
    ordering_fields = ['full_name', 'created_at', 'updated_at']
    permission_classes = [IsStaffWriteOwnerDelete]

    def perform_create(self, serializer):
        customer = serializer.save()
        write_audit('create', 'Customer', customer.id, self.request.user)

    def perform_update(self, serializer):
        customer = serializer.save()
        write_audit('update', 'Customer', customer.id, self.request.user)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().select_related('customer').prefetch_related('items')
    serializer_class = OrderSerializer
    search_fields = ['code', 'customer__full_name', 'customer__phone', 'internal_notes']
    ordering_fields = ['created_at', 'updated_at', 'payment_date', 'due_date', 'total_amount']

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


class OrderMessageLogViewSet(viewsets.ModelViewSet):
    queryset = OrderMessageLog.objects.all().select_related('order', 'customer', 'template')
    serializer_class = OrderMessageLogSerializer
    search_fields = ['order__code', 'customer__full_name', 'stage', 'message_body']
    ordering_fields = ['sent_at', 'created_at']


class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    search_fields = ['title', 'message']
    ordering_fields = ['created_at', 'starts_at', 'ends_at']

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


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all().select_related('customer', 'created_by', 'updated_by').prefetch_related('status_history', 'attachments')
    serializer_class = JobSerializer
    search_fields = ['customer__full_name', 'job_type', 'description', 'special_instructions']
    ordering_fields = ['created_at', 'deadline', 'updated_at', 'total']
    permission_classes = [IsStaffWriteOwnerDelete]

    def perform_create(self, serializer):
        job = serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)
        job.customer.last_job_date = timezone.now()
        job.customer.save(update_fields=['last_job_date', 'updated_at'])
        JobStatusHistory.objects.create(job=job, from_status='', to_status=job.status, changed_by=self.request.user if self.request.user.is_authenticated else None)
        write_audit('create', 'Job', job.id, self.request.user)

    def perform_update(self, serializer):
        previous = self.get_object()
        if not is_owner_user(self.request.user):
            protected_fields = {'unit_price', 'quantity', 'amount_paid'}
            attempted = protected_fields.intersection(set(self.request.data.keys()))
            if attempted:
                raise serializers.ValidationError(
                    {
                        'detail': 'Only the owner/admin can change job pricing, quantity, or saved payment amounts after creation.'
                    }
                )
        old_status = previous.status
        job = serializer.save(updated_by=self.request.user if self.request.user.is_authenticated else None)
        job.customer.last_job_date = timezone.now()
        job.customer.save(update_fields=['last_job_date', 'updated_at'])
        if old_status != job.status:
            JobStatusHistory.objects.create(job=job, from_status=old_status, to_status=job.status, changed_by=self.request.user if self.request.user.is_authenticated else None)
        write_audit('update', 'Job', job.id, self.request.user)

    @decorators.action(detail=False, methods=['get'])
    def queue(self, request):
        now = timezone.now()
        qs = self.get_queryset().exclude(status__in=[Job.JobStatus.COMPLETED, Job.JobStatus.CANCELLED])
        data = self.get_serializer(qs, many=True).data
        for row in data:
            deadline = row.get('deadline')
            if deadline:
                parsed_deadline = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                row['is_overdue'] = parsed_deadline < now
            else:
                row['is_overdue'] = False
        return response.Response(data)


class PaymentRecordViewSet(viewsets.ModelViewSet):
    queryset = PaymentRecord.objects.all().select_related('job', 'recorded_by')
    serializer_class = PaymentRecordSerializer
    search_fields = ['service_label', 'job__job_type', 'job__customer__full_name']
    ordering_fields = ['created_at', 'amount']
    permission_classes = [IsStaffWriteOwnerDelete]

    def perform_create(self, serializer):
        payment = serializer.save(recorded_by=self.request.user if self.request.user.is_authenticated else None)
        if payment.job_id:
            job = payment.job
            job.amount_paid = (job.amount_paid or Decimal('0.00')) + payment.amount
            job.save()
        write_audit('create', 'PaymentRecord', payment.id, self.request.user)

    def perform_update(self, serializer):
        reason = self.request.data.get('edit_reason', '').strip()
        if not reason:
            raise serializers.ValidationError({'edit_reason': 'edit_reason is required when editing a payment'})
        payment = serializer.save()
        write_audit('update', 'PaymentRecord', payment.id, self.request.user, reason=reason)


class PhotocopySessionViewSet(viewsets.ModelViewSet):
    queryset = PhotocopySession.objects.all().select_related('staff')
    serializer_class = PhotocopySessionSerializer
    ordering_fields = ['created_at', 'updated_at', 'expected_revenue', 'actual_cash_collected']
    permission_classes = [IsStaffWriteOwnerDelete]

    def perform_create(self, serializer):
        session = serializer.save(staff=self.request.user if self.request.user.is_authenticated else None)
        write_audit('create', 'PhotocopySession', session.id, self.request.user)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
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
def auth_login(request):
    serializer = AuthLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data['user']
    token, _ = Token.objects.get_or_create(user=user)
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
        target = datetime.strptime(date_param, '%Y-%m-%d').date()

    jobs = Job.objects.filter(created_at__date=target)
    completed_jobs = jobs.filter(status=Job.JobStatus.COMPLETED)
    payments = PaymentRecord.objects.filter(created_at__date=target)
    photocopy = PhotocopySession.objects.filter(created_at__date=target)

    outstanding_balances = jobs.aggregate(total=Sum('balance_due')).get('total') or Decimal('0.00')
    total_revenue = payments.aggregate(total=Sum('amount')).get('total') or Decimal('0.00')
    photocopy_revenue = photocopy.aggregate(total=Sum('actual_cash_collected')).get('total') or Decimal('0.00')

    anomalies = {
        'completed_unpaid_jobs': completed_jobs.exclude(payment_status=Job.PaymentStatus.PAID).count(),
        'photocopy_discrepancies': photocopy.filter(has_discrepancy=True).count(),
    }

    return response.Response(
        {
            'date': str(target),
            'jobs_created': jobs.count(),
            'jobs_completed': completed_jobs.count(),
            'payments_received': payments.count(),
            'photocopy_sessions': photocopy.count(),
            'total_revenue': total_revenue,
            'photocopy_revenue': photocopy_revenue,
            'outstanding_balances': outstanding_balances,
            'anomalies': anomalies,
        }
    )
