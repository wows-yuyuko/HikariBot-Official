#!/bin/bash
# ============================================================
# HikariBot Linux 一键部署脚本（Poetry 方案）
# 用法: ./deploy.sh
# 说明:
#   1. 检测本机 Python（要求 >=3.11,<3.13）：
#      - 符合要求 -> 询问是否使用本机 Python 构建（默认是）
#      - 不符合 / 用户选择不用 -> 自动用 uv 下载隔离 Python 3.11
#   2. 使用 Poetry 构建完全隔离的项目虚拟环境（.venv），
#      不污染系统 Python。请勿使用 apt 安装 Poetry（其默认
#      不创建虚拟环境），脚本会使用官方安装器。
#   需要 sudo 权限（安装系统依赖、中文字体）
# ============================================================
set -e

cd "$(dirname "$0")"

echo "==> [1/6] 检查本机 Python 环境"
PYTHON=""
for py in python3.11 python3.12 python3; do
    if command -v "$py" >/dev/null 2>&1; then
        if "$py" -c 'import sys; exit(0 if (3, 11) <= sys.version_info < (3, 13) else 1)' 2>/dev/null; then
            PYTHON="$py"
            break
        fi
    fi
done

if [ -n "$PYTHON" ]; then
    echo "    检测到符合要求的本机 Python: $($PYTHON --version)"
    USE_LOCAL="yes"
    # 非交互环境（如 CI）下 read 直接返回空，默认使用本机 Python
    read -r -p "    是否使用本机 Python 构建环境？[Y/n] " ANSWER || true
    case "$ANSWER" in
        n|N|no|NO) USE_LOCAL="no" ;;
        *)         USE_LOCAL="yes" ;;
    esac
    if [ "$USE_LOCAL" = "no" ]; then
        echo "    按选择改用 uv 下载隔离 Python..."
        PYTHON=""
    fi
fi

if [ -z "$PYTHON" ]; then
    echo "    未检测到符合要求的本机 Python（>=3.11,<3.13），使用 uv 下载隔离 Python 3.11..."
    if ! command -v uv >/dev/null 2>&1; then
        echo "    安装 uv（优先国内镜像 uv.agentsmirror.com，失败则回退官方源）..."
        if curl -LsSf https://uv.agentsmirror.com/install-cn.sh -o /tmp/uv-install-cn.sh 2>/dev/null && sh /tmp/uv-install-cn.sh; then
            echo "    uv 安装成功（国内镜像）"
        else
            echo "    国内镜像不可用，回退官方安装器..."
            curl -LsSf https://astral.sh/uv/install.sh | sh
        fi
        rm -f /tmp/uv-install-cn.sh
        export PATH="$HOME/.local/bin:$PATH"
    fi
    # uv 下载 Python 默认走国内镜像（南京大学 github-release 镜像，稳定可靠）；
    # 如需更换，可先 export UV_PYTHON_INSTALL_MIRROR=<镜像地址> 再执行本脚本，此处会尊重你的设置
    export UV_PYTHON_INSTALL_MIRROR="${UV_PYTHON_INSTALL_MIRROR:-https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone}"
    uv python install 3.11
    PYTHON="$(uv python find 3.11)"
fi
echo "    使用解释器: $($PYTHON --version)"

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
