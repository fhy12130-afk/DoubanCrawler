@echo off
chcp 65001 >nul
cd /d "%~dp0"
python douban_gui.py
pause
