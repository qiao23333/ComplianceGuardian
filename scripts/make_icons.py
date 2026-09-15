#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 PWA 图标（盾牌 + 勾）。

为什么要脚本化
--------------
图标是二进制资源，手工塞进仓库就没法复现、也没法改。这个脚本用与页面
favicon 同一套几何（同一份 24×24 的路径数据）重绘成 PNG，改配色时
两端一起改，不会出现"页面里的盾牌和桌面图标不是同一个"。

安全区
------
画的时候内容只占画布 76%，四周留白——Android 的 maskable 图标会把
图标裁成圆形/水滴形，贴边的图形会被切掉。

用法::

    python scripts/make_icons.py            # 生成 192 / 512 / apple-touch
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def bezier(p0, c1, c2, p3, n=28):
    """三次贝塞尔采样：PIL 没有曲线绘制，只能自己打点。"""
    pts = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def shield_polygon(scale: float, ox: float, oy: float):
    """24×24 坐标系下的盾牌轮廓，缩放到目标像素。"""
    def P(p):
        return (ox + p[0] * scale, oy + p[1] * scale)

    left = [(12.0, 2.2), (4.0, 5.4), (4.0, 11.5)]
    left += bezier((4.0, 11.5), (4.0, 16.2), (7.3, 20.4), (12.0, 21.8))
    # 右半边是左半边关于 x=12 的镜像，首尾两点不重复
    right = [(24.0 - x, y) for (x, y) in reversed(left[1:-1])]
    return [P(p) for p in left + right]


def check_points(scale: float, ox: float, oy: float, width: float):
    pts = [(8.4, 12.1), (10.9, 14.6), (15.6, 9.5)]
    return [(ox + p[0] * scale, oy + p[1] * scale) for p in pts], width * scale


BG = (13, 17, 23, 255)        # --bg，与页面深色主题同色
GREEN = (63, 185, 80, 255)    # --ok
INNER = (17, 24, 33, 255)     # 盾牌内部的淡填充


def render(size: int) -> Image.Image:
    # 4 倍超采样再缩下来，边缘才不会有锯齿
    ss = 4
    canvas = size * ss
    img = Image.new("RGBA", (canvas, canvas), BG)
    d = ImageDraw.Draw(img)

    # 内容占 76%，留出 maskable 安全区
    span = canvas * 0.76
    scale = span / 24.0
    ox = (canvas - span) / 2
    oy = (canvas - span) / 2

    poly = shield_polygon(scale, ox, oy)
    d.polygon(poly, fill=INNER)

    # 描边：沿着闭合轮廓画一条粗线（PIL 的 polygon 边框无法控宽，只能这样）
    outline = poly + [poly[0]]
    d.line(outline, fill=GREEN, width=max(2, int(1.7 * scale)), joint="curve")

    pts, w = check_points(scale, ox, oy, 1.9)
    d.line(pts, fill=GREEN, width=max(2, int(w)), joint="curve")
    # 给勾的端点补圆头（PIL 的 joint 只管拐角）
    r = max(1, int(w / 2))
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=GREEN)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "web"
    targets = [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("apple-touch-icon.png", 180),
    ]
    for name, size in targets:
        path = out_dir / name
        render(size).save(path, "PNG", optimize=True)
        print(f"{path.name:24s} {size}x{size}  {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
