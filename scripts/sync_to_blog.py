# -*- coding: utf-8 -*-
"""把 Web 端静态站同步到个人博客的 ``public/guardian/``。

为什么需要这个脚本
------------------
合规卫士 Web 端是**零构建纯静态**（12 个文件，全部相对路径引用），
本来挂在沙箱域名 ``*.app.workbuddy.host`` 下 —— 地址又长又是别人的域名，
也不适合长期对外。

个人博客（``D:/codex/个人/个人站``）是 Astro + Cloudflare Pages，
push ``main`` 就自动重建，``public/`` 里的东西会原样出现在站点根下。
所以把它镜像到 ``public/guardian/`` 就能得到一个自有域名下的地址::

    https://qiaozt.pages.dev/guardian/          # 现在
    https://<自己的域名>/guardian/                # 绑定自定义域名之后

为什么必须走脚本 + 校验
----------------------
同一份产物存在于**两个仓库**（合规卫士 / 博客），这是典型的"同一事实存两处"。
词库更新后如果忘了同步，博客上就是旧版静态站 —— **不报错、不崩溃、
界面看着正常，只是结论过时**。所以：

* 同步只走这个脚本，不手抄；
* ``--check`` 提供一个**会失败**的一致性校验（本地随时可跑）。

用法::

    python scripts/sync_to_blog.py            # 同步
    python scripts/sync_to_blog.py --check    # 只校验，不一致退出码 1

环境变量 ``GUARDIAN_BLOG_DIR`` 可覆盖目标目录（换机器 / 换博客路径时用）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "web"

#: 博客里的目标目录。默认是本机那份个人站仓库；可用环境变量覆盖。
_DEFAULT_BLOG_DIR = Path(r"D:/codex/个人/个人站/public/guardian")

#: 记录源版本的小文件，随站点一起发布（只含事实：提交号、文件哈希）。
_MANIFEST = ".guardian-source.json"


def _blog_dir() -> Path:
    import os

    override = os.environ.get("GUARDIAN_BLOG_DIR")
    return Path(override) if override else _DEFAULT_BLOG_DIR


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _source_files() -> dict[str, Path]:
    """源目录里所有要发布的文件（相对路径 -> 绝对路径）。"""
    return {
        p.relative_to(_SRC).as_posix(): p
        for p in sorted(_SRC.rglob("*"))
        if p.is_file() and p.name != _MANIFEST
    }


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_ROOT, capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _diff(src: dict[str, Path], dst: Path) -> tuple[list[str], list[str], list[str]]:
    """返回 (缺失, 内容不同, 多余) 三份相对路径清单。"""
    missing, changed, extra = [], [], []
    for rel, sp in src.items():
        dp = dst / rel
        if not dp.is_file():
            missing.append(rel)
        elif dp.read_bytes() != sp.read_bytes():
            changed.append(rel)
    for dp in sorted(dst.rglob("*")):
        if dp.is_file():
            rel = dp.relative_to(dst).as_posix()
            if rel == _MANIFEST:
                continue
            if rel not in src:
                extra.append(rel)
    return missing, changed, extra


def main() -> int:
    ap = argparse.ArgumentParser(description="同步 Web 端静态站到个人博客")
    ap.add_argument("--check", action="store_true",
                    help="只校验副本与源是否一致，不写入")
    args = ap.parse_args()

    dst = _blog_dir()
    src = _source_files()
    total_kb = sum(p.stat().st_size for p in src.values()) // 1024

    print(f"源   : {_SRC}  ({len(src)} 个文件 / {total_kb} KB)")
    print(f"目标 : {dst}")

    if not _SRC.is_dir():
        print("!! 源目录不存在", file=sys.stderr)
        return 1

    # 目标仓库不在这台机器上（换机器 / CI）属于**环境缺失**，不是不一致。
    # 这时候 --check 跳过而不是判失败 —— 否则 CI 会天天红，
    # 红习惯之后真不一致就没人看了。
    if not dst.parent.is_dir():
        msg = f"博客 public 目录不存在（{dst.parent}）"
        if args.check:
            print(f"跳过：{msg} —— 环境缺失，不是一致性错误")
            return 0
        print(f"!! {msg}；可用 GUARDIAN_BLOG_DIR 指定目标", file=sys.stderr)
        return 1

    missing, changed, extra = _diff(src, dst)

    if args.check:
        if not missing and not changed and not extra:
            print(f"OK：副本与源一致（{len(src)} 个文件）")
            return 0
        print("!! 不一致：", file=sys.stderr)
        for tag, items in (("缺失", missing), ("内容不同", changed), ("多余", extra)):
            for rel in items:
                print(f"   {tag}: {rel}", file=sys.stderr)
        print("\n   跑 python scripts/sync_to_blog.py 同步", file=sys.stderr)
        return 1

    for rel in missing + changed:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src[rel], target)
    for rel in extra:
        (dst / rel).unlink()
        # 顺手清掉空目录，避免博客仓库里留一堆空壳
        for parent in (dst / rel).parents:
            if parent != dst and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
            else:
                break

    manifest = {
        "source": "qiao23333/ComplianceGuardian",
        "commit": _git_sha(),
        "synced_at": date.today().isoformat(),
        "files": {rel: _sha256(dst / rel) for rel in src},
    }
    (dst / _MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"已同步：新增 {len(missing)} / 更新 {len(changed)} / 删除 {len(extra)}")
    print(f"源版本：{manifest['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
