#!/bin/bash
# ============================================================
# HikariBot Linux 启停脚本
# 用法: ./service.sh {start|stop|restart|status}
# 进程后台运行，标准输出/错误写入 logs/bot.log
# 机器人自身日志位于 logs/info.log
# ============================================================

cd "$(dirname "$0")"

# 官方安装器安装的 Poetry 位于 ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"

APP="HikariBot"
PID_FILE="bot.pid"
LOG_FILE="logs/bot.log"

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
    if is_running; then
        echo "$APP 已在运行 (PID $(cat "$PID_FILE"))"
        return 0
    fi
    if [ ! -f .env.prod ]; then
        echo "错误: 缺少 .env.prod，请先执行 ./deploy.sh 或复制 .env.prod-example 并填写配置" >&2
        exit 1
    fi
    mkdir -p logs
    echo "启动 $APP ..."
    nohup poetry run nb run >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if is_running; then
        echo "$APP 已启动 (PID $(cat "$PID_FILE"))，日志: $LOG_FILE"
    else
        echo "启动失败，请查看日志: $LOG_FILE" >&2
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "停止 $APP (PID $PID) ..."
        kill "$PID"
        for _ in $(seq 1 15); do
            kill -0 "$PID" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$PID" 2>/dev/null; then
            echo "未正常退出，强制结束..."
            kill -9 "$PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        echo "已停止"
    else
        echo "$APP 未在运行"
    fi
}

status() {
    if is_running; then
        echo "$APP 运行中 (PID $(cat "$PID_FILE"))"
    else
        echo "$APP 未运行"
    fi
}

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; start ;;
    status)  status ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
