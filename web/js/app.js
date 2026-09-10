/**
 * 合规卫士 · Web 体验页应用逻辑
 * ============================================================
 *
 * 职责边界很清楚：
 *   - engine.js 负责"怎么判"（匹配、归一化、评分）
 *   - 本文件负责"怎么显示"（渲染、交互、导出报告）
 *
 * 页面完全离线：无 fetch、无 XHR、无后端。用户粘贴的文案只存在于
 * 这个 tab 的内存里，关掉即消失——这是本工具相对 SaaS 违禁词检测的
 * 核心差异点，也是页面上那个绿色徽章要说的事。
 */
(function () {
  'use strict';

  // ============================================================ 常量

  var SEV_ORDER = ['critical', 'high', 'medium', 'low'];
  var SEV_LABEL = { critical: '高危', high: '中危', medium: '低危', low: '提示' };
  var SEV_WEIGHT = { critical: 10, high: 5, medium: 2, low: 0 };
  var SEV_VAR = {
    critical: 'var(--sev-critical)',
    high: 'var(--sev-high)',
    medium: 'var(--sev-medium)',
    low: 'var(--sev-low)',
  };

  var SOURCE_LABEL = {
    ad_law: '广告法',
    platform: '平台规则',
    blue_v: '蓝V规则',
    regex: '组合词',
    'industry:immigration': '移民红线',
    'industry:study_abroad': '留学红线',
  };

  var PLATFORM_LABEL = {
    '*': '全平台', xiaohongshu: '小红书', douyin: '抖音', weixin: '微信',
  };

  var INDUSTRY_LABEL = { immigration: '移民行业', study_abroad: '留学行业' };

  var INDUSTRY_MAP = {
    all: ['immigration', 'study_abroad'],
    immigration: ['immigration'],
    study_abroad: ['study_abroad'],
    none: [],
  };

  var RING_CIRCUMFERENCE = 263.894;   // 2 * π * r(42)，与 SVG 里的 stroke-dasharray 对应

  // ============================================================ 示例文案

  // 说明：这些不是编的"演示数据"，是照着行业里真实发布过的违规话术写的。
  // 第 4 条是反例——它必须 0 命中，否则说明词库误报了。
  var SAMPLES = [
    {
      slot: 0,
      text: [
        '澳洲雇主担保移民，官方授权渠道，包安排雇主，无需英语、无需工作经验。',
        '保签不过全额退款，成功率 100%，全网最低价，名额有限先到先得。',
      ].join('\n'),
    },
    {
      slot: 1,
      text: '全网最低價！加薇芯詳聊，保 签 包 过，不过全额退款，成功率１００％，本公司首创该模式。',
    },
    {
      slot: 2,
      text: '留学申请保录取，考不上全额退费。名师一对一，短期提分保过，内部招生名额有限。',
    },
    {
      slot: 3,
      text: [
        '澳洲雇主担保移民项目说明会将于本月举行，欢迎有兴趣的朋友了解详情。',
        '我们会结合您的学历、工作经历和语言情况，评估可行的签证路径，并提供材料准备方面的建议。',
      ].join('\n'),
    },
  ];

  // ============================================================ DOM 引用

  var $ = function (id) { return document.getElementById(id); };

  var els = {};
  function cacheEls() {
    [
      'input', 'platform', 'accountType', 'industry', 'variants', 'autoReplace',
      'counter', 'engineInfo', 'engineMeta', 'samples',
      'ringValue', 'scoreNum', 'riskBadge', 'riskSub', 'counts',
      'findings', 'preview', 'safeBox',
      'exportBtn', 'copyBtn', 'clearBtn', 'themeBtn',
      'heroRuleCount', 'fRuleCount',
    ].forEach(function (id) { els[id] = $(id); });
  }

  var engine = null;
  var lastResult = null;
  var debounceTimer = null;

  // ============================================================ 工具函数

  var ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ESC_MAP[c]; });
  }

  function scoreColor(score) {
    if (score >= 90) return 'var(--ok)';
    if (score >= 70) return SEV_VAR.medium;
    if (score >= 40) return SEV_VAR.high;
    return SEV_VAR.critical;
  }

  function stamp() {
    var d = new Date();
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '-' +
      p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds());
  }

  /** 从原文里裁一段上下文，并把命中片段用 <em> 框出来（高亮不跑偏）。 */
  function excerptHtml(chars, start, end, radius) {
    radius = radius || 12;
    var lo = Math.max(0, start - radius);
    var hi = Math.min(chars.length, end + radius);
    return (lo > 0 ? '…' : '') +
      esc(chars.slice(lo, start).join('')) +
      '<em>' + esc(chars.slice(start, end).join('')) + '</em>' +
      esc(chars.slice(end, hi).join('')) +
      (hi < chars.length ? '…' : '');
  }

  /** 全文高亮预览：命中之间互不重叠且已按 start 排序，顺序拼即可。 */
  function buildPreviewHtml(text, findings) {
    var chars = Array.from(text);
    var out = [];
    var cursor = 0;
    findings.forEach(function (f) {
      if (f.start > cursor) out.push(esc(chars.slice(cursor, f.start).join('')));
      out.push('<mark data-sev="' + esc(f.severity) + '" title="' +
        esc(f.keyword + ' · ' + SEV_LABEL[f.severity]) + '">' +
        esc(chars.slice(f.start, f.end).join('')) + '</mark>');
      cursor = f.end;
    });
    out.push(esc(chars.slice(cursor).join('')));
    return out.join('');
  }

  // ============================================================ 选项读取

  function currentOptions() {
    return {
      platform: els.platform.value,
      accountType: els.accountType.value,
      industries: INDUSTRY_MAP[els.industry.value] || [],
      useVariants: els.variants.checked,
      autoReplace: els.autoReplace.checked,
    };
  }

  // ============================================================ 检测主流程

  function runDetect() {
    if (!engine) return;

    var text = els.input.value;
    var opts = currentOptions();
    var res = engine.detect(text, opts);
    lastResult = res;

    els.counter.textContent = Array.from(text).length + ' 字';
    render(res, text, opts);
  }

  function scheduleDetect() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runDetect, 160);
  }

  // ============================================================ 渲染

  function render(res, text, opts) {
    var s = res.summary;
    var chars = Array.from(text);

    // ---- 评分环 ----
    els.ringValue.style.strokeDashoffset =
      String(RING_CIRCUMFERENCE * (1 - s.score / 100));
    els.ringValue.style.stroke = scoreColor(s.score);
    els.scoreNum.textContent = String(s.score);

    // ---- 风险等级 ----
    els.riskBadge.dataset.risk = s.riskLevel;
    els.riskBadge.textContent = s.riskLevel;

    var n = res.findings.length;
    if (!text.trim()) {
      els.riskSub.textContent = '等待输入文案';
    } else if (n === 0) {
      els.riskSub.textContent = '未发现风险词';
    } else {
      els.riskSub.textContent = '命中 ' + n + ' 处 · 扣 ' + (100 - s.score) + ' 分';
    }

    // ---- 引擎元信息 ----
    els.engineMeta.textContent = text.trim()
      ? ('扫描 ' + res.meta.ruleCount + ' 条规则 · ' + res.meta.elapsedMs + ' ms')
      : '';

    // ---- 四档计数 ----
    els.counts.innerHTML = SEV_ORDER.map(function (k) {
      var c = s.counts[k] || 0;
      return '<span class="count" data-empty="' + (c ? 0 : 1) + '">' +
        '<span class="count__dot" style="background:' + SEV_VAR[k] + '"></span>' +
        SEV_LABEL[k] + ' ' + c + '</span>';
    }).join('');

    // ---- 命中卡片（按严重度分组，高危在前）----
    if (n === 0) {
      els.findings.innerHTML = '<div class="empty"><div class="empty__big">✓</div>' +
        (text.trim() ? '未发现风险词' : '把文案粘到左边，立刻开始检测') + '</div>';
    } else {
      els.findings.innerHTML = renderGroups(res.findings, chars);
    }

    // ---- 全文高亮预览 ----
    if (n > 0) {
      els.preview.hidden = false;
      els.preview.innerHTML = buildPreviewHtml(text, res.findings);
    } else {
      els.preview.hidden = true;
      els.preview.innerHTML = '';
    }

    // ---- 自动改写结果 ----
    if (opts.autoReplace && res.safeText && res.safeText !== text) {
      els.safeBox.innerHTML = '<div class="safe"><div class="safe__head">' +
        '自动改写结果（仅改写词库给出替换词的命中，其余仍需人工判断）</div>' +
        esc(res.safeText) + '</div>';
    } else {
      els.safeBox.innerHTML = '';
    }

    els.exportBtn.disabled = !text.trim();
    els.copyBtn.disabled = !text.trim();
  }

  function renderGroups(findings, chars) {
    var bySev = {};
    SEV_ORDER.forEach(function (k) { bySev[k] = []; });
    findings.forEach(function (f) {
      (bySev[f.severity] || (bySev[f.severity] = [])).push(f);
    });

    var html = '';
    SEV_ORDER.forEach(function (k) {
      var list = bySev[k];
      if (!list || !list.length) return;
      html += '<div class="findings__group" data-sev="' + k + '">' +
        SEV_LABEL[k] + ' ' + list.length + ' 处' +
        '<span>每处扣 ' + SEV_WEIGHT[k] + ' 分</span></div>';
      list.forEach(function (f) { html += findingHtml(f, chars); });
    });
    return html;
  }

  function findingHtml(f, chars) {
    var tags = '';

    if (f.matchType === 'variant') {
      tags += '<span class="tag tag--var" title="原文写的不是关键词本身，' +
        '而是谐音 / 跳字 / 全角 / 繁体等规避写法（置信度 ' +
        Math.round(f.confidence * 100) + '%）">疑似规避写法</span>';
    } else if (f.matchType === 'regex') {
      tags += '<span class="tag tag--warn" title="由组合正则匹配到的极限词">组合词</span>';
    }

    if (f.industry) {
      tags += '<span class="tag">' +
        esc(INDUSTRY_LABEL[f.industry] || f.industry) + '</span>';
    }

    var src = SOURCE_LABEL[f.source] || f.source;
    if (src) tags += '<span class="tag tag--src">' + esc(src) + '</span>';

    if (f.platform && f.platform !== '*') {
      tags += '<span class="tag tag--src">' +
        esc(PLATFORM_LABEL[f.platform] || f.platform) + '</span>';
    }

    var body = '<div class="finding__ctx">' + excerptHtml(chars, f.start, f.end) + '</div>';

    var tips = '';
    if (f.suggestion) {
      tips += '<div class="finding__tip"><b>建议</b><span>' + esc(f.suggestion) + '</span></div>';
    }
    if (f.replacements && f.replacements.length) {
      tips += '<div class="finding__tip"><b>可改为</b><span>' +
        f.replacements.map(esc).join(' / ') + '</span></div>';
    }
    if (f.variantOf && f.variantOf !== f.matchedText) {
      tips += '<div class="finding__tip"><b>对应词条</b><span>' +
        esc(f.variantOf) + '</span></div>';
    }

    return '<div class="finding" data-sev="' + esc(f.severity) + '">' +
      '<div class="finding__top">' +
      '<span class="sev-tag" data-sev="' + esc(f.severity) + '">' +
      SEV_LABEL[f.severity] + '</span>' +
      '<span class="finding__word">' + esc(f.matchedText) + '</span>' +
      tags +
      '<span class="finding__cat">' + esc(f.category || '') + '</span>' +
      '</div>' +
      body + tips +
      '</div>';
  }

  // ============================================================ 导出报告

  function buildReportHtml(res, text, opts) {
    var s = res.summary;
    var rows = res.findings.map(function (f, i) {
      return '<tr>' +
        '<td>' + (i + 1) + '</td>' +
        '<td class="sev-' + esc(f.severity) + '">' + SEV_LABEL[f.severity] + '</td>' +
        '<td><code>' + esc(f.matchedText) + '</code></td>' +
        '<td>' + esc(f.keyword) + '</td>' +
        '<td>' + esc(f.category || '') + '</td>' +
        '<td>' + esc(SOURCE_LABEL[f.source] || f.source || '') + '</td>' +
        '<td>' + (f.matchType === 'variant' ? '疑似规避写法' :
          f.matchType === 'regex' ? '组合词' : '字面') + '</td>' +
        '<td>' + esc(f.suggestion || '') +
        (f.replacements && f.replacements.length
          ? '<br><span class="dim">建议改为：' + esc(f.replacements.join(' / ')) + '</span>' : '') +
        '</td>' +
        '</tr>';
    }).join('');

    var emptyRow = '<tr><td colspan="8" class="dim">未发现风险词。</td></tr>';

    return '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">' +
      '<title>合规检测报告 ' + stamp() + '</title><style>' +
      'body{font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;' +
      'color:#1f2328;margin:0;padding:32px;max-width:1000px;}' +
      'h1{font-size:20px;margin:0 0 4px;}h2{font-size:15px;margin:26px 0 8px;' +
      'border-bottom:1px solid #d8dee4;padding-bottom:5px;}' +
      '.dim{color:#6b7580;}.meta{color:#59636e;font-size:12.5px;}' +
      '.cards{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0;}' +
      '.card{border:1px solid #d8dee4;border-radius:8px;padding:10px 16px;min-width:96px;}' +
      '.card b{display:block;font-size:22px;line-height:1.3;}' +
      '.card span{font-size:12px;color:#59636e;}' +
      'table{border-collapse:collapse;width:100%;font-size:12.5px;}' +
      'th,td{border:1px solid #d8dee4;padding:6px 9px;text-align:left;vertical-align:top;}' +
      'th{background:#f0f3f6;font-weight:600;}' +
      'code{font-family:Consolas,monospace;background:#f0f3f6;padding:1px 5px;border-radius:3px;}' +
      '.sev-critical{color:#c0392b;font-weight:600;}.sev-high{color:#b9770e;font-weight:600;}' +
      '.sev-medium{color:#9a7d0a;}.sev-low{color:#6b7580;}' +
      'pre{background:#f6f8fa;border:1px solid #d8dee4;border-radius:8px;padding:14px;' +
      'white-space:pre-wrap;word-break:break-word;font-size:13px;}' +
      'footer{margin-top:32px;color:#818b96;font-size:12px;border-top:1px solid #d8dee4;padding-top:12px;}' +
      '</style></head><body>' +

      '<h1>合规卫士 · 检测报告</h1>' +
      '<div class="meta">生成时间 ' + new Date().toLocaleString('zh-CN') +
      ' ｜ 目标平台 ' + esc(PLATFORM_LABEL[opts.platform] || opts.platform) +
      ' ｜ 账号类型 ' + (opts.accountType === 'blue_v' ? '蓝V认证' : '普通账号') +
      ' ｜ 行业词库 ' + esc(els.industry.options[els.industry.selectedIndex].text) +
      ' ｜ 变体检测 ' + (opts.useVariants ? '开' : '关') +
      ' ｜ 规则库 ' + res.meta.ruleCount + ' / ' + res.meta.ruleTotal + ' 条</div>' +

      '<div class="cards">' +
      '<div class="card"><b>' + s.score + '</b><span>合规分（满分 100）</span></div>' +
      '<div class="card"><b class="sev-' + riskSevClass(s.riskLevel) + '">' + s.riskLevel + '</b><span>风险等级</span></div>' +
      SEV_ORDER.map(function (k) {
        return '<div class="card"><b>' + (s.counts[k] || 0) + '</b><span>' + SEV_LABEL[k] + '</span></div>';
      }).join('') +
      '</div>' +

      '<h2>命中明细</h2>' +
      '<table><thead><tr><th>#</th><th>等级</th><th>命中片段</th><th>对应词条</th>' +
      '<th>类别</th><th>来源</th><th>类型</th><th>建议</th></tr></thead><tbody>' +
      (rows || emptyRow) + '</tbody></table>' +

      '<h2>原文</h2><pre>' + esc(text) + '</pre>' +

      (opts.autoReplace && res.safeText !== text
        ? '<h2>自动改写结果</h2><pre>' + esc(res.safeText) + '</pre>' : '') +

      '<footer>本报告由「合规卫士」浏览器端引擎生成，检测全程在本机完成，' +
      '文案未上传任何服务器。报告只覆盖关键词与规则匹配，不构成法律意见；' +
      '发布前请结合平台最新规则复核。</footer>' +
      '</body></html>';
  }

  function riskSevClass(risk) {
    if (risk === '高风险') return 'critical';
    if (risk === '中风险') return 'high';
    if (risk === '低风险') return 'medium';
    return 'low';
  }

  function exportReport() {
    if (!lastResult) return;
    var html = buildReportHtml(lastResult, els.input.value, currentOptions());
    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = '合规检测报告_' + stamp() + '.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  /** 命中清单的纯文本版，方便直接粘进工单或聊天窗口。 */
  function buildPlainList() {
    if (!lastResult || !lastResult.findings.length) return '未发现风险词。';
    var lines = ['合规分 ' + lastResult.summary.score + ' ｜ 风险等级 ' +
      lastResult.summary.riskLevel + ' ｜ 命中 ' + lastResult.findings.length + ' 处', ''];
    SEV_ORDER.forEach(function (k) {
      var list = lastResult.findings.filter(function (f) { return f.severity === k; });
      if (!list.length) return;
      lines.push('【' + SEV_LABEL[k] + '】');
      list.forEach(function (f) {
        lines.push('  · ' + f.matchedText + '（对应词条：' + f.keyword + '，' +
          (f.matchType === 'variant' ? '疑似规避写法' :
            f.matchType === 'regex' ? '组合词' : '字面') + '）' +
          (f.suggestion ? ' → ' + f.suggestion : ''));
      });
      lines.push('');
    });
    return lines.join('\n');
  }

  function copyList() {
    var txt = buildPlainList();
    var done = function (ok) {
      var old = els.copyBtn.textContent;
      els.copyBtn.textContent = ok ? '已复制' : '复制失败，请手动选择';
      setTimeout(function () { els.copyBtn.textContent = old; }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(function () { done(true); },
        function () { done(false); });
    } else {
      var ta = document.createElement('textarea');
      ta.value = txt;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      done(ok);
    }
  }

  // ============================================================ 主题

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    els.themeBtn.textContent = theme === 'dark' ? '浅色' : '深色';
    try { localStorage.setItem('adcompli-theme', theme); } catch (e) { /* 无痕模式忽略 */ }
  }

  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem('adcompli-theme'); } catch (e) { /* ignore */ }
    applyTheme(saved === 'light' ? 'light' : 'dark');
  }

  // ============================================================ 事件绑定

  function bindEvents() {
    els.input.addEventListener('input', scheduleDetect);

    ['platform', 'accountType', 'industry', 'variants', 'autoReplace'].forEach(function (id) {
      els[id].addEventListener('change', runDetect);
    });

    els.samples.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('.chip') : null;
      if (!btn) return;
      var slot = Number(btn.getAttribute('data-sample'));
      var sample = SAMPLES.filter(function (s) { return s.slot === slot; })[0];
      if (!sample) return;
      els.input.value = sample.text;
      els.input.focus();
      runDetect();
    });

    els.exportBtn.addEventListener('click', exportReport);
    els.copyBtn.addEventListener('click', copyList);

    els.clearBtn.addEventListener('click', function () {
      els.input.value = '';
      els.input.focus();
      runDetect();
    });

    els.themeBtn.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      applyTheme(cur === 'dark' ? 'light' : 'dark');
    });
  }

  // ============================================================ 启动

  function fatal(msg) {
    els.engineInfo.textContent = msg;
    els.findings.innerHTML = '<div class="empty"><div class="empty__big">⚠</div>' + esc(msg) + '</div>';
  }

  function init() {
    cacheEls();
    initTheme();
    bindEvents();

    if (typeof window.GuardianEngine !== 'function') {
      fatal('引擎脚本未加载（web/js/engine.js）');
      return;
    }
    if (!window.GUARDIAN_RULES) {
      fatal('词库未加载（web/data/rules.js）。请确认 web/data/ 目录完整。');
      return;
    }

    engine = new window.GuardianEngine(window.GUARDIAN_RULES);

    var meta = window.GUARDIAN_RULES.meta || {};
    var total = meta.rule_count || window.GUARDIAN_RULES.rules.length;
    els.heroRuleCount.textContent = String(total);
    els.fRuleCount.textContent = String(total);
    els.engineInfo.textContent = '词库 ' + total + ' 条 · 引擎 ' + (meta.engine || '—');

    runDetect();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
