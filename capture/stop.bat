@echo off
setlocal
if "%CAPTURE_PORT%"=="" set CAPTURE_PORT=12138
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%CAPTURE_PORT% " ^| findstr LISTENING') do (
  echo Stopping PID %%p
  taskkill /PID %%p /F
)
exit /b 0
