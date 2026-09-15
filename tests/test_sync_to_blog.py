"""``scripts/sync_to_blog.py`` 的门禁。

为什么值得单独测
----------------
这个脚本维护的是"同一份产物在两个仓库"的一致性 —— 合规卫士 Web 端既发布到
自己的仓库（GitHub Pages），也镜像进个人博客的 ``public/guardian/``。
词库更新后若忘了同步，博客上就是**旧版静态站**：不报错、界面看着正常，
只是结论过时。这类失败没有任何自动信号，只能靠一条会失败的校验兜住。

所以这里测的不是"函数返回了 True"，而是**走真实路径**：
真的跑脚本、真的写文件、真的改坏一个字节，看它是否真的判红。

同时锁住一个刻意的设计：目标目录不存在（换机器 / CI 上没克隆博客仓库）
必须**跳过而不是失败** —— 否则 CI 天天红，红习惯之后真不一致就没人看了。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "sync_to_blog.py"
_SRC = _ROOT / "web"


def _run(target: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GUARDIAN_BLOG_DIR"] = str(target)
    # 中文路径 + Windows 控制台编码：强制子进程用 UTF-8 输出，避免断言里读到乱码
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    """博客侧的目标目录（父目录存在，模拟真实的 public/ 已就位）。"""
    d = tmp_path / "public" / "guardian"
    d.parent.mkdir(parents=True)
    return d


def test_sync_copies_every_source_file(target: Path):
    """首次同步必须把 web/ 里的每个文件都搬过去，且内容字节一致。"""
    r = _run(target)
    assert r.returncode == 0, r.stdout + r.stderr

    src_files = {p.relative_to(_SRC).as_posix() for p in _SRC.rglob("*") if p.is_file()}
    assert src_files, "web/ 里没有文件？源目录结构变了"

    for rel in src_files:
        got = target / rel
        assert got.is_file(), f"漏了 {rel}"
        assert got.read_bytes() == (_SRC / rel).read_bytes(), f"{rel} 内容不一致"


def test_check_passes_after_sync(target: Path):
    assert _run(target).returncode == 0
    r = _run(target, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_check_fails_on_modified_content(target: Path):
    """改坏一个字节 → 必须判红，并指出是哪个文件。"""
    assert _run(target).returncode == 0
    victim = target / "data" / "rules.js"
    victim.write_text(victim.read_text(encoding="utf-8") + "\n// 被篡改\n", encoding="utf-8")

    r = _run(target, "--check")
    assert r.returncode == 1, "副本与源不一致却没有判红"
    assert "data/rules.js" in (r.stdout + r.stderr)


def test_check_fails_on_missing_file(target: Path):
    """副本缺文件 → 判红。词库产物丢了正是最该被发现的一种。"""
    assert _run(target).returncode == 0
    (target / "js" / "engine.js").unlink()

    r = _run(target, "--check")
    assert r.returncode == 1
    assert "js/engine.js" in (r.stdout + r.stderr)


def test_check_fails_on_extra_file(target: Path):
    """副本里有源里没有的文件 → 也要报出来（多半是上次改名的残留）。"""
    assert _run(target).returncode == 0
    (target / "stale-removed.js").write_text("// 上一次同步留下的旧文件\n", encoding="utf-8")

    r = _run(target, "--check")
    assert r.returncode == 1
    assert "stale-removed.js" in (r.stdout + r.stderr)


def test_sync_removes_stale_files(target: Path):
    """同步要顺手清掉残留，否则"多余"永远消不掉。"""
    assert _run(target).returncode == 0
    (target / "stale-removed.js").write_text("// 旧文件\n", encoding="utf-8")

    assert _run(target).returncode == 0
    assert not (target / "stale-removed.js").exists()
    assert _run(target, "--check").returncode == 0


def test_missing_target_is_skipped_not_failed(tmp_path: Path):
    """目标仓库不在本机（换机器 / CI）→ --check 跳过，而不是判失败。

    判失败会让 CI 长期红灯，红习惯之后真不一致就没人看了。
    但**同步**（不带 --check）在目标缺失时必须报错 —— 否则用户以为同步成功了。
    """
    absent = tmp_path / "not-cloned" / "public" / "guardian"
    assert not absent.parent.exists()

    check = _run(absent, "--check")
    assert check.returncode == 0, "目标缺失时 --check 不该判失败"
    assert "跳过" in (check.stdout + check.stderr)

    sync = _run(absent)
    assert sync.returncode == 1, "目标缺失时同步必须报错，不能静默成功"


def test_manifest_records_source_commit(target: Path):
    """产出自述文件：记录它来自哪个提交，便于线上对照。"""
    assert _run(target).returncode == 0
    manifest = json.loads((target / ".guardian-source.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "qiao23333/ComplianceGuardian"
    assert manifest["commit"]
    # 清单里的哈希必须与真实文件对得上（否则这个自述文件本身就在撒谎）
    assert set(manifest["files"]) == {
        p.relative_to(_SRC).as_posix() for p in _SRC.rglob("*")
        if p.is_file() and p.name != ".guardian-source.json"
    }


def test_manifest_is_never_treated_as_extra(target: Path):
    """自述文件是本侧产生的，不该被"多余文件"判定误伤。"""
    assert _run(target).returncode == 0
    assert _run(target, "--check").returncode == 0
