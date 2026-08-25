@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"

rem 设置 Python 环境
set "PATH=%BASE_DIR%\pyenv\Library\bin;%BASE_DIR%\pyenv;%BASE_DIR%\pyenv\Scripts;%PATH%"

rem 设置 Playwright 使用内置浏览器
set "PLAYWRIGHT_BROWSERS_PATH=0"

set PYTHONPATH=.
set PYTHONHASHSEED=1

rem 首次运行：解压 conda 环境
if exist "%BASE_DIR%\pyenv\Scripts\conda-unpack.exe" if not exist "%BASE_DIR%\pyenv\.unpacked" (
    echo [首次运行] 正在解压 Python 环境，请稍候...
    "%BASE_DIR%\pyenv\Scripts\conda-unpack.exe"
    if !errorlevel! equ 0 (
        echo done > "%BASE_DIR%\pyenv\.unpacked"
        echo [完成] 环境解压成功！
    ) else (
        echo [错误] 环境解压失败！
        pause
        exit /b 1
    )
)

cd /d "%BASE_DIR%"

rem 检查配置文件
if not exist .env.prod (
    echo "[错误] 未找到 .env.prod 配置文件！"
    echo "请复制 .env.prod-example 并重命名为 .env.prod，然后填写配置。"
    pause
    exit /b 1
)

echo [启动] HikariBot...

python -m nb_cli run

pause