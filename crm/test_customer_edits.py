from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase
from .models import Customer, AuditLog


class CustomerEditTests(APITestCase):
    def test_only_admin_edits_customer_and_can_clear_or_restore_follow_up(self):
        user = get_user_model()
        owner = user.objects.create_user('edit_owner', is_superuser=True, is_staff=True)
        staff = user.objects.create_user('edit_staff', is_staff=True)
        customer = Customer.objects.create(full_name='Customer', phone='08011111111', follow_up_flag=True)
        url = f'/api/customers/{customer.pk}/'
        client = APIClient()
        client.force_authenticate(staff)
        self.assertEqual(client.patch(url, {'full_name': 'Changed', 'follow_up_flag': False}, format='json').status_code, 403)
        customer.refresh_from_db()
        self.assertEqual(customer.full_name, 'Customer')
        self.assertTrue(customer.follow_up_flag)
        client.force_authenticate(owner)
        payload = {'full_name': 'Corrected name', 'phone': '08022222222', 'email': 'correct@example.com', 'city': 'Lagos', 'business_name': 'Correct business', 'customer_type': 'premium', 'contact_preference': 'whatsapp', 'notes': 'Contacted customer', 'follow_up_flag': False}
        result = client.patch(url, payload, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        customer.refresh_from_db()
        for key, value in payload.items():
            self.assertEqual(getattr(customer, key), value)
        self.assertTrue(AuditLog.objects.filter(model_name='Customer', object_id=str(customer.pk), performed_by=owner, action='update').exists())
        self.assertEqual(client.patch(url, {'follow_up_flag': True}, format='json').status_code, 200)
        customer.refresh_from_db()
        self.assertTrue(customer.follow_up_flag)
        self.assertEqual(Customer.objects.count(), 1)
