@echo off
chcp 65001 > nul
echo =====================================
echo 太陽能追日系統啟動器
echo =====================================
echo.
echo 請選擇運行模式:
echo 1. 對比模式 (ANFIS + 傳統追日同時運行)
echo 2. ANFIS智慧追日模式
echo 3. 傳統追日模式  
echo 4. 系統狀態檢查
echo 5. 退出
echo.
set /p choice=請輸入選擇 (1-5): 

if "%choice%"=="1" (
    echo 啟動對比模式...
    cd /d "%~dp0\.."
    python raspberry-pi\src\main_controller.py --mode both
) else if "%choice%"=="2" (
    echo 啟動ANFIS智慧追日模式...
    cd /d "%~dp0\.."
    python raspberry-pi\src\main_controller.py --mode anfis
) else if "%choice%"=="3" (
    echo 啟動傳統追日模式...
    cd /d "%~dp0\.."
    python raspberry-pi\src\main_controller.py --mode traditional
) else if "%choice%"=="4" (
    echo 檢查系統狀態...
    cd /d "%~dp0\.."
    python -c "
from raspberry_pi.src.utils.config_manager import get_config_manager
config = get_config_manager()
print('系統配置載入成功!')
print('硬體配置:', config.hardware)
print('系統配置:', config.system)
"
) else if "%choice%"=="5" (
    echo 退出...
    exit
) else (
    echo 無效選擇，請重新執行
)

pause