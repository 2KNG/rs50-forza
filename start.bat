@echo off
chcp 65001 >nul
title RS50 x FH6
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

echo ============================================
echo   RS50 x Forza Horizon 6
echo   Dashboard: http://127.0.0.1:8777
echo   Quit: Ctrl+C in this window
echo ============================================

rem open dashboard after 3s (wait for app startup)
start "" /min cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8777"

python -m src.main --led

echo.
echo App stopped.
pause
