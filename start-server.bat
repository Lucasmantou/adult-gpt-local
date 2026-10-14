@echo off
title ChatGPT Server
rem -- 成人版GPT 手动启动脚本（带访问密码的 web-server.py 版，2026-09-09）--

rem -- Ollama 没在跑就先拉起它（最小化窗口） --
netstat -ano -p tcp | findstr /C:":11434" | findstr /C:"LISTENING" >nul
if errorlevel 1 (
    echo Ollama not running, starting it...
    set "OLLAMA_MODELS=E:\成人版GPT\models"
    set "OLLAMA_HOST=0.0.0.0:11434"
    set "OLLAMA_ORIGINS=*"
set "OLLAMA_KEEP_ALIVE=5m"
    start "Ollama" /min "E:\成人版GPT\Ollama\ollama.exe" serve
    ping -n 7 127.0.0.1 >nul
)

cd /d E:\成人版GPT
echo Starting web server on port 9090 (with password)...
start "" "http://localhost:9090"
python "E:\成人版GPT\web-server.py"
