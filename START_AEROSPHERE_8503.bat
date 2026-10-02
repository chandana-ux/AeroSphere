@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.11 run_aerosphere.py --port 8503
) else (
  python run_aerosphere.py --port 8503
)
endlocal
