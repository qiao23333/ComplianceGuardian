"""测试配置"""
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，这样可以直接 import guardian
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
