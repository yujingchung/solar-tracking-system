"""
setup_systems.py
建立四組系統資料 (實驗組I/II、對照組I/II)

使用方式：
    docker exec solar_backend python manage.py setup_systems
"""
from django.core.management.base import BaseCommand
from dashboard.models import SystemGroup


class Command(BaseCommand):
    help = '建立四組追日系統 (實驗組I/II、對照組I/II) 於先鋒金土地公廟'

    def handle(self, *args, **options):
        systems = [
            {
                'name': '實驗組I',
                'system_type': 'experiment',
                'location': '新北先鋒金土地公廟',
                'description': 'ANFIS 智能追日系統 - 第一組',
            },
            {
                'name': '實驗組II',
                'system_type': 'experiment',
                'location': '新北先鋒金土地公廟',
                'description': 'ANFIS 智能追日系統 - 第二組',
            },
            {
                'name': '對照組I',
                'system_type': 'control',
                'location': '新北先鋒金土地公廟',
                'description': '差分感測追日系統 - 第一組',
            },
            {
                'name': '對照組II',
                'system_type': 'control',
                'location': '新北先鋒金土地公廟',
                'description': '差分感測追日系統 - 第二組',
            },
        ]

        self.stdout.write(self.style.HTTP_INFO('\n── 建立系統組別 ──────────────────────────'))
        for sys_data in systems:
            obj, created = SystemGroup.objects.get_or_create(
                name=sys_data['name'],
                defaults=sys_data,
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ 建立成功: {obj.name}  →  系統 ID = {obj.id}')
                )
            else:
                # 更新 location 與 description（以防資料舊）
                obj.location = sys_data['location']
                obj.description = sys_data['description']
                obj.save()
                self.stdout.write(
                    f'⏩ 已存在 : {obj.name}  →  系統 ID = {obj.id}'
                )

        self.stdout.write(self.style.HTTP_INFO('──────────────────────────────────────────'))
        self.stdout.write(self.style.SUCCESS(
            '\n請將以上 ID 設定到各樹莓派的 config.json → "system_id" 欄位：'
        ))
        for obj in SystemGroup.objects.order_by('id'):
            self.stdout.write(f'  {obj.name:8s}  →  "system_id": {obj.id}')
        self.stdout.write('')
