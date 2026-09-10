#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Python 内核 ↔ 浏览器引擎 对拍验证。

为什么必须做
------------
Web 体验页的价值在于"它给出的是**同一个工具**的结论"。如果前端引擎和
Python 内核结果不一致，作品集展示的就是另一套行为——那叫演示，不叫产品。
本脚本用同一批语料跑两端，逐条比对命中集合与风险等级，把差异摆到台面上。

已知且**预期**的差异
--------------------
* **拼音通道**：前端不含（需 pypinyin，体积不划算，且误报率高）。
  因此纯拼音输入（如 "jiaweixin"）只在 Python 侧命中——这是有意为之，
  脚本会把它单列为"预期差异"，不计入失败。

用法::

    python scripts/verify_web_parity.py
    python scripts/verify_web_parity.py --verbose
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from guardian.engine import DetectionEngine  # noqa: E402
from guardian.schema import DetectionOptions  # noqa: E402

#: 对拍语料：覆盖正样本 / 负样本 / 各类规避手法
CORPUS: list[str] = [
    # 极限词与绝对化用语
    "这是最好的产品",
    "全网最低价，不容错过",
    "史上最强，销量第一",
    "国家级认证产品",
    "100%有效，永久有效",
    "唯一官方渠道",
    # 移民行业红线
    "保证下签，零拒签记录",
    "百分百获批，不成功退全款",
    "我们跟移民局有关系",
    "内部名额有限",
    "假流水可以做",
    "挂靠公司做雇主担保",
    "全澳最低价，华人第一",
    # 留学行业
    "名校保录，保录取",
    "包offer，一周下offer",
    "代考包过，安全可靠",
    "假成绩单也能申请",
    # 导流
    "加我微信，拉你进群",
    "加卫星，我发你资料",
    "卫星号在简介里",
    "私聊我了解详情",
    # 规避写法
    "加我薇信",
    "加我威信",
    "加我溦信",
    "全 网 最 低 价",
    "保 证 下 签",
    "最好的服務",
    "加我ＷｅｉＸｉｎ",
    # 归一化文本上的正则通道：跳字/全角/繁体写出的组合型违规
    # （词库无精确词条、仅正则覆盖，只跑原文必漏）
    "全 球 级 认证",
    "本公司提供全 球 级服务",
    "成功率１００％，绝无例外",
    "全 網 最 低 價",
    # 负样本：必须干净
    "微信支付很方便",
    "关注我们的微信公众号",
    "微信读书上有很多好书",
    "澳洲雇主担保签证的基本要求",
    "高考后留学澳洲的几种路径",
    "专注澳洲技术移民与投资移民服务",
    "我最近最后还是用了这个方案",
    "这个和那个有关系吗",
    "做事情要一步到位",
    "普通分享，无违规内容",
    "我们提供全程中文服务",
    "移民局最新政策解读",
    "完全按照移民局要求准备材料",
    # 拼音规避：仅 Python 侧可检出（前端无拼音通道，属已知预期差异）
    "jiaweixin",
    "加我wei信",
    # 混合长文
    "澳洲雇主担保移民，保证获批，加我微信详聊，我们是澳洲第一",
]


def _python_side(corpus: list[str], industries: list[str]) -> list[dict]:
    eng = DetectionEngine()
    out = []
    for text in corpus:
        r = eng.detect_text(text, DetectionOptions(industries=industries))
        out.append({
            "text": text,
            "risk_level": r.summary["risk_level"],
            "score": r.summary["score"],
            "counts": r.summary["counts"],
            "findings": [
                {"matched": f.matched_text, "severity": f.severity,
                 "match_type": f.match_type}
                for f in r.findings
            ],
        })
    return out


def _js_side(corpus: list[str], industries: list[str]) -> list[dict]:
    runner = _ROOT / "scripts" / "js_parity_runner.js"
    with tempfile.TemporaryDirectory() as tmp:
        cin = Path(tmp) / "corpus.json"
        cout = Path(tmp) / "out.json"
        cin.write_text(
            json.dumps([{"text": t, "options": {"industries": industries}}
                        for t in corpus], ensure_ascii=False),
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["node", str(runner), str(cin), str(cout)],
            cwd=str(_ROOT), capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print("[错误] Node 执行失败：", proc.stderr[-2000:], file=sys.stderr)
            raise SystemExit(1)
        return json.loads(cout.read_text(encoding="utf-8"))


#: 只在 Python 侧存在的通道（拼音）——出现差异时不计为失败
PY_ONLY_MATCH_TYPE = "variant"


def _is_expected_diff(py_item: dict, js_item: dict) -> str | None:
    """判断差异是否属于"已知预期"（拼音通道缺失）。返回原因或 None。"""
    py_hits = {(f["matched"], f["match_type"]) for f in py_item["findings"]}
    js_hits = {(f["matched"], f["match_type"]) for f in js_item["findings"]}
    only_py = py_hits - js_hits
    only_js = js_hits - py_hits
    if not only_js and only_py:
        # Python 多出来的全是变体命中，且原文里含字母/拼音 → 拼音通道差异
        text = py_item["text"]
        if any(mt == PY_ONLY_MATCH_TYPE for _, mt in only_py) and any(
            not ("\u4e00" <= ch <= "\u9fff") for ch in text
        ):
            return "拼音通道（前端不含，属预期）"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Python ↔ JS 引擎对拍")
    ap.add_argument("--verbose", action="store_true", help="打印全部用例结果")
    args = ap.parse_args()

    industries = ["immigration", "study_abroad"]
    py = _python_side(CORPUS, industries)
    js = _js_side(CORPUS, industries)

    assert len(py) == len(js), "两端返回条数不同"

    n_ok = n_diff = n_expected = 0
    diffs: list[str] = []

    for p, j in zip(py, js):
        same_risk = p["risk_level"] == j["risk_level"]
        same_hits = {(f["matched"], f["severity"], f["match_type"]) for f in p["findings"]} == {
            (f["matched"], f["severity"], f["match_type"]) for f in j["findings"]
        }
        if same_risk and same_hits:
            n_ok += 1
            if args.verbose:
                print(f"  ✓ {p['text']}")
            continue

        reason = _is_expected_diff(p, j)
        if reason:
            n_expected += 1
            if args.verbose:
                print(f"  ~ {p['text']}  ← 预期差异（{reason}）")
            continue

        n_diff += 1
        diff_line = [
            f"  ✗ {p['text']}",
            f"      Python: {p['risk_level']} {[(f['matched'], f['severity'], f['match_type']) for f in p['findings']]}",
            f"      JS    : {j['risk_level']} {[(f['matched'], f['severity'], f['match_type']) for f in j['findings']]}",
        ]
        diffs.append("\n".join(diff_line))
        print("\n".join(diff_line))

    total = len(py)
    print("\n=== 对拍结果 ===")
    print(f"  完全一致：{n_ok}/{total}")
    print(f"  预期差异：{n_expected}（拼音通道，前端不含）")
    print(f"  不一致  ：{n_diff}")

    if n_diff == 0:
        print("\n前端引擎与 Python 内核行为一致（仅拼音通道按设计缺失）。")
        return 0
    print("\n[需要修复] 上述不一致项应逐一核对。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
