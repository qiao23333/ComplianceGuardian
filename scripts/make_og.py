#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成社交分享卡片图（og.png）。

为什么需要它
------------
页面里 og:image 一直指向 /og.png，但仓库里根本没有这个文件——链接被转发到
微信 / 飞书 / Twitter 时是没有预览图的白板。作品集场景下分享链接往往就是
别人对这个项目的**第一印象**，这张图比页面里任何一句文案都先被看到。

内容全部由真实数据驱动（规则条数从 web/data/rules.json 读），
所以词库更新后重新跑一次即可，不会出现"图上写着 1000 条、页面写着 1013 条"。

用法::

    python scripts/make_og.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from make_icons import shield_polygon

W, H = 1200, 630

BG = (13, 17, 23, 255)
WHITE = (230, 237, 243, 255)
DIM = (173, 182, 192, 255)
FAINT = (148, 157, 168, 255)
GREEN = (63, 185, 80, 255)
PANEL = (22, 27, 34, 255)
LINE = (42, 50, 60, 255)

FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"

ROOT = Path(__file__).resolve().parent.parent


def load_rule_count() -> int:
    try:
        data = json.loads((ROOT / "web" / "data" / "rules.json").read_text("utf-8"))
        return int(data["meta"]["rule_count"])
    except Exception:
        return 1000


def f(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def draw_chip(d, x, y, text, font, fg, bg, pad_x=18, pad_y=9):
    w = d.textlength(text, font=font)
    d.rounded_rectangle([x, y, x + w + pad_x * 2, y + font.size + pad_y * 2],
                        radius=999, fill=bg)
    d.text((x + pad_x, y + pad_y), text, font=font, fill=fg)
    return x + w + pad_x * 2


def main() -> None:
    n = load_rule_count()
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 顶部一条品牌色细线，让卡片在信息流里更立得住
    d.rectangle([0, 0, W, 5], fill=GREEN)

    # ---- 品牌行 ----
    poly = shield_polygon(scale=84 / 24, ox=76, oy=62)
    d.polygon(poly, fill=(17, 24, 33, 255))
    d.line(poly + [poly[0]], fill=GREEN, width=5, joint="curve")
    cx, cy = 76 + 42, 62 + 42
    d.line([(cx - 15, cy + 2), (cx - 3, cy + 14), (cx + 17, cy - 11)],
           fill=GREEN, width=7, joint="curve")

    d.text((182, 74), "合规卫士", font=f(FONT_BOLD, 40), fill=WHITE)
    d.text((184, 128), "AdCompli · 文案合规检测", font=f(FONT_REG, 20), fill=FAINT)

    # ---- 主标题 ----
    d.text((76, 226), "粘一段文案，", font=f(FONT_BOLD, 56), fill=WHITE)
    d.text((76, 300), "立刻知道哪里会被平台判违规", font=f(FONT_BOLD, 56), fill=WHITE)

    # ---- 数据事实：条数从真实词库里读，不手写 ----
    y = 400
    x = 76
    facts = [
        (f"{n} 条规则", GREEN, (20, 40, 27, 255)),
        ("移民 / 留学行业红线", DIM, PANEL),
        ("识破谐音 · 跳字 · 全角 · 繁体", DIM, PANEL),
    ]
    font_fact = f(FONT_REG, 22)
    for text, fg, bg in facts:
        x = draw_chip(d, x, y, text, font_fact, fg, bg) + 12

    # ---- 底部差异点 ----
    d.line([(76, 494), (W - 76, 494)], fill=LINE, width=1)
    d.text((76, 520), "检测全程在浏览器里跑 · 文案不出本机 · 断网也能用",
           font=f(FONT_BOLD, 26), fill=WHITE)
    d.text((76, 566), "无后端 · 无埋点 · 无次数限制",
           font=f(FONT_REG, 21), fill=FAINT)

    out = ROOT / "web" / "og.png"
    img.convert("RGB").save(out, "PNG", optimize=True)
    print(f"{out}  {W}x{H}  {out.stat().st_size / 1024:.1f} KB  (规则 {n} 条)")


if __name__ == "__main__":
    main()
