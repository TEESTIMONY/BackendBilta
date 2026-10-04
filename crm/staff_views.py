from django.db import transaction
from rest_framework import viewsets
from .models import StaffProfile, StaffDailyRecord
from .staff_serializers import StaffProfileSerializer, StaffDailyRecordSerializer
from .views import IsStaffReadOwnerWrite, only_own, parse_date_param, write_audit


def changed_values(before, after):
    ignored = {'updated_at', 'created_at', 'updated_by_name', 'recorded_by_name'}
    return {field: {'before': before.get(field), 'after': value} for field, value in after.items()
            if field not in ignored and before.get(field) != value}


class StaffProfileViewSet(viewsets.ModelViewSet):
    queryset = StaffProfile.objects.select_related('staff').all()
    serializer_class = StaffProfileSerializer
    permission_classes = [IsStaffReadOwnerWrite]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return only_own(super().get_queryset(), self.request.user, 'staff')

    def perform_update(self, serializer):
        before = self.get_serializer(serializer.instance).data
        with transaction.atomic():
            profile = serializer.save()
            changes = changed_values(before, self.get_serializer(profile).data)
            if changes:
                write_audit('update', 'StaffProfile', profile.id, self.request.user,
                            metadata={'staff_name': str(profile), 'changes': changes})


class StaffDailyRecordViewSet(viewsets.ModelViewSet):
    queryset = StaffDailyRecord.objects.select_related('staff', 'recorded_by', 'updated_by').all()
    serializer_class = StaffDailyRecordSerializer
    permission_classes = [IsStaffReadOwnerWrite]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = only_own(super().get_queryset(), self.request.user, 'staff')
        params = self.request.query_params
        if params.get('staff'):
            try:
                staff_id = int(params['staff'])
            except (TypeError, ValueError):
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'staff': 'Choose a valid staff member.'})
            queryset = queryset.filter(staff_id=staff_id)
        for param, lookup in [('start', 'date__gte'), ('end', 'date__lte'), ('date', 'date')]:
            if params.get(param):
                queryset = queryset.filter(**{lookup: parse_date_param(params[param], param)})
        return queryset

    def perform_create(self, serializer):
        staff = serializer.validated_data['staff']
        profile, _ = StaffProfile.objects.get_or_create(staff=staff)
        with transaction.atomic():
            record = serializer.save(recorded_by=self.request.user, updated_by=self.request.user,
                                     expected_start=profile.expected_start)
            write_audit('create', 'StaffDailyRecord', record.id, self.request.user,
                        metadata={'record': self.get_serializer(record).data})

    def perform_update(self, serializer):
        before = self.get_serializer(serializer.instance).data
        with transaction.atomic():
            record = serializer.save(updated_by=self.request.user)
            changes = changed_values(before, self.get_serializer(record).data)
            if changes:
                write_audit('update', 'StaffDailyRecord', record.id, self.request.user,
                            metadata={'staff_name': record.staff.get_full_name() or record.staff.username,
                                      'date': str(record.date), 'changes': changes})
