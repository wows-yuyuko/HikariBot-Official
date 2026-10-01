@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"

rem ==== 包内自带的 uv / Python / 依赖缓存 / Chromium，全部离线使用 ====
rem uv.exe 位于包根目录
set "PATH=%BASE_DIR%;%PATH%"
rem 托管 Python 与 wheel 缓存都指向包内目录
set "UV_PYTHON_INSTALL_DIR=%BASE_DIR%\uv-python"
set "UV_CACHE_DIR=%BASE_DIR%\uv-cache"
rem 只使用包内 Python，避免误用用户机器上已安装的其他 Python
set "UV_PYTHON_PREFERENCE=only-managed"
rem Chromium 浏览器目录
set "PLAYWRIGHT_BROWSERS_PATH=%BASE_DIR%\ms-playwright"

set PYTHONPATH=.
set PYTHONHASHSEED=1

cd /d "%BASE_DIR%"

rem 检查配置文件
if not exist .env.prod (
    echo "[错误] 未找到 .env.prod 配置文件！"
    echo "请复制 .env.prod-example 并重命名为 .env.prod，然后填写配置。"
    pause
    exit /b 1
)

if exist ".venv" goto :sync
echo [首次运行] 正在离线初始化 Python 环境，请稍候（无需联网）...

:sync
uv sync --offline --python 3.11
if not errorlevel 1 goto :launch

rem 离线失败常见于缓存不完整或整个文件夹被移动过，退回联网安装
echo "[提示] 离线初始化失败，改用联网安装..."
uv sync --python 3.11
if errorlevel 1 goto :envfail

:launch
echo [启动] HikariBot...
uv run --no-sync nb run
pause
exit /b 0

:envfail
echo "[错误] Python 环境初始化失败，请重新下载完整的离线包。"
pause
exit /b 1
