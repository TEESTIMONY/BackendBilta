import json
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from .models import AuditLog, Customer, Job, JobAttachment, Order, PaymentRecord, PhotocopySession

User = get_user_model()


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='bilta-test-media-')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ApiSmokeTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

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
        response = self.staff_client.post('/api/orders/', payload, format='json')
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
        unsigned_response = self.client.get(f'/api/job-attachments/{attachment.id}/download/')
        self.assertEqual(unsigned_response.status_code, 403)

        job_detail = self.staff_client.get(f'/api/jobs/{design_job.id}/')
        signed_url = job_detail.data['attachments'][0]['download_url']
        download_response = self.client.get(signed_url)
        self.assertEqual(download_response.status_code, 200)

        other_attachment = JobAttachment.objects.get(job=checkout_job)
        forged_url = signed_url.replace(
            f'/job-attachments/{attachment.id}/', f'/job-attachments/{other_attachment.id}/'
        )
        self.assertEqual(self.client.get(forged_url).status_code, 403)

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

        self.assertEqual(self.staff_client.get('/api/orders/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/orders/{order['id']}/").status_code, 200)
        self.assertEqual(self.staff_client.get('/api/orders/monthly_report/').status_code, 200)

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

    def test_job_queue_keeps_completed_jobs_available_but_hides_cancelled_jobs(self):
        completed_job = Job.objects.create(
            customer=self.customer,
            created_by=self.staff,
            updated_by=self.staff,
            job_type='printing',
            description='Completed with outstanding payment',
            quantity=1,
            unit_price='1000.00',
            amount_paid='400.00',
            status=Job.JobStatus.COMPLETED,
        )
        cancelled_job = Job.objects.create(
            customer=self.customer,
            created_by=self.staff,
            updated_by=self.staff,
            job_type='binding',
            description='Cancelled job should stay hidden',
            quantity=1,
            unit_price='500.00',
            amount_paid='0.00',
            status=Job.JobStatus.CANCELLED,
        )

        response = self.staff_client.get('/api/jobs/queue/')
        self.assertEqual(response.status_code, 200, response.data)

        returned_ids = {row['id'] for row in response.data}
        self.assertIn(completed_job.id, returned_ids)
        self.assertNotIn(cancelled_job.id, returned_ids)

    def test_owner_management_endpoints(self):
        setting = self.create_setting()
        template = self.create_message_template()
        order = self.create_order()
        message_log = self.create_order_message_log(order['id'], template['id'])
        announcement = self.create_announcement()
        invitation = self.create_staff_invitation()

        self.assertEqual(self.staff_client.get('/api/settings/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/settings/{setting['id']}/").status_code, 200)

        self.assertEqual(self.staff_client.get('/api/message-templates/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/message-templates/{template['id']}/").status_code, 200)

        self.assertEqual(self.staff_client.get('/api/order-message-logs/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/order-message-logs/{message_log['id']}/").status_code, 200)

        self.assertEqual(self.staff_client.get('/api/announcements/').status_code, 200)
        self.assertEqual(self.staff_client.get(f"/api/announcements/{announcement['id']}/").status_code, 200)
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

    def test_internal_endpoints_reject_anonymous_users(self):
        order = self.create_order()
        template = self.create_message_template()
        self.create_announcement()

        for url in (
            '/api/orders/',
            f"/api/orders/{order['id']}/",
            '/api/orders/monthly_report/',
            '/api/message-templates/',
            f"/api/message-templates/{template['id']}/",
            '/api/order-message-logs/',
            '/api/announcements/',
            '/api/customers/',
            '/api/jobs/',
        ):
            self.assertIn(self.client.get(url).status_code, (401, 403), url)

        self.assertIn(
            self.client.delete(f"/api/orders/{order['id']}/").status_code, (401, 403)
        )
        self.assertIn(
            self.client.post('/api/announcements/', {'title': 'x', 'message': 'y'}, format='json').status_code,
            (401, 403),
        )
        self.assertTrue(Order.objects.filter(id=order['id']).exists())

    def test_public_submission_does_not_overwrite_existing_customer(self):
        payload = {
            'first_name': 'Someone',
            'last_name': 'Else',
            'country': 'Nigeria',
            'street_address': '1 Other Street',
            'phone': '08099999999',
            'email': self.customer.email,
            'items': [{'title': 'Flyers', 'price': 'Price on request', 'quantity': 1}],
        }
        response = self.client.post('/api/public/order-requests/checkout/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.full_name, 'API Customer')
        self.assertEqual(self.customer.phone, '08001234567')

        job = Job.objects.get(id=response.data['job_id'])
        self.assertEqual(job.customer_id, self.customer.id)
        self.assertIn('Someone Else', job.special_instructions)
        self.assertIn('08099999999', job.special_instructions)
        # Unpriced requests must not be reported as paid.
        self.assertEqual(job.payment_status, Job.PaymentStatus.UNPAID)

    def test_checkout_total_matches_item_subtotal(self):
        payload = {
            'first_name': 'Sum',
            'last_name': 'Check',
            'country': 'Nigeria',
            'street_address': '2 Street',
            'phone': '08077777777',
            'email': 'sum-check@example.com',
            'items': [
                {'title': 'Cards', 'price': '₦10,000', 'quantity': 1},
                {'title': 'Flyers', 'price': '₦5,000', 'quantity': 2},
            ],
        }
        response = self.client.post('/api/public/order-requests/checkout/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        job = Job.objects.get(id=response.data['job_id'])
        self.assertEqual(job.total, Decimal('20000.00'))

    def test_payment_edit_and_delete_keep_job_balance_in_sync(self):
        job = Job.objects.create(
            customer=self.customer, job_type='printing', quantity=1, unit_price=Decimal('1000.00')
        )
        created = self.staff_client.post(
            '/api/payments/', {'job': job.id, 'amount': '300.00', 'source': 'job'}, format='json'
        )
        self.assertEqual(created.status_code, 201, created.data)
        job.refresh_from_db()
        self.assertEqual(job.amount_paid, Decimal('300.00'))

        updated = self.staff_client.patch(
            f"/api/payments/{created.data['id']}/",
            {'amount': '1000.00', 'edit_reason': 'Typo'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        job.refresh_from_db()
        self.assertEqual(job.amount_paid, Decimal('1000.00'))
        self.assertEqual(job.payment_status, Job.PaymentStatus.PAID)

        deleted = self.owner_client.delete(f"/api/payments/{created.data['id']}/")
        self.assertEqual(deleted.status_code, 204)
        job.refresh_from_db()
        self.assertEqual(job.amount_paid, Decimal('0.00'))
        self.assertEqual(job.payment_status, Job.PaymentStatus.UNPAID)

    def test_daily_summary_rejects_bad_date(self):
        response = self.staff_client.get('/api/reports/daily-summary/?date=not-a-date')
        self.assertEqual(response.status_code, 400)

    def test_login_is_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        statuses = [
            self.client.post(
                '/api/auth/login/', {'username': self.owner.username, 'password': 'wrong'}, format='json'
            ).status_code
            for _ in range(11)
        ]
        cache.clear()
        self.assertEqual(statuses[:10], [400] * 10)
        self.assertEqual(statuses[10], 429)

    def test_queue_only_shows_todays_jobs_and_records_filter_by_day(self):
        today_job = Job.objects.create(customer=self.customer, job_type='printing', quantity=1)
        old_job = Job.objects.create(customer=self.customer, job_type='binding', quantity=1)
        yesterday = timezone.localdate() - timedelta(days=1)
        Job.objects.filter(id=old_job.id).update(created_at=timezone.now() - timedelta(days=1))

        queue_ids = {row['id'] for row in self.staff_client.get('/api/jobs/queue/').data}
        self.assertIn(today_job.id, queue_ids)
        self.assertNotIn(old_job.id, queue_ids)

        yesterday_queue = self.staff_client.get(f'/api/jobs/queue/?date={yesterday}')
        self.assertEqual({row['id'] for row in yesterday_queue.data}, {old_job.id})

        records = self.staff_client.get(f'/api/jobs/?created_on={yesterday}')
        self.assertEqual(records.status_code, 200, records.data)
        self.assertEqual({row['id'] for row in records.data['results']}, {old_job.id})

        self.assertEqual(self.staff_client.get('/api/jobs/?created_on=bad').status_code, 400)
        self.assertEqual(self.staff_client.get('/api/jobs/queue/?date=bad').status_code, 400)
