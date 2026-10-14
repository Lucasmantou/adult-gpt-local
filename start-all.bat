@echo off
rem -- 成人版GPT 开机自启脚本（计划任务 AdultGPT_AutoStart 调用，无窗口）--
set "OLLAMA_MODELS=E:\成人版GPT\models"
set "OLLAMA_HOST=0.0.0.0:11434"
set "OLLAMA_ORIGINS=*"
set "OLLAMA_KEEP_ALIVE=5m"

rem -- Ollama 已在跑就不重复拉起 --
netstat -ano -p tcp | findstr /C:":11434" | findstr /C:"LISTENING" >nul
if errorlevel 1 start "Ollama" /min "E:\成人版GPT\Ollama\ollama.exe" serve
:wait1
ping -n 4 127.0.0.1 >nul
netstat -ano -p tcp | findstr /C:":11434" | findstr /C:"LISTENING" >nul
if errorlevel 1 goto wait1

rem -- 网页服务：web-server.py（静态 + /api 转发 + 访问密码）--
netstat -ano -p tcp | findstr /C:":9090" | findstr /C:"LISTENING" >nul
if errorlevel 1 (
    start "AdultGPT-Web" /min python "E:\成人版GPT\web-server.py"
    ping -n 6 127.0.0.1 >nul
)
netstat -ano -p tcp | findstr /C:":9090" | findstr /C:"LISTENING" >nul
if errorlevel 1 (
    start "AdultGPT-Web" /min python "E:\成人版GPT\web-server.py"
    ping -n 6 127.0.0.1 >nul
)
