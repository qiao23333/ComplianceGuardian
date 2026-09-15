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

from guardian import __version__ as GUARDIAN_VERSION  # noqa: E402
from guardian import context_guard  # noqa: E402
from guardian.normalize.pipeline import _get_opencc, _load_homophone_map, _NOISE_CHARS  # noqa: E402
from guardian.rulebank import RuleBank  # noqa: E402
from guardian.schema import SEVERITY_LEVELS  # noqa: E402

_DEFAULT_OUT = _ROOT / "web" / "data" / "rules.json"


def _review_log_payload() -> dict:
    """读取复核台账，只保留前端展示需要的字段（原样事实，不做日期运算）。

    台账文件缺失时返回空 dict —— 页面据此显示"未登记复核信息"，
    而不是让整个导出失败。
    """
    path = _ROOT / "rules" / "review_log.json"
    if not path.exists():
        return {}
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out = {}
    for src, meta in (log.get("sources") or {}).items():
        out[src] = {
            "label": meta.get("label", src),
            "basis": meta.get("basis", ""),
            "last": meta.get("last_reviewed", ""),
            "days": meta.get("review_interval_days", 0),
            "note": meta.get("note", ""),
        }
    return out


def _law_family(law_ref: str) -> str:
    """从条款号里抽出法规名做聚合："《广告法》第九条" → "《广告法》"。

    抽不出来就原样返回（如 "《化妆品监督管理条例》" 没带条款号，
    还有少数历史规则直接写条款不带书名号）。
    """
    if not law_ref:
        return ""
    end = law_ref.find("》")
    if end != -1:
        return law_ref[: end + 1]
    # 无书名号：按"第X条/第X款"切开，留住前缀
    idx = law_ref.find("第")
    return law_ref[:idx].strip() if idx > 0 else law_ref.strip()



def _industry_packs_payload() -> list[dict]:
    """读取各行业包的 pack.json，供前端动态渲染"行业词库"选择器。

    为什么不让前端写死一张行业表
    ----------------------------
    行业包是**可插拔**的：新增一个包只需要在 ``rules/industry_packs/`` 下
    放两个文件。如果前端把行业名、条数写在 JS 里，每加一个包都要改前端、
    改文档、改测试——而这正是"同一事实存两处必然漂移"的经典场景。

    所以行业元信息随词库产物一起下发，前端只负责渲染。
    """
    packs_dir = _ROOT / "rules" / "industry_packs"
    if not packs_dir.is_dir():
        return []
    out = []
    for pack_dir in sorted(packs_dir.iterdir()):
        meta_path = pack_dir / "pack.json"
        rules_path = pack_dir / "rules.json"
        if not (meta_path.is_file() and rules_path.is_file()):
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # rule_count 以实际条数为准：pack.json 里那个字段是给人看的摘要，
        # 一旦手写就会与实际漂移（历史上就漂过一次：写 140 实际 179）。
        out.append({
            "id": pack_dir.name,
            "name": meta.get("name", pack_dir.name),
            # 短名供下拉框与徽章使用。用"名称去掉'合规包'三字"这种办法凑短名，
            # 看着省事，实则把命名约定变成了隐式契约——改一次包名就会悄悄失效。
            "short": meta.get("short", meta.get("name", pack_dir.name)),
            "industry": meta.get("industry", ""),
            "description": meta.get("description", ""),
            "version": meta.get("version", ""),
            "rule_count": len(rules) if isinstance(rules, list) else 0,
        })
    return out


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
        # 法规条款号（如 "《广告法》第九条"）。源词库里本来就有，
        # 此前导出时被丢掉，于是 Web 端只能说"这是广告法来的"，
        # 说不到"违反第几条"——而"依据可追溯到条款"恰恰是合规工具
        # 与"违禁词表"的分水岭。
        if r.law_ref:
            item["l"] = r.law_ref
        # 规则说明：解释"为什么有问题 / 什么条件下才合规"
        # （如"无激素类表述需检测报告支撑"），是建议之外的第二层信息。
        if r.note:
            item["n"] = r.note
        payload_rules.append(item)

    payload = {
        "meta": {
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine": GUARDIAN_VERSION,
            "rule_count": len(payload_rules),
            "by_severity": dict(Counter(r.severity for r in rules).most_common()),
            "by_source": dict(
                Counter(r.source.split(":")[0] for r in rules).most_common()
            ),
            "industries": sorted({r.industry for r in rules if r.industry}),
            # 行业包元信息（名称/条数/说明）。前端据此渲染行业选择器，
            # 新增行业包时前端零改动。见 _industry_packs_payload 的说明。
            "industry_packs": _industry_packs_payload(),
            "platforms": ["xiaohongshu", "douyin", "weixin"],
            # 依据覆盖率：有条款号的规则占比。这是一个可以持续盯着看的
            # 健康度指标——掉下去就说明新加的规则没写依据。
            "law_coverage": {
                "with_ref": sum(1 for r in rules if r.law_ref),
                "total": len(rules),
            },
            # 分来源的依据覆盖：平台规则本就不该有法条（依据是平台规范），
            # 混在一起算总覆盖率会把"法律类词库 99% 有依据"这个事实淹掉。
            "coverage_by_source": {
                src: {
                    "n": sum(1 for r in rules if r.source == src),
                    "ref": sum(1 for r in rules if r.source == src and r.law_ref),
                }
                for src in sorted({r.source for r in rules})
            },
            # 依据分布（按法规聚合）：词库页展示"我们的规则站在哪些法条上"
            "by_law": dict(
                Counter(
                    _law_family(r.law_ref) for r in rules if r.law_ref
                ).most_common()
            ),
            # 复核台账（原样带上，**不预先算剩余天数**）。
            # "还剩几天有效"是相对"今天"的，一旦写进产物，产物就会每天漂移，
            # 双端对拍门禁会天天变红。所以只导事实，由浏览器现算。
            "review_log": _review_log_payload(),
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


def _strip_volatile(payload: dict) -> dict:
    """去掉每次都会变的字段（生成时间戳），只留下"实质内容"用于比较。"""
    clone = json.loads(json.dumps(payload, ensure_ascii=False))
    clone.get("meta", {}).pop("generated", None)
    return clone


def check(out_path: Path) -> int:
    """校验磁盘上的前端词库是否仍与 Python 端一致（只读，不写文件）。

    为什么必须有这一步
    ------------------
    真实踩过一次**静默腐烂**：``harden_rulebank.py`` 改了源词库，
    但没人重新跑导出，于是 Web 体验页连续几天跑的是旧词库 ——
    少 12 条规则，「全网最低」的严重度也还是旧值（中危被降回低危）。

    两端不一致时，页面输出的就不再是"同一个工具"的结论，
    而"前端与内核同源"恰恰是这个作品最核心的宣称。
    所以把它做成可进 CI 的检查，而不是依赖人记得手动跑。
    """
    if not out_path.exists():
        print(f"[失败] 找不到 {out_path}")
        print("       请先运行：python scripts/export_web_rules.py")
        return 1

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        fresh, _ = export(Path(td) / "rules.json")

    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    fresh = _strip_volatile(fresh)
    on_disk = _strip_volatile(on_disk)

    if fresh == on_disk:
        print("=== 前端词库与 Python 端一致 ===")
        print(f"规则：{len(fresh.get('rules', []))} 条 · 无漂移")
        return 0

    print("=== 前端词库已与 Python 端漂移 ===")
    print("       修复：python scripts/export_web_rules.py")

    fa, da = fresh.get("rules", []), on_disk.get("rules", [])
    if len(fa) != len(da):
        print(f"  · 规则数：源 {len(fa)} 条 vs 前端 {len(da)} 条")

    # 键取 (关键词, 来源, 平台) 三元组而非仅 (关键词, 严重度)：
    # 同词同级但依据（law_ref）或建议改了的漂移，旧写法是看不见的。
    def _key(r):
        return (r.get("k"), r.get("o"), tuple(r.get("p") or ()))

    map_a = {_key(r): r for r in fa}
    map_b = {_key(r): r for r in da}
    missing = sorted(set(map_a) - set(map_b))
    stale = sorted(set(map_b) - set(map_a))
    # 键相同但内容不同 = 字段级漂移（依据/建议/定级任一项被改过）
    field_drift = sorted(
        k for k in set(map_a) & set(map_b) if map_a[k] != map_b[k]
    )

    for label, diff in (("前端缺少（源里有、前端没有）", missing),
                        ("前端过时（前端有、源里已改或已删）", stale)):
        if not diff:
            continue
        print(f"  · {label} {len(diff)} 条：")
        for k, s, _p in diff[:10]:
            print(f"      {k}  [{s}]")
        if len(diff) > 10:
            print(f"      …… 另有 {len(diff) - 10} 条")

    if field_drift:
        print(f"  · 同词条但字段已变 {len(field_drift)} 条：")
        for k in field_drift[:8]:
            a, b = map_a[k], map_b[k]
            changed = [f for f in set(a) | set(b) if a.get(f) != b.get(f)]
            detail = "，".join(
                f"{f}: {_brief(a.get(f), 30)} → {_brief(b.get(f), 30)}"
                for f in sorted(changed)
            )
            print(f"      {k[0]}：{detail}")
        if len(field_drift) > 8:
            print(f"      …… 另有 {len(field_drift) - 8} 条")

    if not missing and not stale and not field_drift:
        other = [k for k in fresh
                 if k not in ("rules", "meta") and fresh[k] != on_disk.get(k)]
        # meta 逐键通用对比。早先这里写死了一张键名单，结果新增 meta 字段
        # （law_coverage / by_law）漂移时，诊断只能输出"未能定位到具体字段"——
        # 门禁能失败但说不清为什么失败，等于把排查成本又丢回给人。
        _skip = {"generated"}
        meta_diff = [
            k for k in set(fresh.get("meta", {})) | set(on_disk.get("meta", {}))
            if k not in _skip
            and fresh.get("meta", {}).get(k) != on_disk.get("meta", {}).get(k)
        ]
        where = other + [f"meta.{m}" for m in sorted(meta_diff)]
        hint = ""
        if meta_diff:
            for m in sorted(meta_diff):
                a = fresh.get("meta", {}).get(m)
                b = on_disk.get("meta", {}).get(m)
                hint += f"      meta.{m}：源 {_brief(a)} vs 前端 {_brief(b)}\n"
        print(f"  · 规则集合一致，差异在：{where or '（未能定位到具体字段）'}")
        if hint:
            print(hint.rstrip("\n"))

    return 1


def _brief(value, limit: int = 90) -> str:
    """把值压成一行短摘要，供漂移诊断打印。"""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description="导出前端词库 JSON")
    ap.add_argument("--out", default=str(_DEFAULT_OUT), help="输出路径")
    ap.add_argument("--check", action="store_true",
                    help="只校验产物是否仍与 Python 端一致，不写文件（CI 用）")
    args = ap.parse_args()

    out_path = Path(args.out)

    if args.check:
        return check(out_path)

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
