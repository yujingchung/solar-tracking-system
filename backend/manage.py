#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pmp_solar_dashboard.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "無法匯入Django。請確認Django已安裝並且在PYTHONPATH中。"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()