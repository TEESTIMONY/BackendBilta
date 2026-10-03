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

        job_detail = self.owner_client.get(f'/api/jobs/{design_job.id}/')
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
        self.owner.refresh_from_db()
        self.assertIsNotNone(self.owner.last_login)

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
            customer=self.customer, job_type='printing', quantity=1, unit_price=Decimal('1000.00'), created_by=self.staff
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
        today_job = Job.objects.create(customer=self.customer, job_type='printing', quantity=1, created_by=self.staff)
        old_job = Job.objects.create(customer=self.customer, job_type='binding', quantity=1, created_by=self.staff)
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

    def test_pending_job_moves_to_records_after_its_day_and_stays_unpaid(self):
        created = self.staff_client.post(
            '/api/jobs/',
            {
                'customer': self.customer.id,
                'job_type': 'printing',
                'description': 'Pending job left at end of day',
                'quantity': 2,
                'unit_price': '1500.00',
                'status': 'pending',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        job_id = created.data['id']
        self.assertEqual(created.data['payment_status'], Job.PaymentStatus.UNPAID)

        queue_ids = {row['id'] for row in self.staff_client.get('/api/jobs/queue/').data}
        self.assertIn(job_id, queue_ids)

        # Midnight passes: the job now belongs to yesterday.
        Job.objects.filter(id=job_id).update(created_at=timezone.now() - timedelta(days=1))
        yesterday = timezone.localdate() - timedelta(days=1)

        queue_ids = {row['id'] for row in self.staff_client.get('/api/jobs/queue/').data}
        self.assertNotIn(job_id, queue_ids)

        records = self.staff_client.get(f'/api/jobs/?created_on={yesterday}').data['results']
        record = next(row for row in records if row['id'] == job_id)
        self.assertEqual(record['status'], Job.JobStatus.PENDING)
        self.assertEqual(record['payment_status'], Job.PaymentStatus.UNPAID)
        self.assertEqual(Decimal(record['amount_paid']), Decimal('0.00'))
        self.assertEqual(Decimal(record['balance_due']), Decimal('3000.00'))

    def test_jobs_are_only_marked_paid_when_payment_is_recorded(self):
        def create(**overrides):
            payload = {
                'customer': self.customer.id,
                'job_type': 'printing',
                'description': 'Payment status check',
                'quantity': 1,
                'unit_price': '1000.00',
                'status': 'pending',
                **overrides,
            }
            response = self.staff_client.post('/api/jobs/', payload, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            return Job.objects.get(id=response.data['id'])

        self.assertEqual(create().payment_status, Job.PaymentStatus.UNPAID)
        self.assertEqual(create(unit_price='0.00').payment_status, Job.PaymentStatus.UNPAID)
        self.assertEqual(create(amount_paid='400.00').payment_status, Job.PaymentStatus.PARTIAL)
        self.assertEqual(create(amount_paid='1000.00').payment_status, Job.PaymentStatus.PAID)

        # Clients cannot set payment_status directly.
        forced = create(payment_status='paid')
        self.assertEqual(forced.payment_status, Job.PaymentStatus.UNPAID)

        # Completing, or moving through any status, does not mark a job paid.
        job = create()
        for status in ('in_progress', 'ready_for_pickup', 'completed'):
            response = self.staff_client.patch(f'/api/jobs/{job.id}/', {'status': status}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            job.refresh_from_db()
            self.assertEqual(job.payment_status, Job.PaymentStatus.UNPAID, status)

        # Only recorded payments change it.
        self.staff_client.post('/api/payments/', {'job': job.id, 'amount': '600.00', 'source': 'job'}, format='json')
        job.refresh_from_db()
        self.assertEqual(job.payment_status, Job.PaymentStatus.PARTIAL)
        self.staff_client.post('/api/payments/', {'job': job.id, 'amount': '400.00', 'source': 'job'}, format='json')
        job.refresh_from_db()
        self.assertEqual(job.payment_status, Job.PaymentStatus.PAID)

        # Website requests start unpaid, priced or not.
        design = self.client.post(
            '/api/public/order-requests/design/',
            {
                'product_title': 'Business Cards',
                'quantity': 1,
                'full_name': 'Web Visitor',
                'phone': '08012121212',
                'email': 'web-visitor@example.com',
                'request_details': 'Simple design',
                'no_logo': True,
            },
            format='json',
        )
        self.assertEqual(design.status_code, 201, design.data)
        self.assertEqual(Job.objects.get(id=design.data['job_id']).payment_status, Job.PaymentStatus.UNPAID)

        checkout = self.client.post(
            '/api/public/order-requests/checkout/',
            {
                'first_name': 'Web',
                'last_name': 'Buyer',
                'country': 'Nigeria',
                'street_address': '3 Street',
                'phone': '08013131313',
                'email': 'web-buyer@example.com',
                'items': [{'title': 'Flyers', 'price': '\u20a65,000', 'quantity': 2}],
            },
            format='json',
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        self.assertEqual(Job.objects.get(id=checkout.data['job_id']).payment_status, Job.PaymentStatus.UNPAID)

    def test_amount_paid_on_a_job_is_backed_by_payment_records(self):
        def job_payments(job_id):
            return list(PaymentRecord.objects.filter(job_id=job_id).order_by('id'))

        # Nothing paid: no payment entry, job unpaid.
        unpaid = self.staff_client.post(
            '/api/jobs/',
            {'customer': self.customer.id, 'job_type': 'printing', 'quantity': 1, 'unit_price': '1000.00'},
            format='json',
        )
        self.assertEqual(job_payments(unpaid.data['id']), [])

        # "Amount paid now" at creation: one payment entry recorded by that staff member.
        created = self.staff_client.post(
            '/api/jobs/',
            {
                'customer': self.customer.id,
                'job_type': 'printing',
                'quantity': 1,
                'unit_price': '1000.00',
                'amount_paid': '400.00',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        job_id = created.data['id']
        payments = job_payments(job_id)
        self.assertEqual([p.amount for p in payments], [Decimal('400.00')])
        self.assertEqual(payments[0].recorded_by, self.staff)

        # Owner corrections are logged as adjustments, so the entries always sum to amount_paid.
        self.owner_client.patch(f'/api/jobs/{job_id}/', {'amount_paid': '1000.00'}, format='json')
        self.owner_client.patch(f'/api/jobs/{job_id}/', {'amount_paid': '700.00'}, format='json')
        payments = job_payments(job_id)
        self.assertEqual([p.amount for p in payments], [Decimal('400.00'), Decimal('600.00'), Decimal('-300.00')])
        job = Job.objects.get(id=job_id)
        self.assertEqual(sum(p.amount for p in payments), job.amount_paid)
        self.assertEqual(job.payment_status, Job.PaymentStatus.PARTIAL)

        # A status-only update adds nothing.
        self.staff_client.patch(f'/api/jobs/{job_id}/', {'status': 'completed'}, format='json')
        self.assertEqual(len(job_payments(job_id)), 3)

        # Daily revenue now matches what the jobs say was collected.
        summary = self.owner_client.get('/api/reports/daily-summary/').data
        self.assertEqual(Decimal(str(summary['total_revenue'])), job.amount_paid)
        staff_summary = self.staff_client.get('/api/reports/daily-summary/').data
        self.assertEqual(Decimal(str(staff_summary['total_revenue'])), Decimal('400.00'))

    def test_discounted_payment_closes_the_job(self):
        job = Job.objects.create(
            customer=self.customer, job_type='printing', quantity=35, unit_price=Decimal('1000.00'), created_by=self.staff
        )
        self.assertEqual(job.total, Decimal('35000.00'))

        # Staff collect N30,000 against an agreed discounted price of N30,000.
        response = self.staff_client.post(
            '/api/payments/',
            {
                'job': job.id,
                'amount': '30000.00',
                'source': 'job',
                'agreed_total': '30000.00',
                'discount_reason': 'Bulk order discount',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('agreed_total', response.data)

        job.refresh_from_db()
        self.assertEqual(job.total, Decimal('35000.00'))
        self.assertEqual(job.discount_amount, Decimal('5000.00'))
        self.assertEqual(job.discount_reason, 'Bulk order discount')
        self.assertEqual(job.amount_paid, Decimal('30000.00'))
        self.assertEqual(job.balance_due, Decimal('0.00'))
        self.assertEqual(job.payment_status, Job.PaymentStatus.PAID)

        detail = self.staff_client.get(f'/api/jobs/{job.id}/').data
        self.assertEqual(Decimal(detail['amount_due']), Decimal('30000.00'))
        self.assertEqual(Decimal(detail['discount_amount']), Decimal('5000.00'))

        audit = AuditLog.objects.get(action='discount', object_id=str(job.id))
        self.assertEqual(audit.performed_by, self.staff)
        self.assertEqual(audit.reason, 'Bulk order discount')
        self.assertEqual(audit.metadata['discount_amount'], '5000.00')

    def test_discount_limits(self):
        job = Job.objects.create(
            customer=self.customer, job_type='printing', quantity=1, unit_price=Decimal('10000.00'),
            amount_paid=Decimal('4000.00'), created_by=self.staff,
        )

        def pay(**extra):
            return self.staff_client.post(
                '/api/payments/', {'job': job.id, 'amount': '1000.00', 'source': 'job', **extra}, format='json'
            )

        self.assertEqual(pay(agreed_total='12000.00').status_code, 400)  # above the job total
        self.assertEqual(pay(agreed_total='3000.00').status_code, 400)  # below what was already paid
        self.assertEqual(
            self.staff_client.post(
                '/api/payments/', {'amount': '500.00', 'source': 'walk_in', 'agreed_total': '400.00'}, format='json'
            ).status_code,
            400,
        )  # no job to discount

        # Discounts can't be set by editing the job directly.
        self.owner_client.patch(f'/api/jobs/{job.id}/', {'discount_amount': '9000.00'}, format='json')
        job.refresh_from_db()
        self.assertEqual(job.discount_amount, Decimal('0.00'))

        # Partial payment with a discount leaves the right balance.
        self.assertEqual(pay(agreed_total='8000.00').status_code, 201)
        job.refresh_from_db()
        self.assertEqual(job.discount_amount, Decimal('2000.00'))
        self.assertEqual(job.amount_paid, Decimal('5000.00'))
        self.assertEqual(job.balance_due, Decimal('3000.00'))
        self.assertEqual(job.payment_status, Job.PaymentStatus.PARTIAL)

        # A plain payment without agreed_total keeps the existing discount.
        self.assertEqual(pay().status_code, 201)
        job.refresh_from_db()
        self.assertEqual(job.discount_amount, Decimal('2000.00'))
        self.assertEqual(job.balance_due, Decimal('2000.00'))

    def test_walk_in_job_with_several_items_and_a_discount(self):
        response = self.staff_client.post(
            '/api/jobs/',
            {
                'customer': self.customer.id,
                'job_type': 'walk_in',
                'fulfilment': 'delivery',
                'items': [
                    {'description': 'A4 flyers, full colour', 'quantity': 50, 'rate': '150.00'},
                    {'description': 'Roll-up banner', 'quantity': 2, 'rate': '25000.00'},
                    {'description': 'Lamination A4', 'quantity': 10, 'rate': '300.00'},
                ],
                'agreed_total': '60000.00',
                'discount_reason': 'Regular customer',
                'amount_paid': '20000.00',
                'special_instructions': 'Deliver to the office',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        job = Job.objects.get(id=response.data['id'])

        self.assertEqual(job.items.count(), 3)
        self.assertEqual(job.total, Decimal('60500.00'))
        self.assertEqual(job.discount_amount, Decimal('500.00'))
        self.assertEqual(job.amount_due, Decimal('60000.00'))
        self.assertEqual(job.balance_due, Decimal('40000.00'))
        self.assertEqual(job.payment_status, Job.PaymentStatus.PARTIAL)
        self.assertEqual(job.fulfilment, 'delivery')
        self.assertIn('Roll-up banner x2', job.description)
        self.assertEqual([i['amount'] for i in response.data['items']], ['7500.00', '50000.00', '3000.00'])

        self.assertEqual(
            [p.amount for p in PaymentRecord.objects.filter(job=job)], [Decimal('20000.00')]
        )
        audit = AuditLog.objects.get(action='discount', object_id=str(job.id))
        self.assertEqual(audit.performed_by, self.staff)
        self.assertEqual(audit.reason, 'Regular customer')

        # Staff can't change the items afterwards; the owner can, and the total follows.
        blocked = self.staff_client.patch(
            f'/api/jobs/{job.id}/', {'items': [{'description': 'x', 'quantity': 1, 'rate': '1.00'}]}, format='json'
        )
        self.assertEqual(blocked.status_code, 400)
        self.owner_client.patch(
            f'/api/jobs/{job.id}/',
            {'items': [{'description': 'A4 flyers, full colour', 'quantity': 100, 'rate': '150.00'}]},
            format='json',
        )
        job.refresh_from_db()
        self.assertEqual(job.total, Decimal('15000.00'))
        self.assertEqual(job.balance_due, Decimal('0.00'))  # 15,000 - 500 discount - 20,000 paid
        self.assertEqual(job.payment_status, Job.PaymentStatus.PAID)

    def test_job_item_and_discount_validation(self):
        def create(**payload):
            return self.staff_client.post(
                '/api/jobs/', {'customer': self.customer.id, 'job_type': 'walk_in', **payload}, format='json'
            )

        self.assertEqual(create(items=[]).status_code, 400)
        self.assertEqual(create(items=[{'description': 'Cards', 'quantity': 0, 'rate': '10.00'}]).status_code, 400)
        self.assertEqual(create(items=[{'description': 'Cards', 'quantity': 1, 'rate': '-5.00'}]).status_code, 400)
        one_item = [{'description': 'Cards', 'quantity': 2, 'rate': '5000.00'}]
        self.assertEqual(create(items=one_item, agreed_total='12000.00').status_code, 400)  # above total
        self.assertEqual(create(items=one_item, agreed_total='4000.00', amount_paid='5000.00').status_code, 400)
        ok = create(items=one_item, agreed_total='9000.00')
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(Job.objects.get(id=ok.data['id']).payment_status, Job.PaymentStatus.UNPAID)

    def test_website_checkout_saves_cart_lines_as_job_items(self):
        response = self.client.post(
            '/api/public/order-requests/checkout/',
            {
                'first_name': 'Item',
                'last_name': 'Buyer',
                'country': 'Nigeria',
                'street_address': '4 Street',
                'phone': '08014141414',
                'email': 'item-buyer@example.com',
                'items': [
                    {'title': 'Business cards', 'price': '\u20a612,000', 'quantity': 1},
                    {'title': 'Flyers', 'price': '\u20a6333', 'quantity': 3},
                    {'title': 'Banner', 'price': 'Price on request', 'quantity': 1},
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        job = Job.objects.get(id=response.data['job_id'])
        self.assertEqual(list(job.items.values_list('description', 'quantity')), [('Business cards', 1), ('Flyers', 3), ('Banner', 1)])
        self.assertEqual(job.total, Decimal('12999.00'))
        self.assertEqual(job.payment_status, Job.PaymentStatus.UNPAID)

    def test_customer_job_count(self):
        for _ in range(2):
            Job.objects.create(customer=self.customer, job_type='printing', quantity=1, unit_price=Decimal('100.00'))
        row = self.staff_client.get(f'/api/customers/{self.customer.id}/').data
        self.assertEqual(row['orders_count'], 2)
        self.assertTrue(row['is_returning_customer'])

    def test_reports_get_detailed_activity_for_one_day(self):
        job = self.staff_client.post(
            '/api/jobs/',
            {
                'customer': self.customer.id,
                'job_type': 'walk_in',
                'items': [{'description': 'Flyers', 'quantity': 10, 'rate': '100.00'}],
            },
            format='json',
        ).data
        self.staff_client.patch(f"/api/jobs/{job['id']}/", {'status': 'completed'}, format='json')
        payment = self.staff_client.post(
            '/api/payments/', {'job': job['id'], 'amount': '600.00', 'source': 'job'}, format='json'
        ).data
        self.owner_client.patch(
            f"/api/payments/{payment['id']}/", {'amount': '700.00', 'edit_reason': 'Miscounted'}, format='json'
        )

        today = timezone.localdate()
        rows = self.owner_client.get(f'/api/audit-logs/?date={today}').data['results']
        by_kind = {(r['model_name'], r['action']): r for r in rows}

        created = by_kind[('Job', 'create')]['metadata']
        self.assertEqual((created['customer_name'], created['total']), ('API Customer', '1000.00'))
        moved = by_kind[('Job', 'update')]['metadata']
        self.assertEqual((moved['status_from'], moved['status_to']), ('pending', 'completed'))
        paid = by_kind[('PaymentRecord', 'create')]['metadata']
        self.assertEqual((paid['amount'], paid['job_id']), ('600.00', job['id']))
        edited = by_kind[('PaymentRecord', 'update')]
        self.assertEqual((edited['metadata']['amount_from'], edited['metadata']['amount'], edited['reason']), ('600.00', '700.00', 'Miscounted'))
        self.assertEqual(by_kind[('Job', 'create')]['performed_by_display'], 'API Staff')

        # Other days are excluded, and bad dates are rejected.
        yesterday = today - timedelta(days=1)
        self.assertEqual(self.owner_client.get(f'/api/audit-logs/?date={yesterday}').data['results'], [])
        self.assertEqual(self.owner_client.get('/api/audit-logs/?date=nope').status_code, 400)
        self.assertEqual(len(self.staff_client.get(f'/api/payments/?date={today}').data['results']), 1)
        self.assertEqual(self.staff_client.get(f'/api/payments/?date={yesterday}').data['results'], [])

    def test_staff_only_see_their_own_jobs_and_money(self):
        other = User.objects.create_user(
            username='other_staff', password='StrongPass!234', is_staff=True, first_name='Other', last_name='Staff'
        )
        other_client = APIClient()
        other_client.force_authenticate(user=other)

        def new_job(client, rate):
            response = client.post(
                '/api/jobs/',
                {
                    'customer': self.customer.id,
                    'job_type': 'walk_in',
                    'items': [{'description': 'Copies', 'quantity': 1, 'rate': rate}],
                    'amount_paid': rate,
                },
                format='json',
            )
            self.assertEqual(response.status_code, 201, response.data)
            return response.data['id']

        mine = new_job(self.staff_client, '1000.00')
        theirs = new_job(other_client, '2500.00')
        website = Job.objects.create(customer=self.customer, job_type='printing', quantity=1, unit_price=Decimal('500.00'))
        other_client.post(
            '/api/photocopy-sessions/',
            {'opening_reading': 0, 'closing_reading': 10, 'price_per_copy': '50.00', 'actual_cash_collected': '500.00'},
            format='json',
        )

        def ids(client, url):
            data = client.get(url).data
            rows = data['results'] if isinstance(data, dict) else data
            return {row['id'] for row in rows}

        # Jobs: list, today's queue, single job and the Records day filter.
        today = timezone.localdate()
        self.assertEqual(ids(self.staff_client, '/api/jobs/'), {mine})
        self.assertEqual(ids(self.staff_client, '/api/jobs/queue/'), {mine})
        self.assertEqual(ids(self.staff_client, f'/api/jobs/?created_on={today}'), {mine})
        self.assertEqual(self.staff_client.get(f'/api/jobs/{theirs}/').status_code, 404)
        self.assertEqual(self.staff_client.get(f'/api/jobs/{website.id}/').status_code, 404)
        self.assertEqual(ids(self.owner_client, '/api/jobs/'), {mine, theirs, website.id})

        # Money: payments, photocopy sessions and the day's totals.
        staff_payments = self.staff_client.get('/api/payments/').data['results']
        self.assertEqual([Decimal(p['amount']) for p in staff_payments], [Decimal('1000.00')])
        self.assertEqual(self.staff_client.get('/api/photocopy-sessions/').data['results'], [])
        staff_day = self.staff_client.get('/api/reports/daily-summary/').data
        self.assertEqual(Decimal(str(staff_day['total_revenue'])), Decimal('1000.00'))
        self.assertEqual(staff_day['jobs_created'], 1)
        self.assertEqual(Decimal(str(staff_day['photocopy_revenue'])), Decimal('0'))
        owner_day = self.owner_client.get('/api/reports/daily-summary/').data
        self.assertEqual(Decimal(str(owner_day['total_revenue'])), Decimal('3500.00'))
        self.assertEqual(owner_day['jobs_created'], 3)

        # Staff can't take payment on someone else's job or a website order; the owner can.
        for job_id in (theirs, website.id):
            refused = self.staff_client.post('/api/payments/', {'job': job_id, 'amount': '100.00', 'source': 'job'}, format='json')
            self.assertEqual(refused.status_code, 400)
        allowed = self.owner_client.post('/api/payments/', {'job': website.id, 'amount': '500.00', 'source': 'job'}, format='json')
        self.assertEqual(allowed.status_code, 201, allowed.data)
