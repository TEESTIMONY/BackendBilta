from datetime import datetime, time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from .models import AuditLog, StaffProfile, StaffDailyRecord

User = get_user_model()


class StaffProfileTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user('profile_owner', is_staff=True, is_superuser=True, first_name='Shop', last_name='Owner')
        self.staff = User.objects.create_user('profile_staff', is_staff=True, first_name='Bisi', last_name='Lawal')
        self.other = User.objects.create_user('profile_other', is_staff=True)
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff)
        self.day = timezone.localdate() - timedelta(days=2)
        self.arrival = timezone.make_aware(datetime.combine(self.day, time(8, 15)))
        self.leaving = timezone.make_aware(datetime.combine(self.day, time(17, 30)))
        self.profile = self.staff.staff_profile
        self.profile.expected_start = time(8)
        self.profile.save()

    def payload(self, **changes):
        return {'staff': self.staff.id, 'date': str(self.day), 'resumed_at': self.arrival.isoformat(), 'left_at': self.leaving.isoformat(), 'rating': 9, 'notes': 'Excellent work, helped a customer.', 'bonus_recommended': True, **changes}

    def test_profiles_are_created_for_new_staff(self):
        self.assertEqual(StaffProfile.objects.count(), 3)
        normal = User.objects.create_user('customer_login')
        self.assertFalse(StaffProfile.objects.filter(staff=normal).exists())
        normal.is_staff = True
        normal.save()
        self.assertTrue(StaffProfile.objects.filter(staff=normal).exists())

    def test_admin_sets_salary_role_name_and_resumption(self):
        url = f'/api/staff-profiles/{self.profile.pk}/'
        result = self.owner_client.patch(url, {'first_name': 'Abisola', 'job_title': 'Designer', 'monthly_salary': '150000.00', 'expected_start': '08:30'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.profile.refresh_from_db()
        self.staff.refresh_from_db()
        self.assertEqual(self.profile.monthly_salary, Decimal('150000'))
        self.assertEqual(self.staff.first_name, 'Abisola')
        self.assertEqual(self.profile.expected_start, time(8, 30))
        self.assertFalse(self.staff.is_superuser)
        log = AuditLog.objects.get(model_name='StaffProfile')
        self.assertEqual(log.metadata['changes']['monthly_salary']['before'], '0.00')
        self.assertEqual(log.performed_by_id, self.owner.pk)
        self.assertEqual(self.owner_client.patch(url, {'monthly_salary': '-1'}, format='json').status_code, 400)
        self.assertEqual(self.staff_client.get(url).status_code, 403)
        self.assertEqual(self.staff_client.patch(url, {'monthly_salary': '1'}, format='json').status_code, 403)
        self.assertEqual(self.staff_client.get(f'/api/staff-profiles/{self.other.staff_profile.pk}/').status_code, 403)
        self.assertEqual(self.staff_client.get('/api/staff-profiles/').status_code, 403)

    def test_attendance_rating_notes_bonus_and_privacy(self):
        result = self.owner_client.post('/api/staff-daily-records/', self.payload(), format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['late_minutes'], 15)
        self.assertEqual(result.data['worked_minutes'], 555)
        self.assertEqual(result.data['rating'], 9)
        url = f"/api/staff-daily-records/{result.data['id']}/"
        self.assertEqual(self.staff_client.get(url).status_code, 403)
        self.assertEqual(self.staff_client.post('/api/staff-daily-records/', self.payload(), format='json').status_code, 403)
        self.assertEqual(self.staff_client.patch(url, {'resumed_at': None, 'rating': 10}, format='json').status_code, 403)
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        self.assertEqual(other_client.get(url).status_code, 403)
        self.assertEqual(other_client.get(f'/api/staff-daily-records/?staff={self.staff.id}').status_code, 403)
        self.assertEqual(APIClient().get('/api/staff-profiles/').status_code, 401)
        self.assertEqual(APIClient().get('/api/staff-daily-records/').status_code, 401)

    def test_daily_record_corrections_are_audited_and_unique(self):
        result = self.owner_client.post('/api/staff-daily-records/', self.payload(), format='json')
        self.assertEqual(result.status_code, 201, result.data)
        url = f"/api/staff-daily-records/{result.data['id']}/"
        corrected = self.owner_client.patch(url, {'rating': 4, 'notes': 'Input corrected after review.', 'bonus_recommended': False}, format='json')
        self.assertEqual(corrected.status_code, 200, corrected.data)
        log = AuditLog.objects.get(model_name='StaffDailyRecord', action='update')
        self.assertEqual(log.metadata['changes']['rating'], {'before': 9, 'after': 4})
        self.assertEqual(log.metadata['changes']['notes']['before'], 'Excellent work, helped a customer.')
        self.assertEqual(self.owner_client.post('/api/staff-daily-records/', self.payload(), format='json').status_code, 400)
        self.assertEqual(self.owner_client.delete(url).status_code, 405)
        self.assertEqual(self.owner_client.patch(url, {'staff': self.other.id}, format='json').status_code, 400)
        self.assertEqual(self.owner_client.patch(url, {'date': str(self.day - timedelta(days=1))}, format='json').status_code, 400)
        self.profile.expected_start = time(9)
        self.profile.save()
        self.assertEqual(self.owner_client.get(url).data['late_minutes'], 15)

    def test_invalid_ratings_dates_and_times(self):
        for rating in (0, 11, -1, 1.5):
            result = self.owner_client.post('/api/staff-daily-records/', self.payload(rating=rating), format='json')
            self.assertEqual(result.status_code, 400, result.data)
        invalid = [
            {'left_at': (self.arrival - timedelta(minutes=1)).isoformat()},
            {'resumed_at': None},
            {'date': str(timezone.localdate() + timedelta(days=1)), 'resumed_at': None, 'left_at': None},
            {'resumed_at': (self.arrival + timedelta(days=1)).isoformat()},
            {'date': str(timezone.localdate()), 'resumed_at': (timezone.now() + timedelta(minutes=5)).isoformat(), 'left_at': None},
        ]
        for values in invalid:
            result = self.owner_client.post('/api/staff-daily-records/', self.payload(**values), format='json')
            self.assertEqual(result.status_code, 400, result.data)
        self.assertEqual(self.owner_client.get('/api/staff-daily-records/?start=bad').status_code, 400)
        self.assertEqual(self.owner_client.get('/api/staff-daily-records/?staff=bad').status_code, 400)

    def test_review_without_attendance_and_overnight_shift(self):
        review = self.owner_client.post('/api/staff-daily-records/', self.payload(resumed_at=None, left_at=None, rating=None, notes='Absent today.'), format='json')
        self.assertEqual(review.status_code, 201, review.data)
        self.assertIsNone(review.data['late_minutes'])
        self.assertIsNone(review.data['worked_minutes'])
        arrival = timezone.make_aware(datetime.combine(self.day - timedelta(days=1), time(22)))
        leaving = arrival + timedelta(hours=8)
        overnight = self.owner_client.post('/api/staff-daily-records/', self.payload(date=str(self.day - timedelta(days=1)), resumed_at=arrival.isoformat(), left_at=leaving.isoformat()), format='json')
        self.assertEqual(overnight.status_code, 201, overnight.data)
        self.assertEqual(overnight.data['worked_minutes'], 480)
        one_day = self.owner_client.get(f'/api/staff-daily-records/?start={self.day}&end={self.day}').data
        self.assertEqual(one_day['count'], 1)

    def test_django_admin_keeps_reviews_and_salary_controls_owner_only(self):
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get('/admin/')
        for model in (StaffProfile, StaffDailyRecord):
            model_admin = admin.site._registry[model]
            request.user = self.staff
            self.assertFalse(model_admin.has_view_permission(request))
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            request.user = self.owner
            self.assertTrue(model_admin.has_view_permission(request))
            self.assertTrue(model_admin.has_change_permission(request))

    def test_staff_self_attendance_uses_server_time_and_preserves_private_review(self):
        from unittest.mock import patch
        day = timezone.localdate()
        arrival = timezone.make_aware(datetime.combine(day, time(23, 50)))
        leaving = arrival + timedelta(minutes=30)
        record = StaffDailyRecord.objects.create(staff=self.staff, date=day, rating=8, notes='Private review', bonus_recommended=True)
        root = '/api/staff-daily-records/'
        self.assertEqual(self.staff_client.post(root + 'sign-out/', {}, format='json').status_code, 400)
        self.assertEqual(self.staff_client.post(root + 'sign-in/', {'staff': self.other.pk, 'resumed_at': self.arrival.isoformat()}, format='json').status_code, 400)
        with patch('django.utils.timezone.now', return_value=arrival):
            result = self.staff_client.post(root + 'sign-in/', {}, format='json')
            self.assertEqual(result.status_code, 200, result.data)
            self.assertNotIn('notes', result.data)
            self.assertNotIn('rating', result.data)
            self.assertEqual(self.staff_client.post(root + 'sign-in/', {}, format='json').status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.resumed_at, arrival)
        self.assertEqual(record.notes, 'Private review')
        with patch('django.utils.timezone.now', return_value=leaving):
            self.assertEqual(self.staff_client.get(root + 'attendance/').data['id'], record.pk)
            result = self.staff_client.post(root + 'sign-out/', {}, format='json')
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(result.data['worked_minutes'], 30)
        record.refresh_from_db()
        self.assertEqual(record.left_at, leaving)
        self.assertEqual(record.rating, 8)
        self.assertTrue(record.bonus_recommended)
        self.assertFalse(StaffDailyRecord.objects.filter(staff=self.other).exists())
        self.assertEqual(AuditLog.objects.filter(model_name='StaffDailyRecord', action__in=['sign_in', 'sign_out'], performed_by=self.staff).count(), 2)
        self.assertEqual(APIClient().post(root + 'sign-in/', {}, format='json').status_code, 401)

    def test_staff_cannot_repeat_sign_out_or_change_saved_times(self):
        root = '/api/staff-daily-records/'
        self.assertEqual(self.staff_client.post(root + 'sign-in/', {}, format='json').status_code, 200)
        self.assertEqual(self.staff_client.post(root + 'sign-out/', {}, format='json').status_code, 200)
        record = StaffDailyRecord.objects.get(staff=self.staff)
        original = record.left_at
        self.assertEqual(self.staff_client.post(root + 'sign-out/', {}, format='json').status_code, 400)
        self.assertEqual(self.staff_client.post(root + 'sign-in/', {}, format='json').status_code, 400)
        self.assertEqual(self.staff_client.patch(f'{root}{record.pk}/', {'left_at': None}, format='json').status_code, 403)
        record.refresh_from_db()
        self.assertEqual(record.left_at, original)
