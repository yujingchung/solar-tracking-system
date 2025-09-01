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
    list_display = ['system', 'timestamp', 'voltage', 'current', 'power_output', 'temperature']
    # 修正：移除有問題的 timestamp__date 過濾器
    list_filter = ['system']  
    search_fields = ['system__name', 'notes']
    date_hierarchy = 'timestamp'  # 這個會提供日期過濾功能
    
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('基本資訊', {
            'fields': ('system', 'timestamp', 'notes')
        }),
        ('電力數據', {
            'fields': ('voltage', 'current', 'power_output')
        }),
        ('環境數據', {
            'fields': ('light_intensity', 'temperature', 'humidity')
        }),
        ('角度資訊', {
            'fields': ('panel_azimuth', 'panel_tilt')
        }),
    )
    
    list_per_page = 50
    
    def get_queryset(self, request):
        """優化查詢性能"""
        return super().get_queryset(request).select_related('system')