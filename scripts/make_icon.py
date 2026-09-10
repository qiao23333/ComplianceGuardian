#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标（.ico / .png），纯 Pillow 绘制，无需管理员权限、无需外部素材。

设计说明：
    盾牌 + 对勾，是"安全 / 合规 / 通过"最直观的视觉隐喻。
    配色用蓝→青渐变（信任、专业），在浅色和深色任务栏上都清晰可辨。

用法::

    python scripts/make_icon.py

产出：
    packaging/icon.ico   （多尺寸，Windows 用）
    packaging/icon.png   （512x512，README / 文档用）
    packaging/icon_512.png
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

# 渐变配色：蓝 → 青
COLOR_TOP = (37, 99, 235)      # #2563EB
COLOR_BOTTOM = (6, 182, 212)   # #06B6D4
CHECK_COLOR = (255, 255, 255)

OUT_DIR = Path(__file__).resolve().parent.parent / "packaging"


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def draw_shield(size: int) -> Image.Image:
    """绘制盾牌图标。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = size
    # ---- 盾牌主体（渐变）----
    # 盾牌轮廓：上部矩形 + 下部收敛的尖角
    shield = [
        (s * 0.50, s * 0.06),   # 顶点中
        (s * 0.90, s * 0.20),   # 右上
        (s * 0.90, s * 0.52),   # 右中
        (s * 0.50, s * 0.95),   # 底尖
        (s * 0.10, s * 0.52),   # 左中
        (s * 0.10, s * 0.20),   # 左上
    ]

    # 用逐行填充实现渐变
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(shield, fill=255)

    grad = Image.new("RGB", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(1, size - 1)
        gd.line(
            [(0, y), (size, y)],
            fill=(lerp(COLOR_TOP[0], COLOR_BOTTOM[0], t),
                  lerp(COLOR_TOP[1], COLOR_BOTTOM[1], t),
                  lerp(COLOR_TOP[2], COLOR_BOTTOM[2], t)),
        )

    img.paste(grad, (0, 0), mask)

    # ---- 白色对勾 ----
    w = max(2, int(s * 0.085))   # 线宽
    p1 = (s * 0.30, s * 0.50)
    p2 = (s * 0.45, s * 0.65)
    p3 = (s * 0.72, s * 0.36)
    draw.line([p1, p2], fill=CHECK_COLOR, width=w, joint="curve")
    draw.line([p2, p3], fill=CHECK_COLOR, width=w, joint="curve")

    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 512 主图（文档用）
    big = draw_shield(512)
    big.save(OUT_DIR / "icon_512.png", "PNG")
    big.resize((256, 256), Image.LANCZOS).save(OUT_DIR / "icon.png", "PNG")

    # 多尺寸 ico（Windows）
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_imgs = [draw_shield(sz[0]) for sz in sizes]
    ico_path = OUT_DIR / "icon.ico"
    ico_imgs[0].save(
        ico_path, "ICO",
        sizes=[(im.width, im.height) for im in ico_imgs],
        append_images=ico_imgs[1:],
    )

    print(f"[OK] 图标已生成：")
    print(f"     {ico_path}")
    print(f"     {OUT_DIR / 'icon.png'}")
    print(f"     {OUT_DIR / 'icon_512.png'}")


if __name__ == "__main__":
    main()
