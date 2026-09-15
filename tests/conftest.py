"""测试配置"""
import sys
from pathlib import Path

import pytest

# 把项目根目录加入 sys.path，这样可以直接 import guardian
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def tk_root():
    """整个测试会话共用一个 Tk 根窗口。

    为什么必须共用（2026-09-15 实测，踩了一轮）
    ------------------------------------------
    在同一个进程里**反复创建/销毁 Tcl 解释器**，在本机的 Python/Tcl 上
    不可靠：只要先在某个根窗口上建过 customtkinter 控件，销毁该根之后再
    建新根就会失败，而且报错信息看起来完全不像"测试写错了"——

        _tkinter.TclError: Can't find a usable init.tcl in the following
        directories: {D:\\computer\\.py\\新建文件夹\\tcl\\tcl8.6}
        ...
        This probably means that Tcl wasn't installed properly.

    以及另一种形态：``_tkinter.TclError: invalid command name "tcl_findLibrary"``。
    根因是 Tcl 的库路径只在进程内**第一次** ``Tcl_FindExecutable`` 时确定，
    第一个解释器销毁后再建就找不回 ``init.tcl``。

    对照实验（同一台机器，同一解释器）：

    ==================================================== ========
    场景                                                  结果
    ==================================================== ========
    连续建两个裸 ``tk.Tk()``                              正常
    ``tk.Tk()`` + 一个 ``CTkFrame`` → 销毁 → 再建 ``tk.Tk()``  失败
    ``tk.Tk()`` + 一个 ``CTkFrame`` → 销毁 → ``ctk.CTk()``      正常
    ==================================================== ========

    这种"时好时坏"最容易把门禁变成摆设：布局测试**静默 skip**，看起来是
    "环境缺显示"，实际上是在阳间跑得好好的。会话内共用一个根，就永远只有
    一次解释器创建，问题消失。

    注意：根窗口**不能 withdraw**。``winfo_viewable()`` 在隐藏窗口下对所有
    控件都返回 0，而布局门禁正是靠它排除"按条件没 pack 的行"——根一隐藏，
    守卫就会永远通过（比 skip 更糟，属于静默失效）。所以这里用
    ``-alpha 0`` 让窗口对用户不可见，但保持"已映射"状态。
    """
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # 无可用显示（CI 里靠 xvfb-run 提供）
        pytest.skip(f"无法创建 Tk 根窗口：{exc}")

    root.geometry("1100x740")  # 与 apps/desktop/app.py 的 minsize 对齐
    try:
        root.attributes("-alpha", 0.0)  # 透明但仍是 mapped
    except tk.TclError:  # 某些窗口管理器不支持 alpha，不影响测量
        pass
    root.update()

    try:
        yield root
    finally:
        root.destroy()
