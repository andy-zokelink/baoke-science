@echo off
REM Claude Code 构建进度监控脚本
REM 每30秒检查一次输出

:loop
cls
echo ====== Claude Code 构建进度 ======
echo 时间: %date% %time%
echo.
echo 最近输出:
type "C:\Users\HermesCC\baoke-science\claude_build.log" 2>nul | find /c "" | findstr /r "^" >nul
if %errorlevel% equ 0 (
    powershell -Command "Get-Content 'C:\Users\HermesCC\baoke-science\claude_build.log' -Tail 20"
)
echo.
echo 数据库状态:
python -c "from db_utils_v2 import *; print(f'题目:{get_question_count()} 概念:{len([c for c in [[1]]])}')" 2>nul
echo.
echo 文件状态:
if exist "C:\Users\HermesCC\baoke-science\docs\index.html" (
    echo index.html 存在
    for %%F in ("C:\Users\HermesCC\baoke-science\docs\index.html") do echo 大小: %%~zF 字节
) else (
    echo index.html 尚未生成
)
echo.
timeout /t 30 /nobreak >nul
goto loop
