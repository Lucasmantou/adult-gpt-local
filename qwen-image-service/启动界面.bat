@echo off
cd /d %~dp0
title Qwen-Image-2.1 WebUI
echo ============================================
echo   Qwen-Image-2.1 WebUI  -  http://127.0.0.1:7860
echo.
echo   Starting (10-20 seconds)...
echo   Browser will open automatically when ready.
echo   Close this window = stop service.
echo ============================================
echo.
venv\Scripts\python.exe server.py
echo.
pause
