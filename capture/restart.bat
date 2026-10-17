@echo off
call "%~dp0stop.bat"
timeout /t 1 /nobreak >nul
call "%~dp0start.bat"
