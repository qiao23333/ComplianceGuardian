/**
 * 前端引擎冒烟测试（Node 环境，无需浏览器）
 *
 * 用法： node scripts/js_smoke.js
 *
 * 之所以能这样测：web/js/engine.js 不依赖任何 DOM API，
 * 核心是纯函数式匹配逻辑，因此可以直接在 Node 里跑，
 * 与 Python 端做逐例对拍（见 scripts/verify_web_parity.py）。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
// eslint-disable-next-line no-eval
eval(fs.readFileSync(path.join(root, 'web/js/engine.js'), 'utf8'));

const data = JSON.parse(fs.readFileSync(path.join(root, 'web/data/rules.json'), 'utf8'));
const eng = new GuardianEngine(data);

console.log('词库版本:', data.meta.engine, '| 规则数:', data.meta.rule_count);
console.log('严重度分布:', JSON.stringify(data.meta.by_severity));

// 来自中立语料 + 正样本的混合用例
const CASES = [
  // —— 应命中 ——
  ['这是最好的产品，全网最低价', true],
  ['加我薇信，拉你进群', true],
  ['加我微信', true],
  ['加卫星，我发你资料', true],
  ['保证下签，零拒签', true],
  ['保录取，名校保录', true],
  ['全 网 最 低 价', true],
  ['最好的服務', true],
  ['史上最强产品', true],
  // —— 不应命中（误报治理）——
  ['微信支付很方便', false],
  ['关注我们的微信公众号', false],
  ['澳洲雇主担保签证的基本要求', false],
  ['我最近最后还是用了这个方案', false],
  ['专注澳洲技术移民与投资移民服务', false],
  ['高考后留学澳洲的几种路径', false],
  ['普通分享，无违规内容', false],
  ['这个和那个有关系吗', false],
];

let pass = 0;
let fail = 0;

for (const [text, shouldHit] of CASES) {
  const r = eng.detect(text);
  const hit = r.findings.length > 0;
  const ok = hit === shouldHit;
  if (ok) pass += 1; else fail += 1;
  const hits = r.findings
    .map((f) => `${f.matchedText}(${f.severity}/${f.matchType})`)
    .join(', ');
  console.log(
    `  ${ok ? 'PASS' : 'FAIL'}  ${shouldHit ? '应命中' : '应干净'}  ${text}`
    + `  →  ${r.summary.riskLevel}${hits ? ' [' + hits + ']' : ''}`
    + `  ${r.meta.elapsedMs}ms`
  );
}

console.log(`\n冒烟结果：${pass} 通过 / ${fail} 失败`);

// 性能：两万字长文
const long = '这是一段很长的营销文案，包含一些正常内容。'.repeat(500);
const t0 = Date.now();
const rr = eng.detect(long);
console.log(`性能：${long.length} 字，耗时 ${Date.now() - t0} ms，命中 ${rr.findings.length} 条`);

process.exit(fail === 0 ? 0 : 1);
