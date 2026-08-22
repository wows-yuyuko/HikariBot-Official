#!/bin/bash
# ============================================================
# HikariBot Linux 一键部署脚本（Poetry 方案）
# 用法: ./deploy.sh
# 要求: 已安装 Python 3.11 ~ 3.12（项目要求 >=3.11,<3.13）
#       需要 sudo 权限（安装系统依赖、中文字体）
# 说明: 使用 Poetry 构建完全隔离的项目虚拟环境（.venv），
#       不污染系统 Python。请勿使用 apt 安装 Poetry（其默认
#       不创建虚拟环境），脚本会使用官方安装器。
# ============================================================
set -e

cd "$(dirname "$0")"

echo "==> [1/6] 检查 Python 版本"
PYTHON=""
for py in python3.11 python3.12 python3; do
    if command -v "$py" >/dev/null 2>&1; then
        if "$py" -c 'import sys; exit(0 if (3, 11) <= sys.version_info < (3, 13) else 1)' 2>/dev/null; then
            PYTHON="$py"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "错误: 未找到 Python 3.11 ~ 3.12，请先安装（项目要求 >=3.11,<3.13）" >&2
    exit 1
fi
echo "    使用: $($PYTHON --version)"

echo "==> [2/6] 初始化 git 子模块 hikari_core"
git submodule update --init --recursive

echo "==> [3/6] 安装 Poetry（如缺失）"
if ! command -v poetry >/dev/null 2>&1; then
    echo "    未检测到 Poetry，使用官方安装器..."
    curl -sSL https://install.python-poetry.org | "$PYTHON" -
    export PATH="$HOME/.local/bin:$PATH"
fi
poetry --version

echo "==> [4/6] 创建隔离环境并安装依赖（按 poetry.lock）"
poetry config virtualenvs.in-project true --local || true
poetry env use "$PYTHON"
poetry install

echo "==> [5/6] 安装 Playwright Chromium 及系统依赖"
poetry run playwright install chromium
PLAYWRIGHT_BIN="$(poetry run which playwright)"
if [ "$(id -u)" -eq 0 ]; then
    "$PLAYWRIGHT_BIN" install-deps chromium || echo "    警告: install-deps 失败，请参考 README 手动安装系统依赖"
else
    sudo "$PLAYWRIGHT_BIN" install-deps chromium || echo "    警告: install-deps 失败，请参考 README 手动安装系统依赖"
fi
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y fonts-noto >/dev/null 2>&1 || echo "    警告: fonts-noto 安装失败，可能影响图片中文渲染"
fi

echo "==> [6/6] 生成 .env.prod（如缺失）"
if [ ! -f .env.prod ]; then
    cp .env.prod-example .env.prod
    echo "    已生成 .env.prod，请编辑填写配置后再启动！"
else
    echo "    .env.prod 已存在，跳过"
fi

echo ""
echo "部署完成！接下来："
echo "  1. 编辑 .env.prod 填写配置（QQ_BOTS / API_TOKEN / SUPERUSERS）"
echo "  2. ./service.sh start   启动"
echo "  3. ./service.sh status  查看状态"
