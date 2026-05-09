from django.contrib import admin

from .models import (
    Announcement,
    AuditLog,
    Customer,
    Job,
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


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'price', 'enable_design_upload', 'is_active', 'updated_at')
    list_filter = ('category', 'enable_design_upload', 'is_active')
    search_fields = ('title', 'slug', 'description', 'details')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'email', 'city', 'created_at')
    search_fields = ('full_name', 'phone', 'email', 'city')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('code', 'customer', 'source', 'status', 'payment_status', 'total_amount', 'amount_paid', 'balance_due', 'created_at')
    list_filter = ('source', 'status', 'payment_status')
    search_fields = ('code', 'customer__full_name', 'customer__phone')
    inlines = [OrderItemInline]


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'stage', 'is_active', 'updated_at')
    list_filter = ('stage', 'is_active')
    search_fields = ('name', 'body')


@admin.register(OrderMessageLog)
class OrderMessageLogAdmin(admin.ModelAdmin):
    list_display = ('order', 'customer', 'channel', 'stage', 'sent_at')
    list_filter = ('channel', 'stage')
    search_fields = ('order__code', 'customer__full_name', 'message_body')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'starts_at', 'ends_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'message')


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'job_type', 'status', 'payment_status', 'total', 'amount_paid', 'balance_due', 'deadline')
    list_filter = ('status', 'payment_status', 'job_type')
    search_fields = ('customer__full_name', 'description', 'special_instructions')


@admin.register(JobStatusHistory)
class JobStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('job', 'from_status', 'to_status', 'changed_by', 'created_at')
    list_filter = ('to_status',)
    search_fields = ('job__customer__full_name',)


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'job', 'source', 'amount', 'recorded_by', 'created_at')
    list_filter = ('source',)
    search_fields = ('service_label', 'job__customer__full_name')


@admin.register(PhotocopySession)
class PhotocopySessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'staff', 'opening_reading', 'closing_reading', 'total_copies', 'expected_revenue', 'actual_cash_collected', 'has_discrepancy')
    list_filter = ('has_discrepancy',)
    search_fields = ('staff__username',)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'photocopy_price_per_copy', 'updated_at')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'object_id', 'performed_by', 'created_at')
    list_filter = ('model_name', 'action')
    search_fields = ('model_name', 'action', 'performed_by__username', 'reason')


@admin.register(StaffInvitation)
class StaffInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'invited_by', 'accepted_user', 'accepted_at', 'expires_at')
    list_filter = ('role', 'accepted_at')
    search_fields = ('email', 'first_name', 'last_name', 'token')
