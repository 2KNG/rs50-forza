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

rem open side dashboards on left/right monitors after 3s (auto-detect layout)
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep 3; & '%~dp0tools\open_dashboards.ps1'"

python -m src.main --monitor

echo.
echo App stopped.
pause
