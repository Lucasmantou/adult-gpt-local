@echo off
cd /d %~dp0
title Stop Qwen-Image-2.1
echo Stopping Qwen-Image-2.1 service...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo.
echo Done.
pause
