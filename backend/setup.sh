#!/bin/bash

# ==========================================
# Backend Setup Script (Venv & Dependencies)
# ==========================================

VENV_PATH="/opt/projects/venv"
PROJECT_PATH="/opt/projects/backend"

echo "---------------------------------"
echo "Setup Environment"
echo "---------------------------------"

# 1. 进入项目目录
if [ ! -d "$PROJECT_PATH" ]; then
    echo "Error: Project directory $PROJECT_PATH does not exist."
    exit 1
fi
cd "$PROJECT_PATH"

# 2. 检查/创建虚拟环境
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment at $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
else
    echo "Virtual environment exists at $VENV_PATH"
fi

# 3. 激活虚拟环境
source "$VENV_PATH/bin/activate"

# 4. 安装依赖
echo "Installing/Updating dependencies..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "Warning: requirements.txt not found in $PROJECT_PATH"
fi

echo "Setup complete."
