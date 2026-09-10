/**
 * 对拍执行器：读入语料 JSON，输出 JS 引擎的检测结果 JSON。
 * 由 scripts/verify_web_parity.py 调用，不单独使用。
 *
 * 用法： node scripts/js_parity_runner.js <corpus.json> <out.json>
 */
'use strict';

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
// eslint-disable-next-line no-eval
eval(fs.readFileSync(path.join(root, 'web/js/engine.js'), 'utf8'));

const corpusPath = process.argv[2];
const outPath = process.argv[3];
const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));
const data = JSON.parse(fs.readFileSync(path.join(root, 'web/data/rules.json'), 'utf8'));

const eng = new GuardianEngine(data);

const out = corpus.map(function (item) {
  const r = eng.detect(item.text, item.options || {});
  return {
    text: item.text,
    risk_level: r.summary.riskLevel,
    score: r.summary.score,
    counts: r.summary.counts,
    findings: r.findings.map(function (f) {
      return { matched: f.matchedText, severity: f.severity, match_type: f.matchType };
    }),
  };
});

fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('JS 侧完成：' + out.length + ' 条');
