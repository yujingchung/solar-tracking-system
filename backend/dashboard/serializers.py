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
        fields = '__all__'  # Include all fields including new dual actuator fields

class RealTimeDataSerializer(serializers.Serializer):
    """接收樹莓派實時數據的專用序列化器"""
    system_id = serializers.IntegerField()
    
    # 基本電力數據
    voltage = serializers.FloatField()
    current = serializers.FloatField()
    power_output = serializers.FloatField(required=False)
    
    # 可選的環境數據
    light_intensity = serializers.FloatField(required=False, allow_null=True)
    temperature = serializers.FloatField(required=False, allow_null=True)
    humidity = serializers.FloatField(required=False, allow_null=True)
    
    # 系統狀態
    panel_azimuth = serializers.FloatField(required=False, allow_null=True)
    panel_tilt = serializers.FloatField(required=False, allow_null=True)
    
    # 樹莓派電源
    raspberry_pi_voltage = serializers.FloatField(required=False, allow_null=True)
    raspberry_pi_current = serializers.FloatField(required=False, allow_null=True)
    raspberry_pi_power = serializers.FloatField(required=False, allow_null=True)
    
    # 南北推桿
    ns_actuator_angle = serializers.FloatField(required=False, allow_null=True)
    ns_actuator_extension = serializers.FloatField(required=False, allow_null=True)
    
    # 東西推桿
    ew_actuator_angle = serializers.FloatField(required=False, allow_null=True)
    ew_actuator_extension = serializers.FloatField(required=False, allow_null=True)
    
    # 推桿總功率
    actuator_total_voltage = serializers.FloatField(required=False, allow_null=True)
    actuator_total_current = serializers.FloatField(required=False, allow_null=True)
    actuator_total_power = serializers.FloatField(required=False, allow_null=True)
    
    # 舊版推桿相關數據（保留向下相容）
    actuator_voltage = serializers.FloatField(required=False, allow_null=True)
    actuator_current = serializers.FloatField(required=False, allow_null=True)
    actuator_power = serializers.FloatField(required=False, allow_null=True)
    actuator_angle = serializers.FloatField(required=False, allow_null=True)
    actuator_extension = serializers.FloatField(required=False, allow_null=True)
    
    # 其他數據
    device_id = serializers.CharField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)