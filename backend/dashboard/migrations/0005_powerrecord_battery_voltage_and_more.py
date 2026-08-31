# Generated 2026-06-23 — 加電池端 V/I/P 欄位
# 動機:V1 真實 MPPT 上線後只讀 PV 端 0x3100-0x3103,
# 真實電池狀態需要 0x3104(V) / 0x3105(I) / 0x3106-7(P)
# 12V 鉛酸滿電應顯示 13.5-14.5V

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0004_powerrecord_light_east_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='powerrecord',
            name='battery_voltage',
            field=models.FloatField(
                blank=True, null=True,
                help_text='EPEVER 0x3104,12V 鉛酸滿電應 13.5-14.5V',
                verbose_name='電池電壓(V)'),
        ),
        migrations.AddField(
            model_name='powerrecord',
            name='battery_current',
            field=models.FloatField(
                blank=True, null=True,
                help_text='EPEVER 0x3105,>0 充電 <0 放電',
                verbose_name='電池充電電流(A)'),
        ),
        migrations.AddField(
            model_name='powerrecord',
            name='battery_power',
            field=models.FloatField(
                blank=True, null=True,
                help_text='EPEVER 0x3106/3107,實際進電池的功率',
                verbose_name='電池充電功率(W)'),
        ),
    ]
