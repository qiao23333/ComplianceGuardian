#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检测结果导出：HTML / 图片(PNG) / PDF。

给桌面端"导出报告"按钮与批量检测汇总用。设计要点：

* 纯 Python，仅依赖 Pillow（图片/PDF 渲染），不引入 tkinter / fastapi。
* 统一输入是"报告载荷" dict（见 ``build_payload``），既可由新引擎
  ``DetectionResult`` 构造，也可由历史库记录直接构造，耦合低。
* 字体：优先加载系统中文字体（Windows 微软雅黑 / macOS 苹方），
  找不到则降级到默认字体（仅影响字形，不影响文件生成）。
* PDF 用 Pillow 图直接存为 PDF（单页），避免引入 reportlab 等重依赖。
"""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from guardian.schema import DetectionResult, SEVERITY_LEVELS

# 风险等级 → 颜色（与 UI 主题一致）
_RISK_COLOR = {
    "高风险": "#d92d20",
    "中风险": "#f79009",
    "低风险": "#fdb022",
    "基本合规": "#12b76a",
    "安全": "#12b76a",
}
_SEV_COLOR = {
    "critical": "#d92d20",
    "high": "#f79009",
    "medium": "#fdb022",
    "low": "#475467",
}
_SEV_LABEL = {
    "critical": "高危",
    "high": "中危",
    "medium": "低危",
    "low": "提示",
}


def build_payload(result: DetectionResult, platform: str = "all",
                  created_at: str = "") -> dict:
    """从新引擎 DetectionResult 构造导出载荷。"""
    findings = []
    for f in result.findings:
        findings.append({
            "keyword": f.keyword,
            "matched_text": f.matched_text,
            "severity": f.severity,
            "category": f.category,
            "suggestion": f.suggestion,
            "source": f.source,
            "match_type": f.match_type,
        })
    return {
        "text": result.text,
        "risk_level": result.summary.get("risk_level", "基本合规"),
        "score": result.summary.get("score", 100),
        "counts": result.summary.get("counts", {}),
        "findings": findings,
        "safe_text": result.safe_text,
        "platform": platform,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ============================================================ HTML

def build_html(payload: dict) -> str:
    """生成带内联样式的 HTML 报告字符串。"""
    esc = html.escape
    risk = payload.get("risk_level", "基本合规")
    color = _RISK_COLOR.get(risk, "#475467")
    counts = payload.get("counts", {})

    rows = []
    for f in payload.get("findings", []):
        sev = f.get("severity", "low")
        sc = _SEV_COLOR.get(sev, "#475467")
        sl = _SEV_LABEL.get(sev, sev)
        sug = esc(f.get("suggestion") or "—")
        kw = esc(f.get("matched_text") or f.get("keyword") or "")
        cat = esc(f.get("category") or "")
        src = esc(f.get("source") or "")
        mtype = esc(f.get("match_type") or "")
        rows.append(
            f'<div class="item">'
            f'<span class="dot" style="background:{sc}"></span>'
            f'<div class="body">'
            f'<div class="kw">{kw} '
            f'<span class="tag" style="background:{sc}22;color:{sc}">{sl}</span>'
            f'<span class="muted">· {cat} · {src} · {mtype}</span></div>'
            f'<div class="sug">建议：{sug}</div>'
            f'</div></div>'
        )
    items_html = "\n".join(rows) if rows else '<div class="empty">未检出风险词 ✅</div>'

    counts_html = " ".join(
        f'<span class="pill">{_SEV_LABEL.get(k, k)} {counts.get(k, 0)}</span>'
        for k in ("critical", "high", "medium", "low")
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>合规检测报告</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei","PingFang SC",system-ui,sans-serif;
       margin:0; padding:32px; background:#f5f7fb; color:#1d2433; }}
.card {{ max-width:860px; margin:0 auto; background:#fff; border-radius:16px;
        padding:28px 32px; box-shadow:0 8px 30px rgba(20,30,60,.08); }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.sub {{ color:#667; font-size:13px; margin-bottom:20px; }}
.badge {{ display:inline-block; padding:6px 16px; border-radius:999px;
         color:#fff; font-weight:700; font-size:15px; }}
.score {{ font-size:40px; font-weight:800; margin:12px 0 4px; }}
.meta {{ color:#667; font-size:13px; margin-bottom:18px; }}
.pill {{ display:inline-block; padding:4px 12px; border-radius:999px;
        background:#eef1f6; color:#455; font-size:13px; margin:0 6px 6px 0; }}
.section-t {{ font-size:15px; font-weight:700; margin:22px 0 10px;
             border-left:4px solid #3b6cff; padding-left:10px; }}
.item {{ display:flex; gap:10px; padding:12px 0; border-bottom:1px solid #f0f2f6; }}
.dot {{ width:10px; height:10px; border-radius:50%; margin-top:6px; flex:none; }}
.body {{ flex:1; }}
.kw {{ font-weight:600; }}
.tag {{ font-size:12px; padding:1px 8px; border-radius:6px; margin-left:6px; }}
.muted {{ color:#90a; font-size:12px; color:#889; }}
.sug {{ color:#556; font-size:13px; margin-top:2px; }}
.empty {{ color:#12b76a; padding:14px 0; }}
.orig {{ background:#f8fafc; border-radius:10px; padding:12px 14px;
        font-size:13px; white-space:pre-wrap; word-break:break-all; }}
.foot {{ margin-top:24px; color:#99a; font-size:12px; text-align:center; }}
</style></head>
<body><div class="card">
<h1>合规检测报告</h1>
<div class="sub">ComplianceGuardian · 本地内容合规检测</div>
<div class="badge" style="background:{color}">{esc(risk)}</div>
<div class="score">{payload.get('score', 100)}<span style="font-size:16px">/100</span></div>
<div class="meta">平台：{esc(payload.get('platform','all'))} ｜ 生成时间：{esc(payload.get('created_at',''))}</div>
<div>{counts_html}</div>
<div class="section-t">命中明细（{len(payload.get('findings', []))}）</div>
{items_html}
<div class="section-t">原文</div>
<div class="orig">{esc(payload.get('text', ''))}</div>
<div class="section-t">改写建议（一键改写时）</div>
<div class="orig">{esc(payload.get('safe_text', '') or '（未开启自动改写）')}</div>
<div class="foot">本报告由 ComplianceGuardian 本地生成，数据不出本机</div>
</div></body></html>"""


def export_html(payload: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(payload), encoding="utf-8")
    return out_path


# ============================================================ 图片 / PDF

def _load_font(size: int):
    """尽力加载一个能显示中文的字体；失败则返回 None（Pillow 用默认位图字体）。"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                from PIL import ImageFont
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return None


def build_image(payload: dict, scale: int = 2) -> "Image.Image":
    """用 Pillow 渲染报告卡片，返回 RGB 图像（供 PNG / PDF 复用）。"""
    from PIL import Image, ImageDraw

    W = 900
    pad = 36
    font_title = _load_font(30 * scale // 2) or _load_font(30)
    font_norm = _load_font(18 * scale // 2) or _load_font(18)
    font_small = _load_font(14 * scale // 2) or _load_font(14)
    font_big = _load_font(54 * scale // 2) or _load_font(54)

    risk = payload.get("risk_level", "基本合规")
    rc = _RISK_COLOR.get(risk, "#475467")
    counts = payload.get("counts", {})
    findings = payload.get("findings", [])

    # 先估算高度
    line_h = 26 * scale // 2
    h = pad * 2 + 40 + 70 + 30 + 24
    h += 30  # counts
    h += 30  # section title
    h += max(1, len(findings)) * (line_h + 14) + 10
    h += 30 + 60  # 原文区
    h += 30 + 60  # 改写区
    h += 30

    img = Image.new("RGB", (W, h), "#ffffff")
    d = ImageDraw.Draw(img)

    def text(x, y, s, font, fill="#1d2433"):
        d.text((x, y), s, font=font, fill=fill)

    y = pad
    text(pad, y, "合规检测报告", font_title, "#1d2433")
    text(pad, y + 36, "ComplianceGuardian · 本地内容合规检测", font_small, "#8895a7")
    y += 40 + 30

    # 风险徽章 + 分数
    d.rounded_rectangle([pad, y, pad + 150 * scale // 2, y + 38 * scale // 2],
                        radius=19 * scale // 2, fill=rc)
    text(pad + 14 * scale // 2, y + 6 * scale // 2, risk, font_norm, "#ffffff")
    text(pad + 170 * scale // 2, y, f"{payload.get('score', 100)}/100",
         font_big, rc)
    y += 38 * scale // 2 + 24

    # 计数
    cnt_str = "  ".join(f"{_SEV_LABEL.get(k, k)} {counts.get(k, 0)}"
                        for k in ("critical", "high", "medium", "low"))
    text(pad, y, f"平台 {payload.get('platform', 'all')} ｜ {cnt_str}",
         font_small, "#667085")
    y += 30

    text(pad, y, f"命中明细（{len(findings)}）", font_norm, "#1d2433")
    y += 28
    for f in findings:
        sev = f.get("severity", "low")
        sc = _SEV_COLOR.get(sev, "#475467")
        kw = f.get("matched_text") or f.get("keyword") or ""
        d.ellipse([pad, y + 6, pad + 10, y + 16], fill=sc)
        line = f"{kw}  [{_SEV_LABEL.get(sev, sev)}] {f.get('category', '')}"
        text(pad + 18, y, line[:42], font_small, "#1d2433")
        y += line_h + 6
    if not findings:
        text(pad + 18, y, "未检出风险词 ✅", font_small, "#12b76a")
        y += line_h + 6
    y += 8

    # 原文
    text(pad, y, "原文", font_norm, "#1d2433")
    y += 24
    d.rounded_rectangle([pad, y, W - pad, y + 52], radius=10, fill="#f5f7fb")
    _wrap_text(d, payload.get("text", ""), pad + 12, y + 10,
               W - 2 * pad - 24, font_small, "#334155")
    y += 52 + 18

    # 改写
    text(pad, y, "改写建议", font_norm, "#1d2433")
    y += 24
    d.rounded_rectangle([pad, y, W - pad, y + 52], radius=10, fill="#f0fdf4")
    _wrap_text(d, payload.get("safe_text", "") or "（未开启自动改写）",
               pad + 12, y + 10, W - 2 * pad - 24, font_small, "#027a48")
    y += 52 + 16

    text(pad, y, "本地生成 · 数据不出本机", font_small, "#aab2c0")

    return img


def _wrap_text(d, text, x, y, max_w, font, fill):
    """简单按字符宽度折行（CJK 逐字，拉丁按词）。"""
    if not text:
        return
    line = ""
    for ch in text:
        test = line + ch
        try:
            w = d.textlength(test, font=font)
        except Exception:
            w = len(test) * 8
        if w > max_w and line:
            d.text((x, y), line, font=font, fill=fill)
            y += 20
            line = ch
        else:
            line = test
    if line:
        d.text((x, y), line, font=font, fill=fill)


def export_image(payload: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = build_image(payload, scale=2)
    img.save(out_path, "PNG")
    return out_path


def export_pdf(payload: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = build_image(payload, scale=2)
    img.convert("RGB").save(out_path, "PDF", resolution=150.0)
    return out_path


def export_all(payload: dict, out_dir: str | Path,
              base_name: str = "合规检测报告") -> dict:
    """一次导出 HTML / PNG / PDF，返回各文件路径。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "html": export_html(payload, out_dir / f"{base_name}.html"),
        "png": export_image(payload, out_dir / f"{base_name}.png"),
        "pdf": export_pdf(payload, out_dir / f"{base_name}.pdf"),
    }
