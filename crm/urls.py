from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnnouncementViewSet,
    AuditLogViewSet,
    CustomerViewSet,
    JobViewSet,
    MessageTemplateViewSet,
    OrderMessageLogViewSet,
    OrderViewSet,
    PaymentRecordViewSet,
    PhotocopySessionViewSet,
    ProductViewSet,
    StaffAccountViewSet,
    StaffInvitationViewSet,
    SystemSettingViewSet,
    auth_login,
    auth_logout,
    auth_me,
    daily_summary,
    health_check,
    job_attachment_download,
    public_checkout_request,
    public_design_request,
    staff_invitation_accept,
    staff_invitation_detail,
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'jobs', JobViewSet, basename='job')
router.register(r'payments', PaymentRecordViewSet, basename='payment')
router.register(r'photocopy-sessions', PhotocopySessionViewSet, basename='photocopy-session')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
router.register(r'staff-accounts', StaffAccountViewSet, basename='staff-account')
router.register(r'staff-invitations', StaffInvitationViewSet, basename='staff-invitation')
router.register(r'settings', SystemSettingViewSet, basename='system-setting')
router.register(r'message-templates', MessageTemplateViewSet, basename='message-template')
router.register(r'order-message-logs', OrderMessageLogViewSet, basename='order-message-log')
router.register(r'announcements', AnnouncementViewSet, basename='announcement')

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('job-attachments/<int:pk>/download/', job_attachment_download, name='job-attachment-download'),
    path('auth/login/', auth_login, name='auth-login'),
    path('auth/logout/', auth_logout, name='auth-logout'),
    path('auth/me/', auth_me, name='auth-me'),
    path('auth/invitations/accept/', staff_invitation_accept, name='staff-invitation-accept'),
    path('auth/invitations/<str:token>/', staff_invitation_detail, name='staff-invitation-detail'),
    path('public/order-requests/checkout/', public_checkout_request, name='public-checkout-request'),
    path('public/order-requests/design/', public_design_request, name='public-design-request'),
    path('reports/daily-summary/', daily_summary, name='daily-summary'),
    path('', include(router.urls)),
]
