from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Announcement,
    AuditLog,
    Customer,
    DailyCashCount,
    Expense,
    Job,
    JobAttachment,
    JobItem,
    JobStatusHistory,
    MessageTemplate,
    Order,
    OrderItem,
    OrderMessageLog,
    PaymentRecord,
    PhotocopySession,
    Product,
    StaffInvitation,
    SystemSetting,
)

User = get_user_model()


def person_name(user):
    """A person's full name for display, falling back to their username."""
    if not user:
        return ''
    return f'{user.first_name} {user.last_name}'.strip() or user.username

ATTACHMENT_LINK_SALT = 'crm.job-attachment-download'
ATTACHMENT_LINK_MAX_AGE_SECONDS = 12 * 60 * 60

# The Naira sign, its UTF-8-read-as-cp1252 mojibake, and currency codes clients may send.
CURRENCY_MARKERS = ('₦', 'â‚¦', 'NGN', 'N')


def parse_public_money(value):
    raw = str(value or '').strip()
    if not raw:
        return Decimal('0.00')

    cleaned = raw.replace(',', '').replace(' ', '')
    for marker in CURRENCY_MARKERS:
        if cleaned.upper().startswith(marker.upper()):
            cleaned = cleaned[len(marker):]
            break
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal('0.00')

    return amount if amount >= Decimal('0.00') else Decimal('0.00')


def resolve_public_customer(*, full_name, phone='', email='', address='', customer_note=''):
    normalized_email = str(email or '').strip().lower()
    normalized_phone = str(phone or '').strip()
    normalized_name = str(full_name or '').strip()

    customer = None

    if normalized_email:
        customer = Customer.objects.filter(email__iexact=normalized_email).first()

    if not customer and normalized_phone:
        customer = Customer.objects.filter(phone=normalized_phone).first()

    if not customer and normalized_name and normalized_phone:
        customer = Customer.objects.filter(
            full_name__iexact=normalized_name,
            phone=normalized_phone,
        ).first()

    if not customer:
        return Customer.objects.create(
            full_name=normalized_name,
            phone=normalized_phone,
            email=normalized_email,
            address=str(address or '').strip(),
            customer_type=Customer.CustomerType.RECURRING,
            contact_preference=(
                Customer.ContactPreference.WHATSAPP
                if normalized_phone
                else Customer.ContactPreference.EMAIL
            ),
            notes=str(customer_note or '').strip(),
        )

    # Public submissions are unauthenticated, so they may only fill gaps in an existing
    # record, never overwrite details staff already hold. What the visitor typed is kept
    # on the job itself.
    changed_fields = []

    if normalized_name and not customer.full_name:
        customer.full_name = normalized_name
        changed_fields.append('full_name')
    if normalized_phone and not customer.phone:
        customer.phone = normalized_phone
        changed_fields.append('phone')
    if normalized_email and not customer.email:
        customer.email = normalized_email
        changed_fields.append('email')
    if address and not customer.address:
        customer.address = str(address).strip()
        changed_fields.append('address')
    if customer_note and customer_note.strip() and customer_note.strip() not in str(customer.notes or ''):
        existing_note = str(customer.notes or '').strip()
        customer.notes = '\n\n'.join(filter(None, [existing_note, customer_note.strip()]))
        changed_fields.append('notes')

    if changed_fields:
        changed_fields.append('updated_at')
        customer.save(update_fields=changed_fields)

    return customer


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


class CustomerSerializer(serializers.ModelSerializer):
    orders_count = serializers.IntegerField(read_only=True)
    is_returning_customer = serializers.BooleanField(read_only=True)

    class Meta:
        model = Customer
        fields = '__all__'


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = '__all__'
        read_only_fields = ('line_total',)
        extra_kwargs = {
            'order': {'required': False},
        }


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, required=False)
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ('balance_due',)

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            item_data.pop('order', None)
            OrderItem.objects.create(order=order, **item_data)
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                item_data.pop('order', None)
                OrderItem.objects.create(order=instance, **item_data)
        return instance


class MessageTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageTemplate
        fields = '__all__'


class OrderMessageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderMessageLog
        fields = '__all__'


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = '__all__'


class JobStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.username', read_only=True)

    class Meta:
        model = JobStatusHistory
        fields = '__all__'


class JobAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = JobAttachment
        fields = ('id', 'original_name', 'content_type', 'size_bytes', 'created_at', 'download_url')

    def get_download_url(self, obj):
        signature = signing.TimestampSigner(salt=ATTACHMENT_LINK_SALT).sign(str(obj.id))
        path = f'/api/job-attachments/{obj.id}/download/?sig={signature}'
        request = self.context.get('request')
        if not request:
            return path
        return request.build_absolute_uri(path)


class JobItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobItem
        fields = ('id', 'description', 'quantity', 'rate', 'amount')
        read_only_fields = ('id', 'amount')
        extra_kwargs = {'quantity': {'min_value': 1}, 'rate': {'min_value': Decimal('0.00')}}


def summarize_items(items):
    lines = [f"{item['description']} x{item['quantity']}" for item in items]
    return ', '.join(lines)[:500]


class JobSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    customer_phone = serializers.CharField(source='customer.phone', read_only=True)
    customer_email = serializers.CharField(source='customer.email', read_only=True)
    customer_business_name = serializers.CharField(source='customer.business_name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    def get_created_by_name(self, obj):
        # The person who added the job; blank for website orders.
        return person_name(obj.created_by)

    status_history = JobStatusHistorySerializer(many=True, read_only=True)
    attachments = JobAttachmentSerializer(many=True, read_only=True)
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    items = JobItemSerializer(many=True, required=False)
    # Optional on create: the price agreed with the customer. The difference from the items'
    # total becomes a discount, logged with who gave it (same rule as discounts on payments).
    agreed_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.00'), required=False, allow_null=True, write_only=True
    )
    discount_reason = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Job
        fields = '__all__'
        read_only_fields = ('total', 'balance_due', 'payment_status', 'discount_amount')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        items = attrs.get('items')
        if items is not None and self.instance is None and not items and 'unit_price' not in attrs:
            raise serializers.ValidationError({'items': 'Add at least one item.'})
        agreed_total = attrs.get('agreed_total')
        if agreed_total is not None:
            if self.instance is not None:
                raise serializers.ValidationError(
                    {'agreed_total': 'Give a discount while recording a payment for an existing job.'}
                )
            if items:
                gross = sum(Decimal(item['quantity']) * item['rate'] for item in items)
            else:
                gross = Decimal(attrs.get('quantity') or 1) * Decimal(attrs.get('unit_price') or 0)
            paid = Decimal(attrs.get('amount_paid') or 0)
            if agreed_total > gross:
                raise serializers.ValidationError(
                    {'agreed_total': f'The discounted price cannot be more than the total ({gross}).'}
                )
            if agreed_total < paid:
                raise serializers.ValidationError(
                    {'agreed_total': f'The discounted price cannot be less than the amount paid ({paid}).'}
                )
        return attrs

    def create(self, validated_data):
        items = validated_data.pop('items', None) or []
        agreed_total = validated_data.pop('agreed_total', None)
        discount_reason = str(validated_data.pop('discount_reason', '') or '').strip()
        if items and not validated_data.get('description'):
            validated_data['description'] = summarize_items(items)

        job = Job.objects.create(**validated_data)
        for item in items:
            JobItem.objects.create(job=job, **item)
        if agreed_total is not None:
            job.save()  # pick up the items' total first
            job.discount_amount = job.total - agreed_total
            job.discount_reason = discount_reason
        job.save()
        self.applied_discount = (
            {'total': str(job.total), 'agreed_total': str(agreed_total), 'discount_amount': str(job.discount_amount)}
            if agreed_total is not None and job.discount_amount
            else None
        )
        return job

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        validated_data.pop('agreed_total', None)
        validated_data.pop('discount_reason', None)
        job = super().update(instance, validated_data)
        if items is not None:
            job.items.all().delete()
            for item in items:
                JobItem.objects.create(job=job, **item)
            job.save()
        return job


class PaymentRecordSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()

    def get_recorded_by_name(self, obj):
        return person_name(obj.recorded_by)

    def get_customer_name(self, obj):
        return obj.job.customer.full_name if obj.job_id else ''

    # Optional: the price agreed with the customer for the linked job. The difference from
    # the job's total is saved as a discount before this payment is applied.
    agreed_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.00'), required=False, allow_null=True, write_only=True
    )
    discount_reason = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = PaymentRecord
        fields = '__all__'

    def validate(self, attrs):
        attrs = super().validate(attrs)
        agreed_total = attrs.get('agreed_total')
        if agreed_total is None:
            return attrs
        if self.instance is not None:
            raise serializers.ValidationError({'agreed_total': 'Discounts can only be given with a new payment.'})
        job = attrs.get('job')
        if not job:
            raise serializers.ValidationError({'agreed_total': 'Choose a job to apply a discount to.'})
        if agreed_total > job.total:
            raise serializers.ValidationError(
                {'agreed_total': f'The agreed price cannot be more than the job total ({job.total}).'}
            )
        if agreed_total < job.amount_paid:
            raise serializers.ValidationError(
                {'agreed_total': f'The agreed price cannot be less than what was already paid ({job.amount_paid}).'}
            )
        return attrs


class PhotocopySessionSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()

    def get_staff_name(self, obj):
        return person_name(obj.staff)


    class Meta:
        model = PhotocopySession
        fields = '__all__'
        read_only_fields = ('total_copies', 'expected_revenue', 'revenue_gap', 'has_discrepancy')


def recorded_total_for(user, day):
    """Money a staff member recorded in the CMS on `day`: payments plus photocopy cash."""
    from django.db.models import Sum

    payments = PaymentRecord.objects.filter(recorded_by=user, created_at__date=day).aggregate(t=Sum('amount'))['t']
    copies = PhotocopySession.objects.filter(staff=user, created_at__date=day).aggregate(t=Sum('actual_cash_collected'))['t']
    return ((payments or Decimal('0.00')) + (copies or Decimal('0.00'))).quantize(Decimal('0.01'))


def takings_expenses_for(user, day):
    """Expenses a person paid out of the money they collected on `day`."""
    from django.db.models import Sum

    from django.db.models import Q

    total = (
        Expense.objects.filter(date=day, paid_from_takings=True)
        .filter(Q(paid_by=user) | Q(paid_by__isnull=True, recorded_by=user))
        .aggregate(t=Sum('amount'))['t']
    )
    return (total or Decimal('0.00')).quantize(Decimal('0.01'))


class DailyCashCountSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    counted_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    recorded_total = serializers.SerializerMethodField()
    spent_from_takings = serializers.SerializerMethodField()
    expected_total = serializers.SerializerMethodField()
    difference = serializers.SerializerMethodField()

    class Meta:
        model = DailyCashCount
        fields = (
            'id', 'staff', 'staff_name', 'date', 'cash_amount', 'transfer_amount', 'note',
            'counted_total', 'recorded_total', 'spent_from_takings', 'expected_total', 'difference',
            'created_at', 'updated_at',
        )
        read_only_fields = ('staff', 'date')
        extra_kwargs = {
            'cash_amount': {'min_value': Decimal('0.00')},
            'transfer_amount': {'min_value': Decimal('0.00')},
        }

    def get_staff_name(self, obj):
        return person_name(obj.staff)

    def _recorded(self, obj):
        # Always compare with the latest CMS figures, so later payments update the check.
        cache = self.context.setdefault('_recorded_totals', {})
        key = (obj.staff_id, obj.date)
        if key not in cache:
            cache[key] = recorded_total_for(obj.staff, obj.date)
        return cache[key]

    def _spent(self, obj):
        cache = self.context.setdefault('_spent_totals', {})
        key = (obj.staff_id, obj.date)
        if key not in cache:
            cache[key] = takings_expenses_for(obj.staff, obj.date)
        return cache[key]

    def _expected(self, obj):
        # What they should be holding: what they recorded, less what they spent from it.
        return self._recorded(obj) - self._spent(obj)

    def get_recorded_total(self, obj):
        return str(self._recorded(obj))

    def get_spent_from_takings(self, obj):
        return str(self._spent(obj))

    def get_expected_total(self, obj):
        return str(self._expected(obj))

    # The comparison with the CMS is for the owner only: staff do a "blind" count.
    OWNER_ONLY_FIELDS = ('recorded_total', 'spent_from_takings', 'expected_total', 'difference')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        show_all = self.context.get('show_comparison') or bool(user and user.is_authenticated and user.is_superuser)
        if not show_all:
            for field in self.OWNER_ONLY_FIELDS:
                data.pop(field, None)
        return data

    def get_difference(self, obj):
        # Positive: more money counted than expected (over). Negative: short.
        return str((obj.counted_total - self._expected(obj)).quantize(Decimal('0.01')))


class ExpenseSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()
    paid_by_name = serializers.SerializerMethodField()
    category_label = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Expense
        fields = (
            'id', 'date', 'category', 'category_label', 'description', 'amount', 'paid_from_takings',
            'paid_by', 'paid_by_name', 'recorded_by', 'recorded_by_name', 'created_at', 'updated_at',
        )
        read_only_fields = ('recorded_by',)
        extra_kwargs = {'amount': {'min_value': Decimal('0.01')}, 'date': {'required': False}}

    def get_recorded_by_name(self, obj):
        return person_name(obj.recorded_by)

    def get_paid_by_name(self, obj):
        return person_name(obj.paid_by or obj.recorded_by)


class AuditLogSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source='performed_by.username', read_only=True)
    performed_by_display = serializers.SerializerMethodField()

    def get_performed_by_display(self, obj):
        return person_name(obj.performed_by) or 'Website'

    class Meta:
        model = AuditLog
        fields = '__all__'


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = '__all__'


class CurrentUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'is_staff',
            'is_superuser',
            'role',
            'display_name',
            'date_joined',
            'last_login',
        )

    def get_role(self, obj):
        return 'owner' if obj.is_superuser else 'staff'

    def get_display_name(self, obj):
        full_name = f'{obj.first_name} {obj.last_name}'.strip()
        return full_name or obj.username


class AuthLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        username = attrs.get('username', '').strip()
        password = attrs.get('password', '')
        user = authenticate(username=username, password=password)

        if not user:
            raise serializers.ValidationError({'detail': 'Invalid username or password.'})

        if not user.is_active:
            raise serializers.ValidationError({'detail': 'This account is inactive.'})

        if not (user.is_staff or user.is_superuser):
            raise serializers.ValidationError({'detail': 'This account does not have CMS access.'})

        attrs['user'] = user
        return attrs


class StaffAccountSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=[('staff', 'Staff'), ('owner', 'Owner/Admin')], required=False)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'is_staff',
            'is_superuser',
            'role',
            'display_name',
            'date_joined',
            'last_login',
        )
        read_only_fields = ('is_staff', 'is_superuser', 'display_name', 'date_joined', 'last_login')

    def get_display_name(self, obj):
        full_name = f'{obj.first_name} {obj.last_name}'.strip()
        return full_name or obj.username

    def update(self, instance, validated_data):
        role = validated_data.pop('role', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)

        if role == 'owner':
            instance.is_staff = True
            instance.is_superuser = True
        elif role == 'staff':
            instance.is_staff = True
            instance.is_superuser = False

        instance.save()
        return instance


class StaffAccountCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    role = serializers.ChoiceField(choices=[('staff', 'Staff'), ('owner', 'Owner/Admin')], default='staff')

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password', 'is_active', 'role')

    def create(self, validated_data):
        password = validated_data.pop('password')
        role = validated_data.pop('role', 'staff')
        is_owner = role == 'owner'
        user = User(
            **validated_data,
            is_staff=True,
            is_superuser=is_owner,
        )
        user.set_password(password)
        user.save()
        return user


class StaffPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=8, trim_whitespace=False)


class StaffInvitationSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    invited_by_name = serializers.CharField(source='invited_by.username', read_only=True)
    accepted_user_name = serializers.CharField(source='accepted_user.username', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = StaffInvitation
        fields = (
            'id',
            'first_name',
            'last_name',
            'email',
            'role',
            'token',
            'display_name',
            'status',
            'invited_by',
            'invited_by_name',
            'accepted_user',
            'accepted_user_name',
            'accepted_at',
            'expires_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'token',
            'display_name',
            'status',
            'invited_by',
            'invited_by_name',
            'accepted_user',
            'accepted_user_name',
            'accepted_at',
            'expires_at',
            'created_at',
            'updated_at',
        )

    def get_display_name(self, obj):
        full_name = f'{obj.first_name} {obj.last_name}'.strip()
        return full_name or obj.email

    def get_status(self, obj):
        if obj.accepted_at:
            return 'accepted'
        if obj.expires_at <= timezone.now():
            return 'expired'
        return 'pending'


class StaffInvitationCreateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=StaffInvitation.Role.choices, default=StaffInvitation.Role.STAFF)

    class Meta:
        model = StaffInvitation
        fields = ('first_name', 'last_name', 'email', 'role')

    def validate_email(self, value):
        normalized_email = value.strip().lower()
        existing_pending = StaffInvitation.objects.filter(
            email__iexact=normalized_email,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        if self.instance:
            existing_pending = existing_pending.exclude(pk=self.instance.pk)
        if existing_pending.exists():
            raise serializers.ValidationError('A pending invitation already exists for this email.')

        existing_staff_account = User.objects.filter(
            email__iexact=normalized_email,
        ).filter(
            Q(is_staff=True) | Q(is_superuser=True)
        )
        if existing_staff_account.exists():
            raise serializers.ValidationError('A staff or owner account already uses this email.')

        return normalized_email

    def create(self, validated_data):
        request = self.context.get('request')
        return StaffInvitation.objects.create(
            **validated_data,
            invited_by=request.user if request and request.user.is_authenticated else None,
        )


class StaffInvitationDetailSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()

    class Meta:
        model = StaffInvitation
        fields = (
            'first_name',
            'last_name',
            'email',
            'role',
            'display_name',
            'expires_at',
            'is_valid',
        )

    def get_display_name(self, obj):
        full_name = f'{obj.first_name} {obj.last_name}'.strip()
        return full_name or obj.email

    def get_is_valid(self, obj):
        return not obj.accepted_at and obj.expires_at > timezone.now()


class StaffInvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)

    def validate(self, attrs):
        token = attrs.get('token', '').strip()
        username = attrs.get('username', '').strip()
        password = attrs.get('password', '')

        try:
            invitation = StaffInvitation.objects.get(token=token)
        except StaffInvitation.DoesNotExist as exc:
            raise serializers.ValidationError({'detail': 'This invitation link is invalid.'}) from exc

        if invitation.accepted_at:
            raise serializers.ValidationError({'detail': 'This invitation has already been used.'})

        if invitation.expires_at <= timezone.now():
            raise serializers.ValidationError({'detail': 'This invitation link has expired.'})

        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({'username': 'This username is already taken.'})

        existing_staff_account = User.objects.filter(
            email__iexact=invitation.email,
        ).filter(
            Q(is_staff=True) | Q(is_superuser=True)
        )
        if existing_staff_account.exists():
            raise serializers.ValidationError(
                {'detail': 'A staff or owner account already exists for this invitation email.'}
            )

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)}) from exc

        attrs['invitation'] = invitation
        attrs['username'] = username
        return attrs

    def create(self, validated_data):
        invitation = validated_data['invitation']
        user = User(
            username=validated_data['username'],
            first_name=invitation.first_name,
            last_name=invitation.last_name,
            email=invitation.email,
            is_active=True,
            is_staff=True,
            is_superuser=invitation.role == StaffInvitation.Role.OWNER,
        )
        user.set_password(validated_data['password'])
        user.save()

        invitation.accepted_user = user
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['accepted_user', 'accepted_at', 'updated_at'])
        return user


class PublicCheckoutItemSerializer(serializers.Serializer):
    slug = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField()
    price = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1)
    requestMode = serializers.CharField(required=False, allow_blank=True)
    specificationSummary = serializers.CharField(required=False, allow_blank=True)
    uploadedDesignNames = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        allow_empty=True,
    )


class PublicCheckoutRequestSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    country = serializers.CharField()
    street_address = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField()
    additional_note = serializers.CharField(required=False, allow_blank=True)
    items = PublicCheckoutItemSerializer(many=True, min_length=1)

    def create(self, validated_data):
        items = validated_data['items']
        full_name = f"{validated_data['first_name']} {validated_data['last_name']}".strip()

        customer = resolve_public_customer(
            full_name=full_name,
            phone=validated_data['phone'],
            email=validated_data['email'],
            address=validated_data['street_address'],
            customer_note='Website checkout order customer.',
        )

        total_quantity = sum(int(item.get('quantity') or 1) for item in items)

        item_lines = []
        for item in items:
            parts = [f"{item['title']} x{item['quantity']}"]
            if item.get('specificationSummary'):
                parts.append(item['specificationSummary'])
            if item.get('price'):
                parts.append(f"Price: {item['price']}")
            if item.get('uploadedDesignNames'):
                parts.append(f"Files: {', '.join(item['uploadedDesignNames'])}")
            item_lines.append(' | '.join(parts))

        note_lines = [
            'Website checkout order.',
            f'Name: {full_name}',
            f"Country: {validated_data['country']}",
            f"Address: {validated_data['street_address']}",
            f"Phone: {validated_data['phone']}",
            f"Email: {validated_data['email']}",
        ]
        if validated_data.get('additional_note'):
            note_lines.append(f"Customer note: {validated_data['additional_note']}")

        job = Job.objects.create(
            customer=customer,
            job_type='printing',
            description=(
                f"Website order: {items[0]['title']}"
                if len(items) == 1
                else f"Website order with {len(items)} items"
            ),
            quantity=total_quantity,
            special_instructions='\n'.join(note_lines),
            project_scope_note='Items:\n' + '\n'.join(f"- {line}" for line in item_lines),
            status=Job.JobStatus.PENDING,
            amount_paid=Decimal('0.00'),
        )
        for item in items:
            JobItem.objects.create(
                job=job,
                description=str(item['title'])[:255],
                quantity=int(item.get('quantity') or 1),
                rate=parse_public_money(item.get('price')),
            )
        job.save()  # total = sum of the items
        return job


class PublicDesignRequestSerializer(serializers.Serializer):
    product_slug = serializers.CharField(required=False, allow_blank=True)
    product_title = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)
    full_name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField()
    request_details = serializers.CharField()
    uploaded_design_names = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        allow_empty=True,
    )
    no_logo = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        uploaded_design_names = attrs.get('uploaded_design_names') or []
        no_logo = bool(attrs.get('no_logo'))
        if not uploaded_design_names and not no_logo:
            raise serializers.ValidationError(
                {'uploaded_design_names': 'Upload at least one file or confirm that no logo is available.'}
            )
        return attrs

    def create(self, validated_data):
        customer = resolve_public_customer(
            full_name=validated_data['full_name'],
            phone=validated_data['phone'],
            email=validated_data['email'],
            customer_note='Website design request customer.',
        )

        detail_lines = [
            'Website design request.',
            f"Name: {validated_data['full_name'].strip()}",
            f"Phone: {validated_data['phone']}",
            f"Email: {validated_data['email']}",
        ]

        uploaded_design_names = validated_data.get('uploaded_design_names') or []
        if uploaded_design_names:
            detail_lines.append(f"Uploaded files: {', '.join(uploaded_design_names)}")
        if validated_data.get('no_logo'):
            detail_lines.append('Customer selected: I do not have a logo.')

        return Job.objects.create(
            customer=customer,
            job_type='design',
            description=f"Website design request for {validated_data['product_title']}",
            quantity=validated_data['quantity'],
            unit_price=Decimal('0.00'),
            special_instructions='\n'.join(detail_lines),
            project_scope_note=validated_data['request_details'].strip(),
            status=Job.JobStatus.PENDING,
            amount_paid=Decimal('0.00'),
        )
