# Generated 2026-06-17 — 加 4 方位 LDR 獨立欄位,讓對照組四向感測器讀值能分開顯示在 dashboard。
# light_intensity 改為四方位平均或單一光照計值。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0003_powerrecord_actuator_total_current_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='powerrecord',
            name='light_north',
            field=models.FloatField(blank=True, null=True, verbose_name='北方 LDR(lux)'),
        ),
        migrations.AddField(
            model_name='powerrecord',
            name='light_east',
            field=models.FloatField(blank=True, null=True, verbose_name='東方 LDR(lux)'),
        ),
        migrations.AddField(
            model_name='powerrecord',
            name='light_west',
            field=models.FloatField(blank=True, null=True, verbose_name='西方 LDR(lux)'),
        ),
        migrations.AddField(
            model_name='powerrecord',
            name='light_south',
            field=models.FloatField(blank=True, null=True, verbose_name='南方 LDR(lux)'),
        ),
        migrations.AlterField(
            model_name='powerrecord',
            name='light_intensity',
            field=models.FloatField(
                blank=True, null=True,
                help_text='四方位平均或單一光照計值',
                verbose_name='光照強度(lux)'),
        ),
    ]
