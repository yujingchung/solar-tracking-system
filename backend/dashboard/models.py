from django.db import models
from django.utils import timezone

class SystemGroup(models.Model):
    SYSTEM_TYPES = [
        ('control', '對照組'),
        ('experiment', '實驗組'),
    ]
    
    name = models.CharField(max_length=100, verbose_name="系統名稱")
    system_type = models.CharField(max_length=20, choices=SYSTEM_TYPES, verbose_name="系統類型")
    location = models.CharField(max_length=100, verbose_name="場域位置")
    description = models.TextField(blank=True, verbose_name="系統描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")
    
    class Meta:
        verbose_name = "系統組別"
        verbose_name_plural = "系統組別"
    
    def __str__(self):
        return f"{self.name} ({self.get_system_type_display()})"

class PowerRecord(models.Model):
    """擴展的發電記錄 - 支援電壓電流數據"""
    system = models.ForeignKey(SystemGroup, on_delete=models.CASCADE, verbose_name="所屬系統")
    timestamp = models.DateTimeField(default=timezone.now, verbose_name="記錄時間")
    
    # 基本電力數據
    voltage = models.FloatField(verbose_name="電壓(V)", help_text="太陽能板輸出電壓")
    current = models.FloatField(verbose_name="電流(A)", help_text="太陽能板輸出電流")
    power_output = models.FloatField(verbose_name="功率(W)", help_text="計算或測量的功率")
    
    # 可選的環境數據
    light_intensity = models.FloatField(null=True, blank=True, verbose_name="光照強度(lux)")
    temperature = models.FloatField(null=True, blank=True, verbose_name="溫度(°C)")
    humidity = models.FloatField(null=True, blank=True, verbose_name="濕度(%)")
    
    # 系統狀態
    panel_azimuth = models.FloatField(null=True, blank=True, verbose_name="方位角(°)")
    panel_tilt = models.FloatField(null=True, blank=True, verbose_name="傾角(°)")
    
    # 記錄元數據
    notes = models.CharField(max_length=200, blank=True, verbose_name="備註")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="記錄建立時間")
    
    class Meta:
        verbose_name = "發電記錄"
        verbose_name_plural = "發電記錄"
        ordering = ['-timestamp']
    
    def save(self, *args, **kwargs):
        # 自動計算功率（如果沒有提供）
        if not self.power_output and self.voltage and self.current:
            self.power_output = self.voltage * self.current
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.system.name} - {self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.power_output:.2f}W"