/**
 * Web 体验页 · 示例文案验收
 * ============================================================
 *
 * 为什么单独写这个脚本
 * --------------------
 * 页面上有 4 个"试一下"按钮。如果示例的实际表现和按钮暗示的不一致
 * （比如写着"合规文案（应 0 命中）"却报了 3 条），那页面就是在骗人，
 * 作品集里最不能出的就是这个错。本脚本按**页面默认选项**跑这 4 条，
 * 并把断言写死，任何一次词库调整导致的偏差都会被立刻发现。
 *
 * 用法：
 *   node scripts/verify_web_page_demo.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');

// rules.js 是浏览器脚本（挂 window.GUARDIAN_RULES），node 里补一个 window 垫片
global.window = global;
// eslint-disable-next-line no-eval
eval(fs.readFileSync(path.join(root, 'web/data/rules.js'), 'utf8'));
// eslint-disable-next-line no-eval
eval(fs.readFileSync(path.join(root, 'web/js/engine.js'), 'utf8'));

const data = global.GUARDIAN_RULES;
const eng = new global.GuardianEngine(data);

// 与 web/js/app.js 的 SAMPLES / currentOptions() 默认值保持一致
const DEFAULTS = {
  platform: 'all',
  accountType: 'non_blue_v',
  industries: ['immigration', 'study_abroad'],
  useVariants: true,
  autoReplace: false,
};

const SAMPLES = [
  {
    name: '移民 · 高危违规',
    text: [
      '澳洲雇主担保移民，官方授权渠道，包安排雇主，无需英语、无需工作经验。',
      '保签不过全额退款，成功率 100%，全网最低价，名额有限先到先得。',
    ].join('\n'),
    check: (r) => {
      const sevs = r.findings.map((f) => f.severity);
      return {
        ok: r.findings.length >= 3 && sevs.includes('critical'),
        why: '应命中 ≥3 处且至少 1 处高危',
      };
    },
  },
  {
    name: '规避写法演示',
    text: '全网最低價！加薇芯詳聊，保 签 包 过，不过全额退款，成功率１００％，本公司首创该模式。',
    check: (r) => {
      const variants = r.findings.filter((f) => f.matchType === 'variant');
      return {
        ok: variants.length >= 3,
        why: '应识别 ≥3 处变体（繁体 / 谐音 / 跳字 / 全角）',
      };
    },
  },
  {
    name: '留学 · 承诺类',
    text: '留学申请保录取，考不上全额退费。名师一对一，短期提分保过，内部招生名额有限。',
    check: (r) => ({
      ok: r.findings.length >= 2,
      why: '应命中 ≥2 处',
    }),
  },
  {
    name: '合规文案（应 0 命中）',
    text: [
      '澳洲雇主担保移民项目说明会将于本月举行，欢迎有兴趣的朋友了解详情。',
      '我们会结合您的学历、工作经历和语言情况，评估可行的签证路径，并提供材料准备方面的建议。',
    ].join('\n'),
    check: (r) => ({
      ok: r.findings.length === 0,
      why: '必须 0 命中 —— 这是误报率的照妖镜',
    }),
  },
];

let pass = 0;
let fail = 0;

console.log('词库版本: ' + (data.meta && data.meta.engine) +
  ' | 规则数: ' + data.rules.length + '\n');

SAMPLES.forEach((s, i) => {
  const r = eng.detect(s.text, DEFAULTS);
  const { ok, why } = s.check(r);
  const hits = r.findings.map((f) => f.matchedText + '(' + f.severity + '/' + f.matchType + ')');
  console.log((ok ? '  PASS  ' : '  FAIL  ') + '[' + i + '] ' + s.name +
    '  →  ' + r.summary.riskLevel + ' / ' + r.summary.score + ' 分 / ' +
    r.findings.length + ' 处');
  console.log('         ' + (hits.length ? hits.join(', ') : '（无命中）'));
  if (!ok) {
    console.log('         ✗ ' + why);
    fail++;
  } else {
    pass++;
  }
  console.log('');
});

console.log('示例验收结果：' + pass + ' 通过 / ' + fail + ' 失败');
process.exit(fail === 0 ? 0 : 1);
