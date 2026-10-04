from decimal import Decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def combine_daily_counts(apps, schema_editor):
    Count = apps.get_model('crm', 'DailyCashCount')
    AuditLog = apps.get_model('crm', 'AuditLog')
    database = schema_editor.connection.alias
    dates = list(Count.objects.using(database).values_list('date', flat=True).distinct())
    for day in dates:
        rows = list(Count.objects.using(database).filter(date=day).order_by('-updated_at', '-id'))
        kept = rows[0]
        cash = sum((row.cash_amount for row in rows), Decimal('0.00'))
        transfers = sum((row.transfer_amount for row in rows), Decimal('0.00'))
        AuditLog.objects.using(database).create(
            action='combine_counts', model_name='DailyCashCount', object_id=str(kept.pk),
            metadata={'date': str(day), 'cash': str(cash), 'transfer': str(transfers),
                      'original_counts': [{'id': row.pk, 'staff_id': row.recorded_by_id,
                                           'cash_amount': str(row.cash_amount), 'transfer_amount': str(row.transfer_amount),
                                           'note': row.note} for row in rows]},
        )
        kept.cash_amount = cash
        kept.transfer_amount = transfers
        # The old staff field described whose money was counted, not who entered it.
        kept.recorded_by = None
        kept.note = '\n'.join(row.note for row in rows if row.note)
        kept.save(using=database, update_fields=['cash_amount', 'transfer_amount', 'recorded_by', 'note'])
        Count.objects.using(database).filter(date=day).exclude(pk=kept.pk).delete()


class Migration(migrations.Migration):
    dependencies = [('crm', '0013_staffdailyrecord_staffprofile'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.RemoveConstraint(model_name='dailycashcount', name='one_cash_count_per_staff_per_day'),
        migrations.RenameField(model_name='dailycashcount', old_name='staff', new_name='recorded_by'),
        migrations.AlterField(model_name='dailycashcount', name='recorded_by',
                              field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                      related_name='shop_cash_counts_recorded', to=settings.AUTH_USER_MODEL)),
        migrations.AlterModelOptions(name='dailycashcount', options={'ordering': ['-date']}),
        migrations.RunPython(combine_daily_counts, migrations.RunPython.noop),
        migrations.AddConstraint(model_name='dailycashcount', constraint=models.UniqueConstraint(fields=['date'], name='one_shop_cash_count_per_day')),
    ]
