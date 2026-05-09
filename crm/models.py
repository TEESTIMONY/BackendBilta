from decimal import Decimal
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def default_staff_invitation_expiry():
    return timezone.now() + timedelta(days=7)


class Product(TimeStampedModel):
    slug = models.SlugField(max_length=220, unique=True)
    category = models.CharField(max_length=120)
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    details = models.TextField(blank=True)
    price = models.CharField(max_length=120, default='Price on request')
    size_options = models.JSONField(default=list, blank=True)
    image = models.TextField()
    images = models.JSONField(default=list, blank=True)
    enable_design_upload = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class Customer(TimeStampedModel):
    class CustomerType(models.TextChoices):
        WALK_IN = 'walk_in', 'Walk-in'
        RECURRING = 'recurring', 'Recurring'
        PREMIUM = 'premium', 'Premium / Project'

    class ContactPreference(models.TextChoices):
        PHONE = 'phone', 'Phone'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        EMAIL = 'email', 'Email'

    full_name = models.CharField(max_length=180)
    business_name = models.CharField(max_length=180, blank=True)
    customer_type = models.CharField(max_length=20, choices=CustomerType.choices, default=CustomerType.RECURRING)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    contact_preference = models.CharField(max_length=20, choices=ContactPreference.choices, default=ContactPreference.PHONE)
    follow_up_flag = models.BooleanField(default=False)
    last_job_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name

    @property
    def orders_count(self):
        return self.orders.count()

    @property
    def is_returning_customer(self):
        return self.orders_count > 1


class Order(TimeStampedModel):
    class Source(models.TextChoices):
        ONLINE = 'online', 'Online'
        MANUAL = 'manual', 'Manual / Job Order'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PARTIAL = 'partial', 'Partially Paid'
        PAID = 'paid', 'Paid'
        REFUNDED = 'refunded', 'Refunded'

    class OrderStatus(models.TextChoices):
        NEW = 'new', 'New'
        CONFIRMED = 'confirmed', 'Confirmed'
        IN_DESIGN = 'in_design', 'In Design'
        IN_PRODUCTION = 'in_production', 'In Production'
        READY = 'ready', 'Ready'
        DISPATCHED = 'dispatched', 'Dispatched'
        DELIVERED = 'delivered', 'Delivered'
        DELAYED = 'delayed', 'Delayed'
        CANCELLED = 'cancelled', 'Cancelled'

    code = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders')
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.ONLINE)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    status = models.CharField(max_length=30, choices=OrderStatus.choices, default=OrderStatus.NEW)
    payment_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=10, default='NGN')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    has_been_messaged = models.BooleanField(default=False)
    last_messaged_at = models.DateTimeField(null=True, blank=True)
    internal_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.balance_due = max(Decimal('0.00'), self.total_amount - self.amount_paid)
        if self.payment_status == self.PaymentStatus.PAID and not self.payment_date:
            self.payment_date = timezone.now()
        super().save(*args, **kwargs)


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * Decimal(self.quantity)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.order.code} - {self.title}'


class MessageTemplate(TimeStampedModel):
    class Stage(models.TextChoices):
        NEW_ORDER = 'new_order', 'New Order'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Payment Confirmed'
        DELAY_NOTICE = 'delay_notice', 'Delay Notice'
        READY_FOR_DELIVERY = 'ready_for_delivery', 'Ready for Delivery'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        POST_DELIVERY = 'post_delivery', 'Post-delivery Follow-up'
        CUSTOM = 'custom', 'Custom'

    name = models.CharField(max_length=120)
    stage = models.CharField(max_length=30, choices=Stage.choices, default=Stage.CUSTOM)
    body = models.TextField(help_text='Use placeholders like {{customer_name}}, {{order_code}}, {{amount}}')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['stage', 'name']

    def __str__(self):
        return f'{self.name} ({self.stage})'


class OrderMessageLog(TimeStampedModel):
    class Channel(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        SMS = 'sms', 'SMS'
        EMAIL = 'email', 'Email'
        CALL = 'call', 'Call'
        OTHER = 'other', 'Other'

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='message_logs')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='message_logs')
    template = models.ForeignKey(MessageTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='message_logs')
    stage = models.CharField(max_length=30, blank=True)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WHATSAPP)
    message_body = models.TextField()
    sent_by = models.CharField(max_length=120, blank=True)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-sent_at']


class Announcement(TimeStampedModel):
    title = models.CharField(max_length=180)
    message = models.TextField()
    cta_text = models.CharField(max_length=80, blank=True)
    cta_url = models.URLField(max_length=1000, blank=True)
    is_active = models.BooleanField(default=False)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Job(TimeStampedModel):
    class JobStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        READY_FOR_PICKUP = 'ready_for_pickup', 'Ready for Pickup'
        AWAITING_DELIVERY = 'awaiting_delivery', 'Awaiting Delivery'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PARTIAL = 'partial', 'Partially Paid'
        PAID = 'paid', 'Paid'

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='jobs')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs_updated')
    job_type = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    deadline = models.DateTimeField(null=True, blank=True)
    special_instructions = models.TextField(blank=True)
    project_scope_note = models.TextField(blank=True)
    status = models.CharField(max_length=25, choices=JobStatus.choices, default=JobStatus.PENDING)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['deadline', '-created_at']

    def save(self, *args, **kwargs):
        self.total = Decimal(self.quantity) * self.unit_price
        self.balance_due = max(Decimal('0.00'), self.total - self.amount_paid)
        if self.balance_due == Decimal('0.00'):
            self.payment_status = self.PaymentStatus.PAID
        elif self.amount_paid > Decimal('0.00'):
            self.payment_status = self.PaymentStatus.PARTIAL
        else:
            self.payment_status = self.PaymentStatus.UNPAID
        super().save(*args, **kwargs)

    def __str__(self):
        return f'JOB-{self.id} {self.job_type}'


class JobAttachment(TimeStampedModel):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='job_attachments/%Y/%m/%d/')
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.original_name or self.file.name


class JobStatusHistory(TimeStampedModel):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=25, blank=True)
    to_status = models.CharField(max_length=25)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class PaymentRecord(TimeStampedModel):
    class PaymentSource(models.TextChoices):
        JOB = 'job', 'Job'
        WALK_IN = 'walk_in', 'Walk-in Service'

    job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source = models.CharField(max_length=20, choices=PaymentSource.choices, default=PaymentSource.JOB)
    service_label = models.CharField(max_length=180, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    edit_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']


class SystemSetting(TimeStampedModel):
    business_name = models.CharField(max_length=180, default='Bilta Print Shop')
    business_address = models.TextField(blank=True)
    photocopy_price_per_copy = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('50.00'))
    job_categories = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-updated_at', '-id']

    def __str__(self):
        return self.business_name


class PhotocopySession(TimeStampedModel):
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='photocopy_sessions')
    opening_reading = models.PositiveIntegerField()
    closing_reading = models.PositiveIntegerField()
    total_copies = models.PositiveIntegerField(default=0)
    price_per_copy = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    expected_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    actual_cash_collected = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    revenue_gap = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    has_discrepancy = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.total_copies = max(0, self.closing_reading - self.opening_reading)
        self.expected_revenue = Decimal(self.total_copies) * self.price_per_copy
        self.revenue_gap = self.actual_cash_collected - self.expected_revenue
        self.has_discrepancy = self.revenue_gap != Decimal('0.00')
        super().save(*args, **kwargs)


class AuditLog(TimeStampedModel):
    action = models.CharField(max_length=80)
    model_name = models.CharField(max_length=80)
    object_id = models.CharField(max_length=64, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']


class StaffInvitation(TimeStampedModel):
    class Role(models.TextChoices):
        STAFF = 'staff', 'Staff'
        OWNER = 'owner', 'Owner/Admin'

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    token = models.CharField(max_length=96, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_invitations_sent',
    )
    accepted_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_staff_invitations',
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=default_staff_invitation_expiry)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} ({self.role})'

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = default_staff_invitation_expiry()
        self.email = (self.email or '').strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_pending(self):
        return not self.accepted_at and self.expires_at > timezone.now()
