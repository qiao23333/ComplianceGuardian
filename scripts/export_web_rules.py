#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Python 词库编译成前端可直接加载的 JSON（Web 端体验页用）。

为什么值得这么做
----------------
把检测引擎整体搬到浏览器里跑，一次拿到三个好处：

1. **点击即体验**：作品集里一个链接就能试，不用下载安装任何东西；
2. **零后端**：纯静态文件，扔进任意静态托管（含作品集站点目录）即可；
3. **隐私即卖点**：文案**连服务器都不上传**，在浏览器内完成检测——
   这正是律所/医美/金融/移民客户真正在意的那件事，而市面上绝大多数
   同类工具是云端 SaaS（文案必须粘贴到别人服务器）。

导出内容
--------
* ``rules``    词库（裁剪为前端所需字段，跳过 disabled）
* ``homophone`` 谐音/形近字表
* ``t2s``      繁体→简体映射（逐字，与 Python 管线口径一致）
* ``exempt``   全局上下文豁免词组（最近/最后/最终…）
* ``noise``    噪声字符集
* 其余引擎常量（严重度权重、短词降级阈值等）

产物：``web/data/rules.json``

用法::

    python scripts/export_web_rules.py
    python scripts/export_web_rules.py --out web/data/rules.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from guardian import context_guard  # noqa: E402
from guardian.normalize.pipeline import _get_opencc, _load_homophone_map, _NOISE_CHARS  # noqa: E402
from guardian.rulebank import RuleBank  # noqa: E402
from guardian.schema import SEVERITY_LEVELS  # noqa: E402

_DEFAULT_OUT = _ROOT / "web" / "data" / "rules.json"


def build_t2s_map() -> dict[str, str]:
    """逐字生成繁→简映射（与 pipeline 的逐字符转换口径一致）。

    只收录"确实需要转换"的字，控制在 ~3k 条；整表 UTF-8 约 40KB，
    远小于引入 opencc-js 的体积。
    """
    cc = _get_opencc()
    if cc is None:
        return {}
    out: dict[str, str] = {}
    for code in range(0x4E00, 0xA000):
        ch = chr(code)
        conv = cc.convert(ch)
        if conv != ch and len(conv) == 1:
            out[ch] = conv
    return out


def export(out_path: Path = _DEFAULT_OUT) -> tuple[dict, Path]:
    bank = RuleBank()
    rules = [r for r in bank.all if r.enabled]

    payload_rules = []
    for r in rules:
        item = {
            "k": r.keyword,                      # keyword
            "s": r.severity,                     # severity
            "c": r.category,                     # category
            "o": r.source,                       # origin / source
            "p": r.platforms,                    # platforms
            "m": r.match_mode,                   # match_mode
        }
        if r.industry:
            item["i"] = r.industry
        if r.context_excludes:
            item["x"] = r.context_excludes
        if r.replacements:
            item["r"] = r.replacements
        if r.suggestion:
            item["g"] = r.suggestion             # guidance / suggestion
        if r.severity_by_account:
            item["sa"] = r.severity_by_account
        payload_rules.append(item)

    payload = {
        "meta": {
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine": "3.0.0-alpha",
            "rule_count": len(payload_rules),
            "by_severity": dict(Counter(r.severity for r in rules).most_common()),
            "by_source": dict(
                Counter(r.source.split(":")[0] for r in rules).most_common()
            ),
            "industries": sorted({r.industry for r in rules if r.industry}),
            "platforms": ["xiaohongshu", "douyin", "weixin"],
        },
        "severity": {
            k: {"label": v[0], "tone": v[1], "weight": v[2]}
            for k, v in SEVERITY_LEVELS.items()
        },
        "rules": payload_rules,
        "homophone": _load_homophone_map(),
        "t2s": build_t2s_map(),
        "exempt": {k: list(v) for k, v in context_guard.EXEMPT_PHRASES.items()},
        "noise": sorted(_NOISE_CHARS),
        "short_keyword_max_len": context_guard.SHORT_KEYWORD_MAX_LEN,
        "downgrade_categories": sorted(context_guard.DOWNGRADE_CATEGORIES),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out_path.write_text(body, encoding="utf-8")

    # 同时写一份 rules.js：以 <script> 方式加载。
    # 这样页面**双击打开也能跑**（file:// 下 fetch 本地 JSON 会被 CORS 拦），
    # 也让作品集站点无需任何构建步骤。
    js_path = out_path.with_suffix(".js")
    js_path.write_text(
        "/* 自动生成，请勿手改：python scripts/export_web_rules.py */\n"
        "window.GUARDIAN_RULES = " + body + ";\n",
        encoding="utf-8",
    )
    return payload, js_path


def main() -> int:
    ap = argparse.ArgumentParser(description="导出前端词库 JSON")
    ap.add_argument("--out", default=str(_DEFAULT_OUT), help="输出路径")
    args = ap.parse_args()

    out_path = Path(args.out)
    payload, js_path = export(out_path)
    size_kb = out_path.stat().st_size / 1024

    print("=== 前端词库导出完成 ===")
    print(f"输出：{out_path}")
    print(f"      {js_path.name}（供页面 <script> 直接加载，双击可跑）")
    print(f"体积：{size_kb:.1f} KB")
    print(f"规则：{payload['meta']['rule_count']} 条")
    print(f"严重度：{payload['meta']['by_severity']}")
    print(f"来源：{payload['meta']['by_source']}")
    print(f"行业包：{payload['meta']['industries']}")
    print(f"谐音表：{len(payload['homophone'])} 条 | "
          f"繁简表：{len(payload['t2s'])} 条 | "
          f"噪声字符：{len(payload['noise'])} 个")
    if size_kb > 400:
        print("[提示] 体积超过 400KB，考虑启用 gzip 或裁剪未用到的类目。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
