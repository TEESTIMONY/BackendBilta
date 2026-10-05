from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets
from .models import StaffProfile, StaffDailyRecord
from .staff_serializers import StaffProfileSerializer, StaffDailyRecordSerializer
from .views import only_own, parse_date_param, write_audit, IsStaffUser, IsOwnerUser


def changed_values(before, after):
    ignored = {'updated_at', 'created_at', 'updated_by_name', 'recorded_by_name'}
    return {field: {'before': before.get(field), 'after': value} for field, value in after.items()
            if field not in ignored and before.get(field) != value}


class StaffProfileViewSet(viewsets.ModelViewSet):
    queryset = StaffProfile.objects.select_related('staff').all()
    serializer_class = StaffProfileSerializer
    permission_classes = [IsOwnerUser]
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
    permission_classes = [IsOwnerUser]
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

    def attendance_record(self):
        records = StaffDailyRecord.objects.filter(staff=self.request.user)
        return (records.filter(resumed_at__isnull=False, left_at__isnull=True).order_by('-date').first()
                or records.filter(date=timezone.localdate()).first())

    @action(detail=False, methods=['get'], permission_classes=[IsStaffUser])
    def attendance(self, request):
        record = self.attendance_record()
        return Response(self.get_serializer(record).data if record else None)

    @action(detail=False, methods=['post'], permission_classes=[IsStaffUser], url_path='sign-in')
    def sign_in(self, request):
        if request.data:
            raise ValidationError('Attendance times are recorded automatically. Do not supply fields.')
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            existing = self.attendance_record()
            if existing and existing.resumed_at:
                raise ValidationError('You have already signed in. Contact admin for corrections.')
            profile, _ = StaffProfile.objects.get_or_create(staff=request.user)
            record, _ = StaffDailyRecord.objects.get_or_create(
                staff=request.user, date=timezone.localdate(),
                defaults={'expected_start': profile.expected_start, 'recorded_by': request.user})
            record.resumed_at = timezone.now()
            record.updated_by = request.user
            record.save(update_fields=['resumed_at', 'updated_by', 'updated_at'])
            write_audit('sign_in', 'StaffDailyRecord', record.id, request.user,
                        metadata={'date': str(record.date), 'resumed_at': record.resumed_at.isoformat()})
        return Response(self.get_serializer(record).data)

    @action(detail=False, methods=['post'], permission_classes=[IsStaffUser], url_path='sign-out')
    def sign_out(self, request):
        if request.data:
            raise ValidationError('Attendance times are recorded automatically. Do not supply fields.')
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            record = self.attendance_record()
            if not record or not record.resumed_at or record.left_at:
                raise ValidationError('Sign in first. You can only sign out once per shift.')
            record.left_at = timezone.now()
            if record.left_at < record.resumed_at:
                raise ValidationError('Leaving time cannot be before arrival.')
            record.updated_by = request.user
            record.save(update_fields=['left_at', 'updated_by', 'updated_at'])
            write_audit('sign_out', 'StaffDailyRecord', record.id, request.user,
                        metadata={'date': str(record.date), 'left_at': record.left_at.isoformat()})
        return Response(self.get_serializer(record).data)
