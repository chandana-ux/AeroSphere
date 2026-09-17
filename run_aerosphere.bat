@echo off
@where py >nul 2>nul
@if errorlevel 1 (python "%~dp0run_aerosphere.py" %*) else (py -3.11 "%~dp0run_aerosphere.py" %*)
if errorlevel 1 pause
