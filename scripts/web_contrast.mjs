#!/usr/bin/env node
/**
 * 合规卫士 · Web 端对比度探针
 * ============================================================
 *
 * 为什么需要它
 * ------------
 * 这个页面把"能不能看清"当成产品质量的一部分：它是在手机屏幕上、
 * 在户外光线下被内容运营用来看自己文案的。深色主题里那些 11–12px 的
 * 辅助文字最容易在调色时被顺手调暗，而人眼在显示器上很难察觉
 * "3.8:1"和"4.5:1"的差别——必须量。
 *
 * 判定标准（WCAG 2.1）：
 *   - 正常文字      ≥ 4.5:1
 *   - 大字（≥24px，或 ≥18.66px 且粗体）≥ 3.0:1
 *
 * 它踩过的两个坑（照抄 xuanlan 项目的教训）
 * ----------------------------------------
 *   1. Chrome 会把 color-mix() 序列化成 color(srgb 0.1 0.2 0.3)（0–1 区间），
 *      与 rgb(0-255) 混在一起。只抓数字会把所有东西都判成接近黑色 → 假阳性。
 *   2. 找底色必须优先看 backgroundColor，不能因为有 backgroundImage 就
 *      整块跳过，否则会一路走到 body 上、输出 0 条"看起来完美实则没测"。
 *
 * 用法
 * ----
 *   cd web && python -m http.server 8923 --bind 127.0.0.1
 *   node scripts/web_contrast.mjs                    # 只看不达标的
 *   THEME=dark node scripts/web_contrast.mjs         # 只测深色
 *   ALL=1 node scripts/web_contrast.mjs              # 连达标的也列出来
 */

import { createRequire } from 'node:module';

const PUPPETEER_ROOT = process.env.PUPPETEER_ROOT || 'G:/work/牛马/wb工作空间/xuanlan';
const require = createRequire(PUPPETEER_ROOT + '/');
const puppeteer = require('puppeteer-core');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8923/index.html';
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const ONLY_THEME = process.env.THEME || '';
const SHOW_ALL = process.env.ALL === '1';

// ---------------------------------------------------------------- 采集
// 对比度必须在真实渲染后量：颜色可能来自 color-mix()、内联样式或继承，
// 静态读 CSS 文件算不准。

const COLLECT = () => {
  function parseColor(s) {
    if (!s) return null;
    s = String(s).trim();
    if (s === 'transparent') return { r: 0, g: 0, b: 0, a: 0 };
    let m = s.match(/^rgba?\(([^)]+)\)$/i);
    if (m) {
      const p = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
      if (p.length >= 3 && p.slice(0, 3).every((v) => !isNaN(v))) {
        return { r: p[0], g: p[1], b: p[2], a: p.length > 3 && !isNaN(p[3]) ? p[3] : 1 };
      }
      return null;
    }
    // color(srgb 0.1 0.2 0.3 / 0.5) —— Chrome 对 color-mix() 的序列化形式
    m = s.match(/^color\(\s*srgb\s+([^)]+)\)$/i);
    if (m) {
      const p = m[1].split(/[\s/]+/).filter(Boolean).map(Number);
      if (p.length >= 3) {
        return {
          r: p[0] * 255, g: p[1] * 255, b: p[2] * 255,
          a: p.length > 3 && !isNaN(p[3]) ? p[3] : 1,
        };
      }
    }
    return null;
  }

  function lum(c) {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }

  function ratio(a, b) {
    const l1 = Math.max(lum(a), lum(b));
    const l2 = Math.min(lum(a), lum(b));
    return (l1 + 0.05) / (l2 + 0.05);
  }

  /** 把半透明前景叠到不透明底色上 */
  function over(fg, bg) {
    const a = fg.a == null ? 1 : fg.a;
    return {
      r: fg.r * a + bg.r * (1 - a),
      g: fg.g * a + bg.g * (1 - a),
      b: fg.b * a + bg.b * (1 - a),
      a: 1,
    };
  }

  /** 自下而上找真实底色：收集沿途所有背景色，到第一个不透明为止 */
  function effectiveBg(el) {
    const stack = [];
    let node = el;
    let fallback = null;
    while (node && node.nodeType === 1) {
      const cs = getComputedStyle(node);
      const c = parseColor(cs.backgroundColor);
      if (c && c.a > 0) {
        stack.push(c);
        if (c.a >= 0.99) { fallback = c; break; }
      }
      node = node.parentElement;
    }
    if (!fallback) {
      const cs = getComputedStyle(document.documentElement);
      fallback = parseColor(cs.backgroundColor) || { r: 13, g: 17, b: 23, a: 1 };
    }
    // 从最底层往上合成
    let base = { r: fallback.r, g: fallback.g, b: fallback.b, a: 1 };
    for (let i = stack.length - 1; i >= 0; i--) {
      if (stack[i] === fallback) continue;
      base = over(stack[i], base);
    }
    return base;
  }

  const out = [];
  const all = document.querySelectorAll('body *');
  for (const el of all) {
    // 只统计"自己直接持有可见文字"的元素
    let hasText = false;
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) { hasText = true; break; }
    }
    if (!hasText) continue;

    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;

    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (parseFloat(cs.opacity) < 0.05) continue;

    // 必须用 checkVisibility()，不能只靠"有没有盒子"。
    //
    // 收起的 <details> 用的是 content-visibility —— 内容**不绘制，但布局盒
    // 照旧存在**，getBoundingClientRect() 照样返回真实高度（实测 294px）。
    // 早期版本因此把收起面板里的文字也算进了"可见文字"，量了一堆用户根本
    // 看不见的东西：数字虚高，还可能给出假的"对比度不达标"。
    if (typeof el.checkVisibility === 'function') {
      if (!el.checkVisibility({ contentVisibilityAuto: true, opacityProperty: true })) {
        continue;
      }
    }

    const fg0 = parseColor(cs.color);
    if (!fg0) continue;
    const bg = effectiveBg(el);
    const fg = fg0.a >= 0.99 ? fg0 : over(fg0, bg);

    const size = parseFloat(cs.fontSize) || 16;
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const isLarge = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = isLarge ? 3.0 : 4.5;

    out.push({
      sel: el.tagName.toLowerCase() +
        (el.id ? '#' + el.id : '') +
        (el.className && typeof el.className === 'string'
          ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''),
      text: el.textContent.trim().slice(0, 34),
      size: Math.round(size * 10) / 10,
      weight,
      need,
      cr: Math.round(ratio(fg, bg) * 100) / 100,
      color: cs.color,
      bg: 'rgb(' + Math.round(bg.r) + ', ' + Math.round(bg.g) + ', ' + Math.round(bg.b) + ')',
    });
  }
  return out;
};

// ---------------------------------------------------------------- 主流程

/**
 * 要量的视图。
 *
 * 早期版本只量了默认的「单条检测」页 —— 于是其他标签页的文字**从来没被
 * 量过**：词库列表、批量结果表、以及默认收起的词库健康度面板，它们
 * 颜色改坏了这个门禁也不会响。只在首屏量，等于门禁只守住了 1/N。
 */
const VIEWS = [
  { name: '单条检测', tab: 'single' },
  { name: '批量检测', tab: 'batch' },
  { name: '词库浏览', tab: 'rules' },
  {
    name: '词库健康度（展开）',
    tab: 'rules',
    open: 'rHealth',
  },
  {
    // 「我的词库」空态只有一句提示，量不到条目行/风险标/来源标签这些
    // 真正会出问题的文字。所以先塞两条进去（一条启用、一条停用，
    // 覆盖 is-off 那种半透明态）再量。
    name: '我的词库（含词条）',
    tab: 'my',
    seed: `localStorage.setItem('adcompli-my-rules', JSON.stringify([
      { id:'u_c1', keyword:'ZZ对比度探针甲', category:'内部禁用', severity:'critical',
        suggestion:'改成「定向邀约」', law_ref:'公司内部合规要求', note:'', enabled:true },
      { id:'u_c2', keyword:'ZZ对比度探针乙', category:'竞品名', severity:'medium',
        suggestion:'', law_ref:'', note:'', enabled:false }
    ]));`,
  },
];

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new', args: ['--no-sandbox'],
});

const themes = ONLY_THEME ? [ONLY_THEME] : ['dark', 'light'];
let bad = 0;
let totalMeasured = 0;

for (const theme of themes) {
  for (const view of VIEWS) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1200 });
    await page.goto(BASE_URL, { waitUntil: 'networkidle0' });

    // 有的视图要先有数据才有可量的文字；塞完必须 reload 让它重新初始化，
    // 于是 data-theme 也得在那之后再设一次（reload 会还原主题）。
    if (view.seed) {
      await page.evaluate(view.seed);
      await page.reload({ waitUntil: 'networkidle0' });
    }

    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);

    // 让检测跑起来，结果区那些动态文字也要量到
    await page.evaluate(() => {
      const el = document.getElementById('input');
      if (el) {
        el.value = '保签包过，百分百成功，全国最低价，内部名额有限。';
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
    await new Promise((r) => setTimeout(r, 500));

    // 切到目标标签页（批量页要先把结果跑出来，才有表格式的文字）
    if (view.tab && view.tab !== 'single') {
      await page.evaluate((t) => {
        const btn = document.querySelector('.tabs__btn[data-tab="' + t + '"]');
        if (btn) btn.click();
      }, view.tab);
      await new Promise((r) => setTimeout(r, 300));
    }

    // 默认收起的 <details> 里的文字量不到，必须显式展开
    if (view.open) {
      await page.evaluate((id) => {
        const el = document.getElementById(id);
        if (el) el.open = true;
      }, view.open);
      await new Promise((r) => setTimeout(r, 250));
    }

    const rows = await page.evaluate(COLLECT);
    const fail = rows.filter((r) => r.cr < r.need);
    bad += fail.length;
    totalMeasured += rows.length;

    console.log('\n' + '='.repeat(62));
    console.log(`主题 ${theme} · ${view.name}：量了 ${rows.length} 处文字，不达标 ${fail.length} 处`);
    console.log('='.repeat(62));

    const list = SHOW_ALL
      ? rows.sort((a, b) => a.cr - b.cr)
      : fail.sort((a, b) => a.cr - b.cr);
    for (const r of list) {
      const mark = r.cr < r.need ? '✗' : '✓';
      console.log(mark + ' ' + String(r.cr).padEnd(6) + '需≥' + r.need +
        '  ' + String(r.size).padStart(5) + 'px  ' +
        r.sel.slice(0, 40).padEnd(42) +
        r.color + ' on ' + r.bg);
      if (r.cr < r.need) console.log('      「' + r.text + '」');
    }
    await page.close();
  }
}

await browser.close();

console.log('\n' + '='.repeat(62));
console.log(`共量 ${totalMeasured} 处文字（${themes.length} 主题 × ${VIEWS.length} 视图）`);
console.log(bad === 0
  ? '全部达标 ✓'
  : '共 ' + bad + ' 处未达 WCAG 2.1（正常文字 4.5:1 / 大字 3.0:1）');
console.log('='.repeat(62));
process.exit(bad === 0 ? 0 : 1);
