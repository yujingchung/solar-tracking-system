#!/usr/bin/env python3
"""
太陽能追日系統主控制程式
作者: YuJing
版本: 1.0
"""

import sys
import os
import logging
import argparse
from pathlib import Path
from datetime import datetime

def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='太陽能追日系統主控制器')
    parser.add_argument(
        '--mode', 
        choices=['both', 'anfis', 'traditional'],
        default='both',
        help='運行模式: both(對比模式), anfis(僅ANFIS), traditional(僅傳統)'
    )
    parser.add_argument(
        '--config',
        default='system_config.json',
        help='配置檔案名稱'
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("太陽能追日系統主控制器")
    print("="*60)
    print(f"運行模式: {args.mode}")
    print(f"配置檔案: {args.config}")
    print("系統初始化完成！")
    print("="*60)

if __name__ == "__main__":
    main()