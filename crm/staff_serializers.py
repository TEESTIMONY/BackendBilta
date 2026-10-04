from datetime import datetime
from decimal import Decimal
from math import ceil
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from .models import StaffProfile, StaffDailyRecord
from .serializers import person_name


class StaffProfileSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='staff.get_full_name', read_only=True)
    username = serializers.CharField(source='staff.username', read_only=True)
    first_name = serializers.CharField(source='staff.first_name', required=False, allow_blank=False)
    last_name = serializers.CharField(source='staff.last_name', required=False, allow_blank=True)
    active = serializers.BooleanField(source='staff.is_active', read_only=True)
    access_role = serializers.SerializerMethodField()
    monthly_salary = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.00'), required=False)

    class Meta:
        model = StaffProfile
        fields = ('id', 'staff', 'display_name', 'username', 'first_name', 'last_name', 'active', 'access_role', 'job_title', 'monthly_salary', 'expected_start')
        read_only_fields = ('staff',)

    def get_access_role(self, obj):
        return 'owner' if obj.staff.is_superuser else 'staff'

    def update(self, instance, validated_data):
        names = validated_data.pop('staff', {})
        for field, value in names.items():
            setattr(instance.staff, field, value)
        if names:
            instance.staff.save(update_fields=list(names))
        return super().update(instance, validated_data)


class StaffDailyRecordSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.get_full_name', read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    late_minutes = serializers.SerializerMethodField()
    worked_minutes = serializers.SerializerMethodField()
    rating = serializers.IntegerField(min_value=1, max_value=10, required=False, allow_null=True)
    staff = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.filter(is_staff=True))

    class Meta:
        model = StaffDailyRecord
        fields = ('id', 'staff', 'staff_name', 'date', 'expected_start', 'resumed_at', 'left_at', 'late_minutes', 'worked_minutes', 'rating', 'notes', 'bonus_recommended', 'recorded_by_name', 'updated_by_name', 'created_at', 'updated_at')
        read_only_fields = ('expected_start',)

    def get_recorded_by_name(self, obj):
        return person_name(obj.recorded_by)

    def get_updated_by_name(self, obj):
        return person_name(obj.updated_by)

    def get_late_minutes(self, obj):
        if obj.resumed_at is None or obj.expected_start is None:
            return None
        expected = timezone.make_aware(datetime.combine(obj.date, obj.expected_start))
        return max(0, ceil((obj.resumed_at - expected).total_seconds() / 60))

    def get_worked_minutes(self, obj):
        if obj.resumed_at is None or obj.left_at is None:
            return None
        return int((obj.left_at - obj.resumed_at).total_seconds() / 60)

    def validate(self, attrs):
        instance = self.instance
        if instance:
            for field in ('staff', 'date'):
                if field in attrs and attrs[field] != getattr(instance, field):
                    raise serializers.ValidationError({field: 'This record belongs to a fixed staff member and day.'})
        day = attrs.get('date', instance.date if instance else timezone.localdate())
        if day > timezone.localdate():
            raise serializers.ValidationError({'date': 'Daily records cannot be entered for a future day.'})
        resumed = attrs.get('resumed_at', instance.resumed_at if instance else None)
        left = attrs.get('left_at', instance.left_at if instance else None)
        if resumed and timezone.localdate(resumed) != day:
            raise serializers.ValidationError({'resumed_at': 'Arrival must be on the selected day in Africa/Lagos.'})
        if left and (not resumed or left < resumed):
            raise serializers.ValidationError({'left_at': 'Leaving time must be on or after arrival.'})
        if any(value and value > timezone.now() for value in (resumed, left)):
            raise serializers.ValidationError({'detail': 'Actual attendance times cannot be in the future.'})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not request or not request.user.is_superuser:
            for field in ('rating', 'notes', 'bonus_recommended', 'recorded_by_name', 'updated_by_name'):
                data.pop(field, None)
        return data
