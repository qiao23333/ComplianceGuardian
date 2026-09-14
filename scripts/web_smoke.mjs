#!/usr/bin/env node
/**
 * 合规卫士 · Web 体验页冒烟测试
 * ============================================================
 *
 * 为什么需要这个脚本
 * ------------------
 * web/ 是纯前端（无构建、无依赖、无后端），好处是双击就能跑，代价是
 * **没有任何编译期检查**：DOM id 写错、函数名拼错、字段路径不对，
 * 页面只会安静地什么都不做——不报错、不白屏，就是没反应。
 *
 * 这类问题靠读代码很难发现（尤其改动跨越 index.html / app.js / engine.js
 * 三个文件时）。所以改完 Web 端必须用真实浏览器跑一遍，看它到底动没动。
 *
 * 它检查的不是"好不好看"，而是"活没活着"：
 *   1. 有没有 JS 报错（含 pageerror 与 console.error）
 *   2. 词库是否加载、规则数是否渲染出来
 *   3. 粘文案 → 是否有命中、分数是否变化
 *   4. 跨平台矩阵是否有内容（三行，且三平台分数口径正确）
 *   5. AI 改写区是否出现、复制指令内容是否包含清单与约束
 *   6. 底部差异区的统计数字是否被真实词库数据填上（不是占位符 …）
 *   7. 演示按钮点了之后输入框是否真被填充
 *
 * 用法
 * ----
 *   # 先起静态服务（web/ 是纯静态，任意 http server 都行）
 *   cd web && python -m http.server 8923 --bind 127.0.0.1
 *
 *   node scripts/web_smoke.mjs
 *   BASE_URL=http://127.0.0.1:8923/index.html node scripts/web_smoke.mjs
 *
 * 依赖：本机 Chrome + puppeteer-core（从 xuanlan 项目的 node_modules 借用，
 * 避免在本项目里塞一个几百 MB 的依赖树）。
 */

import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import fs from 'node:fs';

const PUPPETEER_ROOT = process.env.PUPPETEER_ROOT || 'G:/work/牛马/wb工作空间/xuanlan';
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8923/index.html';
const SHOT_DIR = process.env.SHOT_DIR || '.tmp-web';

const require = createRequire(pathToFileURL(PUPPETEER_ROOT.replace(/\\/g, '/') + '/'));
let puppeteer;
try {
  puppeteer = require('puppeteer-core');
} catch (e) {
  console.error('无法加载 puppeteer-core。请设置 PUPPETEER_ROOT 指向含 node_modules 的目录。');
  console.error('   当前：' + PUPPETEER_ROOT);
  process.exit(2);
}

// ============================================================ 断言脚手架

let pass = 0;
const failures = [];

function check(name, ok, detail) {
  if (ok) {
    pass++;
    console.log('  \u2713 ' + name);
  } else {
    failures.push(name + (detail ? '  → ' + detail : ''));
    console.log('  \u2717 ' + name + (detail ? '  → ' + detail : ''));
  }
}

// ============================================================ 主流程

const jsErrors = [];
const consoleErrors = [];

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1000 });

  page.on('pageerror', (e) => jsErrors.push(String(e && e.message ? e.message : e)));
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });

  console.log('\n[1] 加载页面 ' + BASE);
  await page.goto(BASE, { waitUntil: 'load', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 600));

  check('页面无 JS 运行时错误', jsErrors.length === 0, jsErrors.join(' | '));
  check('无 console.error', consoleErrors.length === 0, consoleErrors.join(' | '));

  // ---- 词库与引擎 ----
  console.log('\n[2] 词库与引擎');
  const boot = await page.evaluate(() => ({
    hasRules: typeof window.GUARDIAN_RULES === 'object' && !!window.GUARDIAN_RULES,
    ruleCount: (window.GUARDIAN_RULES && window.GUARDIAN_RULES.rules || []).length,
    hasEngine: typeof window.GuardianEngine === 'function',
    heroCount: (document.getElementById('heroRuleCount') || {}).textContent,
    engineInfo: (document.getElementById('engineInfo') || {}).textContent,
  }));
  check('词库已加载', boot.hasRules && boot.ruleCount > 0, '规则数=' + boot.ruleCount);
  check('引擎构造函数存在', boot.hasEngine);
  check('页面显示规则数（不是占位符）',
    boot.heroCount && boot.heroCount !== '\u2026' && boot.heroCount !== '…',
    'heroRuleCount=' + boot.heroCount);

  // ---- 点样例出结果 ----
  console.log('\n[3] 检测主流程');
  await page.click('.chip[data-sample="0"]');
  await new Promise((r) => setTimeout(r, 500));
  const r1 = await page.evaluate(() => ({
    score: (document.getElementById('scoreNum') || {}).textContent,
    findings: document.querySelectorAll('#findings .finding').length,
    preview: !document.getElementById('preview').hidden,
    counter: (document.getElementById('counter') || {}).textContent,
  }));
  check('高危样例有命中', r1.findings > 0, '命中 ' + r1.findings + ' 处');
  check('合规分已下降到 100 以下', Number(r1.score) < 100, 'score=' + r1.score);
  check('全文高亮预览出现', r1.preview);

  // ---- 跨平台矩阵 ----
  console.log('\n[4] 跨平台对比矩阵');
  const mx = await page.evaluate(() => {
    const box = document.getElementById('matrixBox');
    return {
      hidden: box.hidden,
      rows: box.querySelectorAll('tbody tr').length,
      verdict: (box.querySelector('.matrix__verdict') || {}).textContent || '',
      cells: Array.from(box.querySelectorAll('tbody tr')).map((tr) =>
        Array.from(tr.querySelectorAll('td')).map((td) => td.textContent.trim())),
    };
  });
  check('矩阵区可见', !mx.hidden);
  check('矩阵有 3 个平台行', mx.rows === 3, '实际 ' + mx.rows + ' 行');
  check('矩阵给出结论', mx.verdict.length > 10, mx.verdict.slice(0, 40) + '…');
  // 三平台同分时必须说“一致”，不能谎报某平台最低
  {
    const scores = mx.cells.map((c) => Number(c[1]));
    const uniq = Array.from(new Set(scores));
    if (uniq.length === 1) {
      check('三平台同分时结论说“一致”而非“某平台最严”',
        mx.verdict.includes('一致'), mx.verdict.slice(0, 50));
    } else {
      const min = Math.min(...scores);
      const strictest = mx.cells.filter((c) => Number(c[1]) === min).map((c) => c[0]);
      check('存在差异时点名最严平台',
        strictest.some((s) => mx.verdict.includes(s)),
        '最严=' + strictest.join('/') + ' 结论=' + mx.verdict.slice(0, 50));
    }
  }

  // ---- 平台差异演示 ----
  console.log('\n[5] 平台差异演示（同一句话，三平台三种结论）');
  await page.click('.dcard__demo[data-demo="platform"]');
  await new Promise((r) => setTimeout(r, 600));
  const plat = await page.evaluate(() => {
    const box = document.getElementById('matrixBox');
    const rows = Array.from(box.querySelectorAll('tbody tr')).map((tr) => ({
      label: tr.querySelectorAll('td')[0].textContent.trim(),
      score: Number(tr.querySelectorAll('td')[1].textContent.trim()),
      only: tr.querySelectorAll('td')[4].textContent.trim(),
    }));
    return {
      input: document.getElementById('input').value,
      rows,
      verdict: (box.querySelector('.matrix__verdict') || {}).textContent || '',
    };
  });
  check('演示文案已填入输入框', plat.input.includes('加微信'), plat.input.slice(0, 24));
  {
    const sc = plat.rows.map((r) => r.score);
    check('三平台分数出现差异（这就是“分平台”的价值）',
      new Set(sc).size > 1, '分数=' + sc.join('/'));
    const xhs = plat.rows.find((r) => r.label.includes('小红书'));
    const wx = plat.rows.find((r) => r.label.includes('微信'));
    // 真实数据：同是「加微信」，小红书/抖音判高危，微信只判中危 → 分数必然不同
    check('同词不同罚：小红书比微信判得更重',
      !!xhs && !!wx && xhs.score < wx.score,
      xhs && wx ? '小红书 ' + xhs.score + ' vs 微信 ' + wx.score : '缺行');
    check('差异列点出了差异来源（不是笼统说“一致”）',
      !!xhs && !xhs.only.includes('与其他平台一致'),
      xhs ? xhs.only.slice(0, 60) : '缺行');
  }

  // 有检测结果时的截图（矩阵 + AI 区都在这一刻才出现）
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.evaluate(() => {
    const el = document.getElementById('matrixBox');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'start' });
    window.scrollBy(0, -70);
  });
  await new Promise((r) => setTimeout(r, 350));
  await page.screenshot({ path: SHOT_DIR + '/web-result.png' });

  // ---- AI 改写区 ----
  console.log('\n[6] AI 改写区');  const ai = await page.evaluate(() => {
    const box = document.getElementById('aiBox');
    return {
      hidden: box.hidden,
      hasCopy: !!document.getElementById('aiCopyBtn'),
      text: box.textContent || '',
    };
  });
  check('AI 改写区可见', !ai.hidden);
  check('有“复制 AI 改写指令”按钮', ai.hasCopy);
  check('说明了“判定不交给 AI”', ai.text.includes('判定不能交给它') || ai.text.includes('判定不交给'));

  // 页面没有把 lastResult 暴露到 window，这里用引擎自己跑一次拿 findings。
  // 好处是顺带验证了"引擎在页面里能被正常实例化和调用"这件事。
  const promptReal = await page.evaluate(() => {
    const eng = new window.GuardianEngine(window.GUARDIAN_RULES);
    const text = document.getElementById('input').value;
    const res = eng.detect(text, {
      platform: 'all', accountType: 'non_blue_v',
      industries: ['immigration', 'study_abroad'], useVariants: true, autoReplace: false,
    });
    return window.GuardianEngine.buildRewritePrompt(text, res.findings, {
      platform: 'all', accountType: 'non_blue_v', industryLabel: '移民 + 留学',
    });
  });
  check('提示词含“不要做合规判定”', promptReal.includes('不要做合规判定'));
  check('提示词含违规清单条目', /命中「.+」/.test(promptReal));
  check('提示词含输出 JSON 契约', promptReal.includes('"rewritten"') && promptReal.includes('"unresolved"'));
  check('提示词含待改写原文', promptReal.includes('待改写原文'));

  // ---- 底部差异区 ----
  console.log('\n[7] 差异说明区（作品自证）');
  const diff = await page.evaluate(() => {
    const g = (id) => ((document.getElementById(id) || {}).textContent || '').trim();
    return {
      cards: document.querySelectorAll('.dcard').length,
      platform: g('dPlatform'),
      platforms: g('dPlatforms'),
      imm: g('dImm'),
      study: g('dStudy'),
      blueV: g('dBlueV'),
    };
  });
  check('四张差异卡片都在', diff.cards === 4, '实际 ' + diff.cards);
  check('平台专属规则数已填真实值', /^\d+$/.test(diff.platform) && Number(diff.platform) > 0,
    'dPlatform=' + diff.platform);
  check('覆盖平台数已填', diff.platforms === '3', 'dPlatforms=' + diff.platforms);
  check('移民规则数已填', /^\d+$/.test(diff.imm) && Number(diff.imm) > 0, 'dImm=' + diff.imm);
  check('留学规则数已填', /^\d+$/.test(diff.study) && Number(diff.study) > 0, 'dStudy=' + diff.study);
  check('蓝V定级差异数已填', /^\d+$/.test(diff.blueV) && Number(diff.blueV) > 0,
    'dBlueV=' + diff.blueV);

  // ---- 浅色主题 ----
  console.log('\n[8] 主题与响应式');
  await page.click('#themeBtn');
  await new Promise((r) => setTimeout(r, 300));
  const theme = await page.evaluate(() => ({
    attr: document.documentElement.getAttribute('data-theme'),
    bg: getComputedStyle(document.body).backgroundColor,
  }));
  check('可切到浅色主题', theme.attr === 'light', 'theme=' + theme.attr);
  await page.click('#themeBtn');
  await new Promise((r) => setTimeout(r, 300));

  // 移动端横向溢出
  await page.setViewport({ width: 390, height: 844, isMobile: true });
  await new Promise((r) => setTimeout(r, 400));
  const overflow = await page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
  }));
  check('移动端无横向溢出',
    overflow.scrollW <= overflow.clientW + 1,
    'scrollW=' + overflow.scrollW + ' clientW=' + overflow.clientW);

  // ---- 截图 ----
  console.log('\n[9] 截图');
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.setViewport({ width: 1440, height: 1200 });
  await new Promise((r) => setTimeout(r, 400));
  await page.screenshot({ path: SHOT_DIR + '/web-desktop.png' });
  await page.setViewport({ width: 390, height: 844, isMobile: true });
  await new Promise((r) => setTimeout(r, 400));
  await page.screenshot({ path: SHOT_DIR + '/web-mobile.png', fullPage: true });
  check('截图已生成', fs.existsSync(SHOT_DIR + '/web-desktop.png'));

  // ---- 汇总 ----
  console.log('\n' + '='.repeat(56));
  if (failures.length) {
    console.log('失败 ' + failures.length + ' 项 / 通过 ' + pass + ' 项\n');
    failures.forEach((f) => console.log('  \u2717 ' + f));
    console.log('='.repeat(56) + '\n');
    process.exitCode = 1;
  } else {
    console.log('全部通过：' + pass + ' 项');
    console.log('截图：' + SHOT_DIR + '/web-desktop.png, web-mobile.png');
    console.log('='.repeat(56) + '\n');
  }
} catch (err) {
  console.error('\n脚本异常：', err);
  process.exitCode = 3;
} finally {
  await browser.close();
}
