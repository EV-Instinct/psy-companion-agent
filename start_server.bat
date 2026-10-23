@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 小树洞 - 六年级心事陪伴智能体
echo.
echo   ====================================================
echo     小树洞 · 六年级心事陪伴智能体
echo     正在启动服务：http://127.0.0.1:8701
echo     按 Ctrl+C 或关闭本窗口可停止服务
echo   ====================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXEC=.venv\Scripts\python.exe
) else (
    set PYTHON_EXEC=python
)

set PORT=8701
%PYTHON_EXEC% server.py

echo.
echo   服务已停止。
pause
