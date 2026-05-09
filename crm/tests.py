import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from .models import AuditLog, Customer, Job, JobAttachment, Order, PaymentRecord, PhotocopySession

User = get_user_model()


class ApiSmokeTests(APITestCase):
    def setUp(self):
        self.owner_password = 'StrongPass!234'
        self.staff_password = 'StrongPass!234'

        self.owner = User.objects.create_user(
            username='api_owner',
            email='api-owner@example.com',
            password=self.owner_password,
            is_staff=True,
            is_superuser=True,
            is_active=True,
            first_name='API',
            last_name='Owner',
        )
        self.staff = User.objects.create_user(
            username='api_staff',
            email='api-staff@example.com',
            password=self.staff_password,
            is_staff=True,
            is_superuser=False,
            is_active=True,
            first_name='API',
            last_name='Staff',
        )

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)

        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff)

        self.customer = Customer.objects.create(
            full_name='API Customer',
            phone='08001234567',
            email='customer@example.com',
            city='Lagos',
            business_name='API Business',
            customer_type='recurring',
            contact_preference='phone',
            notes='Customer for API smoke tests',
            follow_up_flag=True,
        )

        self.product_payload = {
            'slug': 'api-product',
            'category': 'BUSINESS CARDS',
            'title': 'API Product',
            'description': 'API smoke product',
            'details': 'API smoke product details',
            'price': '12000',
            'image': 'https://example.com/product.jpg',
            'images': ['https://example.com/product.jpg'],
            'size_options': [],
            'is_active': True,
        }

    def create_product(self):
        response = self.owner_client.post('/api/products/', self.product_payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_order(self):
        payload = {
            'code': 'API-ORDER-001',
            'customer': self.customer.id,
            'source': 'online',
            'payment_status': 'unpaid',
            'status': 'new',
            'currency': 'NGN',
            'subtotal': '12000.00',
            'discount_amount': '0.00',
            'total_amount': '12000.00',
            'amount_paid': '0.00',
            'internal_notes': 'API order note',
        }
        response = self.client.post('/api/orders/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_job(self):
        payload = {
            'customer': self.customer.id,
            'job_type': 'printing',
            'description': 'API smoke job',
            'quantity': 2,
            'unit_price': '5000.00',
            'deadline': timezone.now().isoformat(),
            'special_instructions': 'None',
            'project_scope_note': 'API scope',
        }
        response = self.staff_client.post('/api/jobs/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_payment(self):
        payload = {
            'amount': '2500.00',
            'source': 'walk_in',
            'service_label': 'Quick print',
            'note': 'API payment',
        }
        response = self.staff_client.post('/api/payments/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_photocopy_session(self):
        payload = {
            'opening_reading': 100,
            'closing_reading': 140,
            'price_per_copy': '50.00',
            'actual_cash_collected': '2000.00',
        }
        response = self.staff_client.post('/api/photocopy-sessions/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_setting(self):
        payload = {
            'business_name': 'API Setting',
            'business_address': '123 Test Street',
            'photocopy_price_per_copy': '55.00',
            'job_categories': ['printing', 'binding'],
        }
        response = self.owner_client.post('/api/settings/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_message_template(self):
        payload = {
            'name': 'API Template',
            'stage': 'custom',
            'body': 'Hello {{customer_name}}',
            'is_active': True,
        }
        response = self.owner_client.post('/api/message-templates/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_order_message_log(self, order_id, template_id):
        payload = {
            'order': order_id,
            'customer': self.customer.id,
            'template': template_id,
            'stage': 'custom',
            'channel': 'whatsapp',
            'message_body': 'API log message',
            'sent_by': self.owner.username,
        }
        response = self.owner_client.post('/api/order-message-logs/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_announcement(self):
        payload = {
            'title': 'API Announcement',
            'message': 'API smoke announcement',
            'cta_text': 'View',
            'cta_url': 'https://example.com',
            'is_active': True,
        }
        response = self.owner_client.post('/api/announcements/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def create_staff_invitation(self):
        payload = {
            'first_name': 'Invite',
            'last_name': 'User',
            'email': 'invite@example.com',
            'role': 'staff',
        }
        response = self.owner_client.post('/api/staff-invitations/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_public_submission_endpoints(self):
        checkout_file = SimpleUploadedFile(
            'card-front.pdf',
            b'%PDF-1.4 mock print file',
            content_type='application/pdf',
        )
        checkout_payload = {
            'payload': json.dumps({
                'first_name': 'Public',
                'last_name': 'Customer',
                'country': 'Nigeria',
                'street_address': '12 Broad Street, Lagos',
                'phone': '08030000000',
                'email': 'public-customer@example.com',
                'additional_note': 'Please call before delivery.',
                'items': [
                    {
                        'slug': 'public-business-card',
                        'title': 'Business Cards',
                        'price': '12000',
                        'quantity': 2,
                        'requestMode': 'upload',
                        'specificationSummary': 'Standard print',
                        'uploadedDesignNames': ['card-front.pdf'],
                    }
                ],
            }),
            'files': [checkout_file],
        }
        checkout_response = self.client.post(
            '/api/public/order-requests/checkout/',
            checkout_payload,
            format='multipart',
        )
        self.assertEqual(checkout_response.status_code, 201, checkout_response.data)
        checkout_job = Job.objects.get(id=checkout_response.data['job_id'])
        self.assertEqual(checkout_job.job_type, 'printing')
        self.assertIn('Website order', checkout_job.description)
        self.assertIn('card-front.pdf', checkout_job.project_scope_note)
        self.assertEqual(checkout_job.attachments.count(), 1)

        design_file = SimpleUploadedFile(
            'logo.png',
            b'\x89PNG\r\nmock-logo',
            content_type='image/png',
        )
        design_payload = {
            'payload': json.dumps({
                'product_slug': 'one-sided-business-cards',
                'product_title': 'One-sided Business Cards',
                'quantity': 1,
                'full_name': 'Design Customer',
                'phone': '08031111111',
                'email': 'design-customer@example.com',
                'request_details': 'Use navy and yellow with a clean layout.',
                'uploaded_design_names': ['logo.png'],
                'no_logo': False,
            }),
            'files': [design_file],
        }
        design_response = self.client.post(
            '/api/public/order-requests/design/',
            design_payload,
            format='multipart',
        )
        self.assertEqual(design_response.status_code, 201, design_response.data)
        design_job = Job.objects.get(id=design_response.data['job_id'])
        self.assertEqual(design_job.job_type, 'design')
        self.assertIn('Website design request', design_job.description)
        self.assertIn('Use navy and yellow', design_job.project_scope_note)
        self.assertEqual(design_job.attachments.count(), 1)

        attachment = JobAttachment.objects.filter(job=design_job).first()
        self.assertIsNotNone(attachment)
        download_response = self.client.get(f'/api/job-attachments/{attachment.id}/download/')
        self.assertEqual(download_response.status_code, 200)

    def test_auth_endpoints(self):
        response = self.client.post(
            '/api/auth/login/',
            {'username': self.owner.username, 'password': self.owner_password},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        token = response.data['token']

        token_client = APIClient()
        token_client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

        me_response = token_client.get('/api/auth/me/')
        self.assertEqual(me_response.status_code, 200, me_response.data)
        self.assertEqual(me_response.data['username'], self.owner.username)

        logout_response = token_client.post('/api/auth/logout/')
        self.assertEqual(logout_response.status_code, 200, logout_response.data)
        self.assertFalse(Token.objects.filter(user=self.owner).exists())

    def test_product_and_customer_endpoints(self):
        product = self.create_product()
        product_list = self.client.get('/api/products/')
        self.assertEqual(product_list.status_code, 200)
        product_detail = self.client.get(f"/api/products/{product['id']}/")
        self.assertEqual(product_detail.status_code, 200)

        customer_payload = {
            'full_name': 'Created API Customer',
            'phone': '08007654321',
            'email': 'created-customer@example.com',
            'city': 'Lagos',
            'business_name': 'Created Business',
            'customer_type': 'recurring',
            'contact_preference': 'phone',
            'notes': 'Created by smoke test',
            'follow_up_flag': False,
        }
        customer_create = self.staff_client.post('/api/customers/', customer_payload, format='json')
        self.assertEqual(customer_create.status_code, 201, customer_create.data)

        customer_list = self.staff_client.get('/api/customers/')
        self.assertEqual(customer_list.status_code, 200)
        customer_detail = self.staff_client.get(f"/api/customers/{customer_create.data['id']}/")
        self.assertEqual(customer_detail.status_code, 200)

    def test_order_job_payment_and_reporting_endpoints(self):
        order = self.create_order()
        job = self.create_job()
        payment = self.create_payment()
        session = self.create_photocopy_session()

        self.assertEqual(self.client.get('/api/orders/').status_code, 200)
        self.assertEqual(self.client.get(f"/api/orders/{order['id']}/").status_code, 200)
        self.assertEqual(self.client.get('/api/orders/monthly_report/').status_code, 200)

        self.assertEqual(self.staff_client.get('/api/jobs/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/jobs/{job['id']}/").status_code, 200)
        self.assertEqual(self.staff_client.get('/api/jobs/queue/').status_code, 200)

        self.assertEqual(self.staff_client.get('/api/payments/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/payments/{payment['id']}/").status_code, 200)

        self.assertEqual(self.staff_client.get('/api/photocopy-sessions/').status_code, 200)
        self.assertEqual(
            self.staff_client.get(f"/api/photocopy-sessions/{session['id']}/").status_code,
            200,
        )

        daily_summary = self.staff_client.get('/api/reports/daily-summary/')
        self.assertEqual(daily_summary.status_code, 200, daily_summary.data)

    def test_owner_management_endpoints(self):
        setting = self.create_setting()
        template = self.create_message_template()
        order = self.create_order()
        message_log = self.create_order_message_log(order['id'], template['id'])
        announcement = self.create_announcement()
        invitation = self.create_staff_invitation()

        self.assertEqual(self.staff_client.get('/api/settings/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/settings/{setting['id']}/").status_code, 200)

        self.assertEqual(self.client.get('/api/message-templates/').status_code, 200)
        self.assertEqual(self.client.get(f"/api/message-templates/{template['id']}/").status_code, 200)

        self.assertEqual(self.client.get('/api/order-message-logs/').status_code, 200)
        self.assertEqual(self.client.get(f"/api/order-message-logs/{message_log['id']}/").status_code, 200)

        self.assertEqual(self.client.get('/api/announcements/').status_code, 200)
        self.assertEqual(self.client.get(f"/api/announcements/{announcement['id']}/").status_code, 200)
        self.assertEqual(self.client.get('/api/announcements/active/').status_code, 200)

        self.assertEqual(self.owner_client.get('/api/staff-invitations/').status_code, 200)
        self.assertEqual(
            self.owner_client.get(f"/api/staff-invitations/{invitation['id']}/").status_code,
            200,
        )

        invitation_detail = self.client.get(f"/api/auth/invitations/{invitation['token']}/")
        self.assertEqual(invitation_detail.status_code, 200, invitation_detail.data)

        accept_response = self.client.post(
            '/api/auth/invitations/accept/',
            {
                'token': invitation['token'],
                'username': 'accepted_user',
                'password': 'StrongPass!234',
            },
            format='json',
        )
        self.assertEqual(accept_response.status_code, 200, accept_response.data)

        self.assertEqual(self.owner_client.get('/api/staff-accounts/').status_code, 200)
        self.assertEqual(self.owner_client.get(f'/api/staff-accounts/{self.staff.id}/').status_code, 200)

        reset_response = self.owner_client.post(
            f'/api/staff-accounts/{self.staff.id}/reset-password/',
            {'new_password': 'NewStrongPass!234'},
            format='json',
        )
        self.assertEqual(reset_response.status_code, 200, reset_response.data)

        audit_list = self.owner_client.get('/api/audit-logs/')
        self.assertEqual(audit_list.status_code, 200)
        audit_log = AuditLog.objects.order_by('-id').first()
        self.assertIsNotNone(audit_log)
        audit_detail = self.owner_client.get(f'/api/audit-logs/{audit_log.id}/')
        self.assertEqual(audit_detail.status_code, 200)
