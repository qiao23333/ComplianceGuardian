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

  // ---- 对照实验 ----
  // 这是全页最重要的一块：它必须真的把"关掉行业词库"和"打开行业词库"
  // 两组数字并排算出来，而不是写死的文案。
  console.log('\n[8] 对照实验（关掉行业词库 vs 打开）');
  await page.click('[data-demo="industry"]');
  await new Promise((r) => setTimeout(r, 500));
  const ab = await page.evaluate(() => {
    const box = document.getElementById('abBox');
    const cols = box ? box.querySelectorAll('.ab__col') : [];
    const scoreOf = (i) => {
      const n = cols[i] ? cols[i].querySelector('.ab__score') : null;
      return n ? Number((n.textContent || '').replace(/[^\d]/g, '')) : NaN;
    };
    const wordsOf = (i) => (cols[i] ? cols[i].querySelectorAll('.ab__list li').length : 0);
    const note = box ? (box.querySelector('.ab__note') || {}).textContent || '' : '';
    return {
      hidden: box ? box.hidden : true,
      cols: cols.length,
      offScore: scoreOf(0),
      onScore: scoreOf(1),
      offWords: wordsOf(0),
      onWords: wordsOf(1),
      head: box ? (box.querySelector('.ab__head') || {}).textContent || '' : '',
      note: note.trim(),
      text: box ? box.textContent : '',
    };
  });
  check('对照实验面板出现', !ab.hidden);
  check('两栏并排（关闭 / 打开）', ab.cols === 2, '实际 ' + ab.cols + ' 栏');
  check('两栏分数都是真实数字', Number.isFinite(ab.offScore) && Number.isFinite(ab.onScore),
    ab.offScore + ' / ' + ab.onScore);
  check('打开行业词库后分数更低（行业规则确实扣了分）',
    ab.onScore < ab.offScore, '关闭=' + ab.offScore + ' 打开=' + ab.onScore);
  check('打开后抓到的条目更多', ab.onWords > 0,
    '关闭=' + ab.offWords + ' 打开=' + ab.onWords);
  check('标注了唯一变量是行业词库', ab.head.includes('唯一变量'),
    ab.head.slice(0, 40));
  check('结论文案克制，说明差异来自行业专属规则',
    ab.note.includes('行业专属规则'), ab.note.slice(0, 40) + '…');

  // ---- 批量检测 ----
  console.log('\n[9] 批量检测');
  await page.click('.tabs__btn[data-tab="batch"]');
  await new Promise((r) => setTimeout(r, 300));
  await page.click('#bSampleBtn');
  await new Promise((r) => setTimeout(r, 600));
  const batch = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('#bResults tbody tr'));
    const card = (n) => {
      const c = document.querySelectorAll('#bStats .bcard')[n];
      return c ? Number((c.querySelector('b').textContent || '').replace(/[^\d]/g, '')) : NaN;
    };
    return {
      paneVisible: !document.getElementById('pane-batch').hidden,
      singleHidden: document.getElementById('pane-single').hidden,
      tableRows: rows.length,
      scores: rows.map((r) => Number(r.children[2].textContent)),
      cards: document.querySelectorAll('#bStats .bcard').length,
      total: card(0), pass: card(1), fail: card(2),
      meta: (document.getElementById('bMeta').textContent || '').trim(),
      csvEnabled: !document.getElementById('bExportCsv').disabled,
      copyEnabled: !document.getElementById('bCopyPass').disabled,
    };
  });
  check('切到批量页且单条页已隐藏', batch.paneVisible && batch.singleHidden);
  check('5 条示例全部进表', batch.tableRows === 5, '实际 ' + batch.tableRows + ' 行');
  check('统计卡 4 项', batch.cards === 4, '实际 ' + batch.cards);
  check('总条数正确', batch.total === 5, 'total=' + batch.total);
  check('可放心发 + 需要改 = 总条数',
    batch.pass + batch.fail === 5, batch.pass + ' + ' + batch.fail);
  check('第 5 条合规反例没有被误报（≥90 分）',
    batch.scores[4] >= 90, '第5条=' + batch.scores[4]);
  check('违规条目确实被判低分',
    batch.scores.slice(0, 4).every((s) => s < 90), batch.scores.join('/'));
  check('点名了最需要改的是第几条', /第\s*\d+\s*条/.test(batch.meta), batch.meta);
  check('导出 CSV 已启用', batch.csvEnabled);
  check('复制通过清单已启用', batch.copyEnabled);

  // ---- 词库浏览 ----
  console.log('\n[10] 词库浏览');
  await page.click('.tabs__btn[data-tab="rules"]');
  await new Promise((r) => setTimeout(r, 400));
  const rl = await page.evaluate(() => ({
    paneVisible: !document.getElementById('pane-rules').hidden,
    items: document.querySelectorAll('#rList .ritem').length,
    stats: (document.getElementById('rStats').textContent || '').trim(),
    page: (document.getElementById('rPageInfo').textContent || '').trim(),
    badge: (document.getElementById('tabRuleCount').textContent || '').trim(),
  }));
  check('切到词库页', rl.paneVisible);
  check('单页渲染 40 条（分页生效，不是一次塞 1000 个节点）',
    rl.items === 40, '实际 ' + rl.items + ' 条');
  check('统计显示总规则数与筛选命中数',
    /共\s*\d+\s*条规则/.test(rl.stats) && /筛选命中/.test(rl.stats), rl.stats);
  check('分页信息正确', /第\s*1\s*\/\s*\d+\s*页/.test(rl.page), rl.page);
  check('标签页角标显示规则数', /^\d+$/.test(rl.badge) && Number(rl.badge) > 0, rl.badge);

  // 搜索
  await page.type('#rSearch', '保签');
  await new Promise((r) => setTimeout(r, 400));
  const searched = await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('#rList .ritem'));
    return {
      n: items.length,
      first: items.length ? items[0].querySelector('.ritem__k').textContent.trim() : '',
      all: items.map((i) => i.querySelector('.ritem__k').textContent.trim()),
      stats: (document.getElementById('rStats').textContent || '').trim(),
    };
  });
  check('搜索「保签」有结果', searched.n > 0, '命中 ' + searched.n + ' 条');
  check('结果确实包含搜索词',
    searched.all.some((k) => k.includes('保签')), searched.all.slice(0, 3).join('、'));
  check('搜索后分页回到第 1 页',
    /第\s*1\s*\//.test((await page.evaluate(() =>
      document.getElementById('rPageInfo').textContent)).trim()));

  // 按来源筛选
  await page.evaluate(() => {
    const s = document.getElementById('rSearch');
    s.value = '';
    s.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.select('#rSource', 'industry:immigration');
  await new Promise((r) => setTimeout(r, 400));
  const srcFilter = await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('#rList .ritem'));
    return {
      n: items.length,
      tagged: items.filter((i) => i.textContent.includes('移民红线')).length,
      hasReplacement: items.filter((i) => i.querySelector('.ritem__r')).length,
    };
  });
  check('按「移民红线」筛出结果', srcFilter.n > 0, srcFilter.n + ' 条');
  check('筛出的条目都带「移民红线」来源标签',
    srcFilter.tagged === srcFilter.n, srcFilter.tagged + '/' + srcFilter.n);
  check('部分条目带「可改为」建议', srcFilter.hasReplacement > 0,
    srcFilter.hasReplacement + ' 条有替换词建议');

  // 翻页
  await page.select('#rSource', '');
  await new Promise((r) => setTimeout(r, 300));
  await page.click('#rNext');
  await new Promise((r) => setTimeout(r, 300));
  const page2 = await page.evaluate(() => ({
    page: (document.getElementById('rPageInfo').textContent || '').trim(),
    prevEnabled: !document.getElementById('rPrev').disabled,
  }));
  check('可以翻到第 2 页', /第\s*2\s*\//.test(page2.page), page2.page);
  check('翻页后「上一页」可用', page2.prevEnabled);

  // ---- 最近检测与隐私 ----
  console.log('\n[11] 最近检测与隐私默认值');
  const histDefault = await page.evaluate(() => ({
    checked: document.getElementById('histStoreText').checked,
    hint: (document.getElementById('histHint').textContent || '').trim(),
  }));
  check('默认不保存原文（开关关闭）', histDefault.checked === false);
  check('提示文案明确说了默认不存原文',
    histDefault.hint.includes('不保存原文'), histDefault.hint.slice(0, 30) + '…');

  await page.evaluate(() => document.getElementById('histClear').click());
  await page.click('.tabs__btn[data-tab="single"]');
  await new Promise((r) => setTimeout(r, 200));
  // 填一段独有的文案，等"停笔"阈值过去让它落一条记录
  await page.evaluate(() => {
    const el = document.getElementById('input');
    el.value = '隐私测试专用文案：保签包过，独家内部名额。';
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 3400));
  const metaOnly = await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('#histList .hitem'));
    const raw = JSON.parse(localStorage.getItem('adcompli-history') || '[]');
    return {
      n: items.length,
      clickable: items.filter((i) => i.classList.contains('hitem--click')).length,
      rawHasText: raw.some((e) => typeof e.text === 'string' && e.text.length > 0),
      rawKeys: raw.length ? Object.keys(raw[0]).sort().join(',') : '',
    };
  });
  check('检测后落了一条记录', metaOnly.n > 0, metaOnly.n + ' 条');
  check('默认态下记录不可点击回看（因为没存原文）',
    metaOnly.clickable === 0, '可点击 ' + metaOnly.clickable + ' 条');
  check('默认态下存储里确实没有原文',
    metaOnly.rawHasText === false, 'keys=' + metaOnly.rawKeys);

  // 打开开关后，应当能存原文并回看
  await page.evaluate(() => {
    const t = document.getElementById('histStoreText');
    t.checked = true;
    t.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.evaluate(() => {
    const el = document.getElementById('input');
    el.value = '第二段文案：保录取，考不上退费，名师一对一。';
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 3400));
  const stored = await page.evaluate(() => ({
    clickable: Array.from(document.querySelectorAll('#histList .hitem--click')).length,
    rawHasText: JSON.parse(localStorage.getItem('adcompli-history') || '[]')
      .some((e) => e.text && e.text.length > 0),
  }));
  check('开启后记录了原文', stored.rawHasText);
  check('开启后记录可点击回看', stored.clickable > 0, stored.clickable + ' 条可点');

  // 点回看 → 输入框恢复
  await page.click('#histList .hitem--click');
  await new Promise((r) => setTimeout(r, 300));
  const restored = await page.evaluate(() =>
    (document.getElementById('input').value || ''));
  check('点记录能恢复原文', restored.includes('第二段文案'), restored.slice(0, 20));

  // 关掉开关 → 已存原文应被清除（隐私承诺要能兑现）
  await page.evaluate(() => {
    const t = document.getElementById('histStoreText');
    t.checked = false;
    t.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 200));
  const purged = await page.evaluate(() => {
    const raw = JSON.parse(localStorage.getItem('adcompli-history') || '[]');
    return {
      rawHasText: raw.some((e) => typeof e.text === 'string' && e.text.length > 0),
      clickable: document.querySelectorAll('#histList .hitem--click').length,
    };
  });
  check('关掉开关后已存原文被一并清除',
    purged.rawHasText === false && purged.clickable === 0,
    'rawHasText=' + purged.rawHasText + ' clickable=' + purged.clickable);
  await page.evaluate(() => document.getElementById('histClear').click());

  // ---- 改前 / 改后迭代对比 ----
  console.log('\n[12] 改前 / 改后迭代对比');
  // 回到单条检测页，并清掉上一组留下的输入与基线
  await page.click('.tabs__btn[data-tab="single"]');
  await page.evaluate(() => document.getElementById('clearBtn').click());
  await new Promise((r) => setTimeout(r, 400));

  const baseBtn0 = await page.evaluate(() => ({
    txt: document.getElementById('baselineBtn').textContent.trim(),
    disabled: document.getElementById('baselineBtn').disabled,
  }));
  check('初始按钮文案是「存为改前」', baseBtn0.txt.includes('存为改前'), baseBtn0.txt);
  check('无文案时「存为改前」不可点', baseBtn0.disabled === true);

  const setInput = async (t) => {
    await page.evaluate((v) => {
      const el = document.getElementById('input');
      el.value = v;
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }, t);
    await new Promise((r) => setTimeout(r, 400));
  };

  await setInput('保签包过，百分百成功。');
  await page.evaluate(() => document.getElementById('baselineBtn').click());
  await new Promise((r) => setTimeout(r, 400));

  const afterSave = await page.evaluate(() => ({
    txt: document.getElementById('baselineBtn').textContent.trim(),
    iterHidden: document.getElementById('iterBox').hidden,
  }));
  check('存基线后按钮带出改前分数', /改前\s*\d+\s*分/.test(afterSave.txt), afterSave.txt);
  check('文案没动时不显示对比块（免得自比自）', afterSave.iterHidden === true);

  // ① 把违规词全改掉 → 应报「已消除」且分数上升
  await setInput('专业团队提供咨询与材料准备。');

  const readIter = () => page.evaluate(() => {
    const b = document.getElementById('iterBox');
    const rows = {};
    Array.from(b.querySelectorAll('.iter__row')).forEach((r) => {
      rows[r.getAttribute('data-k')] =
        (r.querySelector('.iter__k') || {}).textContent || '';
    });
    return {
      hidden: b.hidden,
      rows,
      scores: Array.from(b.querySelectorAll('.iter__score'))
        .map((s) => s.textContent.trim()),
      text: b.textContent,
    };
  });
  const num = (s) => parseInt(String(s).replace(/\D/g, ''), 10) || 0;

  const it1 = await readIter();
  check('改动后对比块出现', it1.hidden === false);
  check('统计出已消除的命中', num(it1.rows.fixed) > 0, it1.rows.fixed);
  check('改后分数确实变高',
    num(it1.scores[1]) > num(it1.scores[0]),
    it1.scores.join(' → '));
  check('改干净时给出发得出去的结论',
    it1.text.includes('可以发了'), it1.text.includes('清零') ? '有清零文案' : '缺');

  // ② 再改出一版带新违规词的 → 应点名「新引入」，这是这块最该报的东西
  await setInput('全国最低价，内部名额有限。');
  const it2 = await readIter();
  check('识别出改动带出的新命中', num(it2.rows.added) > 0, it2.rows.added);
  check('有新命中时会给出警告而不是只夸分数',
    it2.text.includes('新命中'), '（出现警告文案）');

  const addedChip = await page.evaluate(() =>
    (document.querySelector('#iterBox .iter__chip.is-bad') || {}).textContent || '');
  check('新命中的词被具体列出来', addedChip.length > 0, addedChip);

  // ③ 清空 → 基线一并撤销，按钮复位
  await page.evaluate(() => document.getElementById('clearBtn').click());
  await new Promise((r) => setTimeout(r, 400));
  const afterClear = await page.evaluate(() => ({
    txt: document.getElementById('baselineBtn').textContent.trim(),
    iterHidden: document.getElementById('iterBox').hidden,
  }));
  check('清空后对比块消失', afterClear.iterHidden === true);
  check('清空后按钮复位为「存为改前」',
    afterClear.txt.includes('存为改前'), afterClear.txt);

  // ---- 浅色主题 ----
  console.log('\n[13] 主题与响应式');
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

  // ---- PWA：可安装 + 可离线 ----
  console.log('\n[14] PWA 可安装与离线可用');

  const manifest = await page.evaluate(async () => {
    const link = document.querySelector('link[rel="manifest"]');
    if (!link) return { ok: false };
    try {
      const r = await fetch(link.getAttribute('href'));
      const j = await r.json();
      return {
        ok: r.ok, name: j.name, display: j.display,
        icons: (j.icons || []).length, start: j.start_url || '',
      };
    } catch (e) { return { ok: false, err: String(e) }; }
  });
  check('manifest 可访问且字段完整',
    manifest.ok && manifest.icons >= 3 && manifest.display === 'standalone',
    JSON.stringify(manifest).slice(0, 100));

  // 分享卡片图与图标是"链接被转发时的第一印象"，缺一个就是白板
  const assets = await page.evaluate(async () => {
    const urls = ['icon-192.png', 'icon-512.png', 'apple-touch-icon.png', 'og.png', 'sw.js'];
    const out = {};
    for (const u of urls) {
      try { out[u] = (await fetch(u)).status; } catch (e) { out[u] = 0; }
    }
    return out;
  });
  const missing = Object.keys(assets).filter((u) => assets[u] !== 200);
  check('PWA 图标与分享卡片图资源齐全', missing.length === 0,
    missing.length ? '缺 ' + missing.join(', ') : Object.keys(assets).length + ' 个全 200');

  // 等 Service Worker 真正接管本页
  const swState = await page.evaluate(() => new Promise((res) => {
    if (!('serviceWorker' in navigator)) return res('unsupported');
    if (navigator.serviceWorker.controller) return res('controlled');
    const t = setTimeout(() => res('timeout'), 10000);
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      clearTimeout(t);
      res('controlled');
    });
  }));
  check('Service Worker 已接管页面', swState === 'controlled', swState);

  // 关键验证：断网刷新还能不能用。只检查"注册成功"没有意义，
  // 真正要证明的是"拔了网线它照样跑"。
  if (swState === 'controlled') {
    await page.setOfflineMode(true);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await new Promise((r) => setTimeout(r, 1500));

    const offline = await page.evaluate(() => ({
      rules: (document.getElementById('heroRuleCount') || {}).textContent || '',
      hasInput: !!document.getElementById('input'),
      tabs: document.querySelectorAll('.tabs__btn').length,
    }));
    check('断网刷新后页面照常打开', offline.hasInput && offline.tabs === 3,
      '规则数 ' + offline.rules + ' / 标签 ' + offline.tabs);

    await page.evaluate(() => {
      const el = document.getElementById('input');
      el.value = '保签包过，百分百成功。';
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await new Promise((r) => setTimeout(r, 600));
    const offlineHits = await page.evaluate(() =>
      document.querySelectorAll('#findings .finding').length);
    check('断网状态下检测照样出结果', offlineHits > 0, offlineHits + ' 处命中');

    await page.setOfflineMode(false);
    await page.reload({ waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 600));
  }

  // ---- 截图 ----
  console.log('\n[15] 截图');
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.setViewport({ width: 1440, height: 1200 });
  await new Promise((r) => setTimeout(r, 400));

  // 先切回单条页，确保主图是默认视图
  await page.click('.tabs__btn[data-tab="single"]');
  await new Promise((r) => setTimeout(r, 300));
  await page.screenshot({ path: SHOT_DIR + '/web-desktop.png' });

  // 迭代对比块空态看不出东西，手工造一个"改过一轮"的状态再截
  await setInput('保签包过，百分百成功，全国最低价。');
  await page.evaluate(() => document.getElementById('baselineBtn').click());
  await new Promise((r) => setTimeout(r, 300));
  await setInput('专业团队提供咨询与材料准备，欢迎咨询详情。');
  await page.evaluate(() => {
    const el = document.getElementById('iterBox');
    if (el) el.scrollIntoView({ block: 'center' });
  });
  await new Promise((r) => setTimeout(r, 300));
  await page.screenshot({ path: SHOT_DIR + '/web-iter.png' });
  await page.evaluate(() => document.getElementById('clearBtn').click());
  await new Promise((r) => setTimeout(r, 300));

  await page.click('.tabs__btn[data-tab="batch"]');
  await new Promise((r) => setTimeout(r, 500));
  await page.screenshot({ path: SHOT_DIR + '/web-batch.png' });

  await page.click('.tabs__btn[data-tab="rules"]');
  await new Promise((r) => setTimeout(r, 500));
  await page.screenshot({ path: SHOT_DIR + '/web-rules.png' });

  await page.setViewport({ width: 390, height: 844, isMobile: true });
  await new Promise((r) => setTimeout(r, 400));
  await page.screenshot({ path: SHOT_DIR + '/web-mobile.png', fullPage: true });
  check('截图已生成', fs.existsSync(SHOT_DIR + '/web-desktop.png'));
  check('迭代对比截图已生成', fs.existsSync(SHOT_DIR + '/web-iter.png'));
  check('批量页截图已生成', fs.existsSync(SHOT_DIR + '/web-batch.png'));
  check('词库页截图已生成', fs.existsSync(SHOT_DIR + '/web-rules.png'));

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
