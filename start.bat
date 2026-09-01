@echo off
chcp 65001 >nul
title CloudPhoneBoard Launcher
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
