#!/bin/bash

# ==========================================
# Backend Restart Script
# ==========================================

# 1. 配置路径变量
# 请根据服务器实际情况修改这些路径
VENV_PATH="/opt/projects/venv"
PROJECT_PATH="/opt/projects/backend"
LOG_FILE="$PROJECT_PATH/server.log"
PORT=5000

echo "---------------------------------"
echo "Date: $(date)"
echo "Project Dir: $PROJECT_PATH"
echo "Venv Dir:    $VENV_PATH"
echo "---------------------------------"

# 2. 进入项目目录
if [ ! -d "$PROJECT_PATH" ]; then
    echo "Error: Project directory $PROJECT_PATH does not exist."
    exit 1
fi
cd "$PROJECT_PATH"

# 3. 激活虚拟环境
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo "Virtual environment activated."
else
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Attempting to run without explicit activation (relying on system python or path)..."
fi

# 4. 停止旧进程
echo "Checking for running processes..."
# 查找 python eyewear_app.py 或 gunicorn wsgi:application 的进程 ID
# 排除 grep 自身，排除当前脚本
PIDS=$(ps -ef | grep -E "python eyewear_app.py|gunicorn.*wsgi:application" | grep -v grep | grep -v "restart.sh" | awk '{print $2}')

if [ -n "$PIDS" ]; then
    echo "Found running process(es): $PIDS"
    for PID in $PIDS; do
        echo "Killing PID $PID..."
        kill -9 $PID
    done
    echo "Stopped."
else
    echo "No running process found."
fi

# 5. 启动新进程
echo "Starting new process..."

# 优先使用 Gunicorn (如果已安装)
if pip show gunicorn > /dev/null 2>&1; then
    echo "Mode: Gunicorn"
    # -w 4: 4个工作进程
    # -b 0.0.0.0:5000: 绑定地址和端口
    # --access-logfile -: 输出访问日志到 stdout (会被重定向到 LOG_FILE)
    nohup gunicorn -w 4 -b 0.0.0.0:$PORT wsgi:application --access-logfile - --error-logfile - > "$LOG_FILE" 2>&1 &
else
    echo "Mode: Python (Flask Built-in)"
    echo "Warning: Gunicorn not found. Using Flask development server (not recommended for production)."
    nohup python eyewear_app.py > "$LOG_FILE" 2>&1 &
fi

# 6. 验证启动状态
sleep 2
NEW_PIDS=$(ps -ef | grep -E "python eyewear_app.py|gunicorn.*wsgi:application" | grep -v grep | grep -v "restart.sh" | awk '{print $2}')

if [ -n "$NEW_PIDS" ]; then
    echo "Success! Backend is running (PID: $NEW_PIDS)."
    echo "Log file: $LOG_FILE"
    echo "You can view logs with: tail -f $LOG_FILE"
else
    echo "Error: Failed to start backend."
    echo "Check log file for details: $LOG_FILE"
    cat "$LOG_FILE"
fi
