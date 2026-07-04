@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
call conda activate agent-web
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
