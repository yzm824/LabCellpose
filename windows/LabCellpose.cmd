@echo off
rem Command-line entry point of the bundled engine: doctor, self-test, inspect, prepare, run, view.
rem -I -B: the bundled runtime only, and nothing is written into this folder. -X utf8: every file is UTF-8.
setlocal
set "LABCEL_ROOT=%~dp0"
"%LABCEL_ROOT%runtime\python.exe" -I -B -X utf8 "%LABCEL_ROOT%app\launcher.py" %*
exit /b %ERRORLEVEL%
