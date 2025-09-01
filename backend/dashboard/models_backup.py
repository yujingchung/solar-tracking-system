from django.db import models

class SystemGroup(models.Model):
    """系統組別"""
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
    """發電功率記錄"""
    system = models.ForeignKey(SystemGroup, on_delete=models.CASCADE, verbose_name="所屬系統")
    timestamp = models.DateTimeField(verbose_name="記錄時間")
    power_output = models.FloatField(verbose_name="發電功率(W)")
    notes = models.CharField(max_length=200, blank=True, verbose_name="備註")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")
    
    class Meta:
        verbose_name = "發電記錄"
        verbose_name_plural = "發電記錄"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.system.name} - {self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.power_output}W"