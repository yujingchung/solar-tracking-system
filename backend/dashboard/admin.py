from django.contrib import admin
from django.utils.html import format_html
from django.db import models
from .models import SystemGroup, PowerRecord

@admin.register(SystemGroup)
class SystemGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'system_type', 'location', 'created_at', 'latest_power', 'record_count']
    list_filter = ['system_type', 'location']
    search_fields = ['name', 'location']
    
    def latest_power(self, obj):
        """顯示最新功率"""
        try:
            latest = PowerRecord.objects.filter(system=obj).first()
            if latest and latest.power_output is not None:
                power_value = float(latest.power_output)
                return format_html(
                    '<span style="color: green; font-weight: bold;">{:.2f} W</span>',
                    power_value
                )
            else:
                return format_html('<span style="color: gray;">無數據</span>')
        except Exception as e:
            return format_html('<span style="color: red;">錯誤</span>')
    
    latest_power.short_description = "最新功率"
    
    def record_count(self, obj):
        """顯示記錄數量"""
        try:
            count = PowerRecord.objects.filter(system=obj).count()
            return f"{count} 筆"
        except Exception:
            return "0 筆"
    
    record_count.short_description = "記錄數量"

@admin.register(PowerRecord) 
class PowerRecordAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'system', 'voltage', 'current', 'power_output', 'temperature', 
                    'raspberry_pi_power', 'actuator_total_power', 'ns_actuator_angle', 'ew_actuator_angle']
    list_filter = ['system', 'timestamp']
    search_fields = ['system__name', 'notes']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    readonly_fields = ['created_at', 'power_output', 'raspberry_pi_power', 'actuator_total_power']
    
    fieldsets = (
        ('系統資訊', {
            'fields': ('system', 'timestamp', 'notes')
        }),
        ('太陽能板發電數據', {
            'fields': ('voltage', 'current', 'power_output')
        }),
        ('樹莓派電源', {
            'fields': ('raspberry_pi_voltage', 'raspberry_pi_current', 'raspberry_pi_power'),
            'classes': ('collapse',)
        }),
        ('推桿總電源 (兩根加總)', {
            'fields': ('actuator_total_voltage', 'actuator_total_current', 'actuator_total_power'),
            'classes': ('collapse',)
        }),
        ('南北推桿', {
            'fields': ('ns_actuator_angle', 'ns_actuator_extension'),
            'classes': ('collapse',)
        }),
        ('東西推桿', {
            'fields': ('ew_actuator_angle', 'ew_actuator_extension'),
            'classes': ('collapse',)
        }),
        ('舊版推桿欄位 (已棄用)', {
            'fields': ('actuator_voltage', 'actuator_current', 'actuator_power', 
                      'actuator_angle', 'actuator_extension'),
            'classes': ('collapse',)
        }),
        ('環境數據', {
            'fields': ('light_intensity', 'temperature', 'humidity'),
            'classes': ('collapse',)
        }),
        ('面板狀態', {
            'fields': ('panel_azimuth', 'panel_tilt'),
            'classes': ('collapse',)
        }),
        ('記錄元數據', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    list_per_page = 50
    
    def get_queryset(self, request):
        """優化查詢性能"""
        return super().get_queryset(request).select_related('system')