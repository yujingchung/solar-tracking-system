# Generated 2026-06-25 — 加 EPEVER SOC 欄位
# 動機:V_batt + I_batt 推 SOC 不夠精準,EPEVER 0x311A 內建估算更穩定
# 範圍 0-100(整數 %),NULL = 讀不到

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0005_powerrecord_battery_voltage_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='powerrecord',
            name='battery_soc',
            field=models.FloatField(
                blank=True, null=True,
                help_text='EPEVER 0x311A 內建估算,0-100',
                verbose_name='電池 SOC(%)'),
        ),
    ]
