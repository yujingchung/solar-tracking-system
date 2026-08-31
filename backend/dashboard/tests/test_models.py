"""PowerRecord.save() 自動計算功率的行為測試。

驗證「為什麼」：上傳端（樹莓派 / 模擬器）有時只送電壓電流、不送功率，
後端必須自動補 P=V×I，否則 power_output 會是 None 造成下游統計出錯。
這幾條測試會在自動計算邏輯被改壞時失敗。
"""
from django.test import TestCase

from dashboard.models import SystemGroup, PowerRecord


class PowerRecordAutoPowerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = SystemGroup.objects.create(
            name="測試系統", system_type="experiment", location="測試場域"
        )

    def test_power_output_autofilled_from_voltage_current(self):
        """未提供 power_output 時，應自動以 V×I 補上。"""
        rec = PowerRecord.objects.create(system=self.system, voltage=12.0, current=2.0)
        rec.refresh_from_db()
        self.assertAlmostEqual(rec.power_output, 24.0)

    def test_provided_power_output_is_not_overwritten(self):
        """已提供 power_output 時，不應被 V×I 覆蓋（保留真實量測值）。"""
        rec = PowerRecord.objects.create(
            system=self.system, voltage=12.0, current=2.0, power_output=20.0
        )
        rec.refresh_from_db()
        self.assertAlmostEqual(rec.power_output, 20.0)

    def test_raspberry_pi_power_autofilled(self):
        rec = PowerRecord.objects.create(
            system=self.system, voltage=12.0, current=2.0,
            raspberry_pi_voltage=5.0, raspberry_pi_current=1.5,
        )
        rec.refresh_from_db()
        self.assertAlmostEqual(rec.raspberry_pi_power, 7.5)

    def test_actuator_total_power_autofilled(self):
        rec = PowerRecord.objects.create(
            system=self.system, voltage=12.0, current=2.0,
            actuator_total_voltage=24.0, actuator_total_current=0.5,
        )
        rec.refresh_from_db()
        self.assertAlmostEqual(rec.actuator_total_power, 12.0)

    def test_zero_current_does_not_crash_and_power_stays_zero(self):
        """電流為 0（夜間）→ 不應誤算，power_output 維持 0/None 的合理結果。

        現行邏輯：if not power_output and voltage and current → 因 current=0
        條件為 False，故不自動計算；power_output 維持傳入的 0。
        """
        rec = PowerRecord.objects.create(
            system=self.system, voltage=12.0, current=0.0, power_output=0.0
        )
        rec.refresh_from_db()
        self.assertEqual(rec.power_output, 0.0)
