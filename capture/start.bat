@echo off
setlocal
cd /d "%~dp0"
if "%CAPTURE_PORT%"=="" set CAPTURE_PORT=12138
echo Starting mitmdump on port %CAPTURE_PORT% ...
mitmdump -s capture_addon.py --listen-port %CAPTURE_PORT%
