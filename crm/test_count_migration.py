from datetime import date
from decimal import Decimal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ShopCountMigrationTests(TransactionTestCase):
    def test_old_staff_counts_become_one_shop_total_without_losing_money(self):
        old = [('crm', '0013_staffdailyrecord_staffprofile')]
        new = [('crm', '0014_shop_daily_cash_count')]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            User = apps.get_model('auth', 'User')
            Count = apps.get_model('crm', 'DailyCashCount')
            a = User.objects.create(username='migration_a', is_staff=True)
            b = User.objects.create(username='migration_b', is_staff=True)
            day = date(2026, 10, 1)
            Count.objects.create(staff=a, date=day, cash_amount='100.00', transfer_amount='200.00', note='First note')
            Count.objects.create(staff=b, date=day, cash_amount='300.00', transfer_amount='400.00', note='Second note')
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            apps = executor.loader.project_state(new).apps
            counts = apps.get_model('crm', 'DailyCashCount').objects.all()
            self.assertEqual(counts.count(), 1)
            total = counts.get()
            self.assertEqual(total.cash_amount, Decimal('400'))
            self.assertEqual(total.transfer_amount, Decimal('600'))
            self.assertIsNone(total.recorded_by_id)
            self.assertIn('First note', total.note)
            self.assertIn('Second note', total.note)
            audit = apps.get_model('crm', 'AuditLog').objects.get(action='combine_counts')
            self.assertEqual(len(audit.metadata['original_counts']), 2)
        finally:
            MigrationExecutor(connection).migrate(new)
