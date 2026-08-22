#!/bin/bash
# 内容合规检测工具 v2.3 — Mac/Linux 启动脚本
# 自动查找可用的 Python，安装依赖，启动应用

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SOURCE" ]; do
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    [[ $SCRIPT_SOURCE != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 查找可用的 Python（优先 python3）
PYTHON=""
for p in "python3" "python" "/usr/local/bin/python3" "/opt/homebrew/bin/python3"; do
    if command -v "$p" &>/dev/null || [ -f "$p" ]; then
        if "$p" -c "import tkinter" 2>/dev/null; then
            PYTHON="$p"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ 找不到带 tkinter 的 Python"
    echo "请安装 Python 3.10+ (包含 tkinter)"
    echo "  Mac: brew install python@3.12"
    echo "  或从 https://www.python.org/downloads/ 下载"
    read -n 1 -s -r -p "按任意键退出..."
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1)
echo "ℹ️  Python: $PYTHON_VERSION"
echo "✅ tkinter 已就绪"

if [ ! -f "app.py" ]; then
    echo "❌ 找不到 app.py"
    exit 1
fi

# 检查并安装依赖
echo "ℹ️  检查依赖..."
$PYTHON -c "import customtkinter" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 首次运行，安装依赖..."
    $PYTHON -m pip install customtkinter pyahocorasick
fi
$PYTHON -c "import ahocorasick" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 安装 AC自动机依赖..."
    $PYTHON -m pip install pyahocorasick
fi
echo "✅ 依赖已就绪"

echo ""
echo "🚀 正在启动合规卫士 v2.3..."
echo "===================================="
$PYTHON app.py

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ 程序异常退出（错误码：$EXIT_CODE）"
    read -n 1 -s -r -p "按任意键退出..."
    exit $EXIT_CODE
fi
