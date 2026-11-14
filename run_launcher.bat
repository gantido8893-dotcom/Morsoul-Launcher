@echo off
cd /d "%~dp0"
set PYTHONPATH=.\.venv\Lib\site-packages;.
C:\Users\user\AppData\Roaming\uv\python\cpython-3.13.5-windows-x86_64-none\python.exe -m morsoul_launcher_ui
pause
