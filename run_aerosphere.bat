@echo off
"%~dp0..\.venv\Scripts\python.exe" "%~dp0run_aerosphere.py" %*
if errorlevel 1 pause
