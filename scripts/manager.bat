@echo off
setlocal enabledelayedexpansion

rem 配置
set "ROOT_DIR=%~dp0.."
pushd "%ROOT_DIR%"
set "ROOT_DIR=%CD%"
popd
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\frontend\AgentWeb-user"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"

:menu
echo ==========================================
echo   后端 + 前端服务管理器
echo   1.启动后端  2.启动前端  3.启动全部
echo   4.停止后端  5.停止前端  6.停止全部
echo   7.重启后端  8.重启前端  9.查看状态  0.退出
echo ==========================================
choice /c 1234567890 /n /m "请选择: "
if errorlevel 10 goto :exit
if errorlevel 9 goto :do_status
if errorlevel 8 goto :do_restart_frontend
if errorlevel 7 goto :do_restart_backend
if errorlevel 6 goto :do_stop_all
if errorlevel 5 goto :do_stop_frontend
if errorlevel 4 goto :do_stop_backend
if errorlevel 3 goto :do_start_all
if errorlevel 2 goto :do_start_frontend
if errorlevel 1 goto :do_start_backend
goto :menu

:do_start_backend
call :start_backend
goto :menu

:do_start_frontend
call :start_frontend
goto :menu

:do_start_all
call :start_backend
timeout /t 2 /nobreak >nul
call :start_frontend
goto :menu

:do_stop_backend
call :stop_backend
goto :menu

:do_stop_frontend
call :stop_frontend
goto :menu

:do_stop_all
call :stop_backend
call :stop_frontend
goto :menu

:do_restart_backend
call :stop_backend
timeout /t 2 /nobreak >nul
call :start_backend
goto :menu

:do_restart_frontend
call :stop_frontend
timeout /t 2 /nobreak >nul
call :start_frontend
goto :menu

:do_status
call :check_port %BACKEND_PORT%
if "!RUNNING!"=="1" (
    echo [后端] 运行中，端口 %BACKEND_PORT%
) else (
    echo [后端] 已停止
)
call :check_port %FRONTEND_PORT%
if "!RUNNING!"=="1" (
    echo [前端] 运行中，端口 %FRONTEND_PORT%
) else (
    echo [前端] 已停止
)
goto :menu

:start_backend
call :check_port %BACKEND_PORT%
if "!RUNNING!"=="1" (
    echo [后端] 已经在运行中
    goto :eof
)
call :kill_window "Backend"
echo [后端] 正在启动...
start "Backend" /D "%BACKEND_DIR%" cmd /c "conda activate agent-web && uvicorn app.main:app --reload --host 0.0.0.0 --port %BACKEND_PORT%"
echo [后端] 已启动
goto :eof

:stop_backend
call :kill_window "Backend"
call :kill_port %BACKEND_PORT%
timeout /t 1 /nobreak >nul
call :check_port %BACKEND_PORT%
if "!RUNNING!"=="1" (
    echo [警告] 后端可能未完全停止，请检查端口 %BACKEND_PORT%
) else (
    echo [后端] 已停止
)
goto :eof

:start_frontend
call :check_port %FRONTEND_PORT%
if "!RUNNING!"=="1" (
    echo [前端] 已经在运行中
    goto :eof
)
call :kill_window "Frontend"
echo [前端] 正在启动...
start "Frontend" /D "%FRONTEND_DIR%" cmd /c "npm run dev -- --host 0.0.0.0 --port %FRONTEND_PORT% --strictPort"
echo [前端] 已启动
goto :eof

:stop_frontend
call :kill_window "Frontend"
call :kill_port %FRONTEND_PORT%
call :kill_npm_vite
timeout /t 1 /nobreak >nul
call :check_port %FRONTEND_PORT%
if "!RUNNING!"=="1" (
    echo [警告] 前端可能未完全停止，请检查端口 %FRONTEND_PORT%
) else (
    echo [前端] 已停止
)
goto :eof

rem ---------- 辅助函数 ----------
:check_port
set "RUNNING=0"
for /f "tokens=5" %%a in ('netstat -ano -p tcp ^| findstr /r /c:":%~1 .*LISTENING"') do (
    set "RUNNING=1"
    goto :eof
)
goto :eof

:kill_port
set "FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano -p tcp ^| findstr /r /c:":%~1 .*LISTENING"') do (
    echo   正在结束 PID %%a (端口 %~1)
    taskkill /f /t /pid %%a >nul 2>&1
    if !errorlevel! equ 0 set "FOUND=1"
)
if "!FOUND!"=="0" echo   未找到监听端口 %~1 的进程
goto :eof

:kill_window
echo   正在关闭窗口 "%*"
taskkill /f /t /fi "WINDOWTITLE eq %*" >nul 2>&1
goto :eof

:kill_npm_vite
echo   正在清理 npm/vite 进程...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*npm run dev*' -or $_.CommandLine -like '*vite*' } | ForEach-Object { taskkill /f /t /pid $_.ProcessId 2>$null }"
goto :eof

:exit
echo 正在清理所有子进程...
call :stop_backend
call :stop_frontend
echo 所有服务已停止，退出
endlocal
exit /b 0