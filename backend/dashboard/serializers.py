from rest_framework import serializers
from .models import SystemGroup, PowerRecord

class SystemGroupSerializer(serializers.ModelSerializer):
    system_type_display = serializers.CharField(source='get_system_type_display', read_only=True)
    
    class Meta:
        model = SystemGroup
        fields = '__all__'

class PowerRecordSerializer(serializers.ModelSerializer):
    system_name = serializers.CharField(source='system.name', read_only=True)
    system_type = serializers.CharField(source='system.system_type', read_only=True)
    
    class Meta:
        model = PowerRecord
        fields = '__all__'

class RealTimeDataSerializer(serializers.Serializer):
    """接收樹莓派實時數據的專用序列化器"""
    system_id = serializers.IntegerField()
    voltage = serializers.FloatField()
    current = serializers.FloatField()
    power_output = serializers.FloatField(required=False)
    light_intensity = serializers.FloatField(required=False, allow_null=True)
    temperature = serializers.FloatField(required=False, allow_null=True)
    humidity = serializers.FloatField(required=False, allow_null=True)
    panel_azimuth = serializers.FloatField(required=False, allow_null=True)
    panel_tilt = serializers.FloatField(required=False, allow_null=True)
    device_id = serializers.CharField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)