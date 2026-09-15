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
    custom: '我的词库',
  };

  var PLATFORM_LABEL = {
    '*': '全平台', xiaohongshu: '小红书', douyin: '抖音', weixin: '微信',
  };

  // ---- 行业包：全部来自词库产物，前端不写死任何行业 ----
  //
  // 行业包是可插拔的（`rules/industry_packs/<id>/` 两个文件即成立）。
  // 如果前端硬编码一张行业表，每加一个包就得改前端、改测试、改文档——
  // 而漂移总是发生在"忘了改"的那一处。所以元信息随产物下发，前端只渲染。
  var PACKS = ((window.GUARDIAN_RULES || {}).meta || {}).industry_packs || [];
  var INDUSTRY_LABEL = {};     // id → 短名（下拉、徽章用）
  var INDUSTRY_FULL = {};      // id → 全名（健康度表格用）
  PACKS.forEach(function (p) {
    var short = p.short || p.name || p.id;
    INDUSTRY_LABEL[p.id] = short;
    INDUSTRY_FULL[p.id] = p.name || p.id;
    SOURCE_LABEL['industry:' + p.id] = short + '红线';
  });

  /** 行业选择项（all / none / 某个包 id）→ 参与检测的行业包 id 列表。 */
  function industryIds(key) {
    var ids = PACKS.map(function (p) { return p.id; });
    if (key === 'all') return ids;
    if (key === 'none') return [];
    return ids.indexOf(key) >= 0 ? [key] : ids;
  }

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
      'singleBrief', 'settingsBox', 'settingsBrief',
      'ringValue', 'scoreNum', 'riskBadge', 'riskSub', 'counts',
      'findings', 'preview', 'safeBox', 'matrixBox', 'aiBox', 'abBox',
      'exportBtn', 'copyBtn', 'clearBtn', 'themeBtn',
      'iterBox', 'baselineBtn',
      'heroRuleCount', 'fRuleCount', 'fPacks',
      'dPlatform', 'dPlatforms', 'dPacks', 'dIndustry', 'dBlueV',
      // 标签页
      'tabbar', 'pane-single', 'pane-batch', 'pane-rules', 'pane-my',
      'tabRuleCount', 'tabMyCount',
      // 批量检测
      'bInput', 'bPlatform', 'bAccountType', 'bIndustry', 'bVariants',
      'bSampleBtn', 'bClearBtn', 'bCounter', 'bMeta', 'bStats', 'bResults',
      'bExportCsv', 'bCopyPass', 'bBrief', 'bSettingsBox', 'bSettingsBrief',
      // 词库浏览
      'rSearch', 'rSource', 'rSeverity', 'rPlatform', 'rScope', 'rStats', 'rList',
      'rPrev', 'rNext', 'rPageInfo', 'rFilters', 'rFilterN',
      // 词库健康度
      'rHealth', 'rHealthDot', 'rHealthBrief', 'rHealthBody',
      // 最近检测
      'histStoreText', 'histClear', 'histHint', 'histList',
      // 我的词库
      'mMeta', 'mForm', 'mKeyword', 'mSeverity', 'mCategory', 'mSuggestion',
      'mLaw', 'mAddBtn', 'mAddMsg', 'mBulk', 'mBulkBtn', 'mBulkMsg',
      'mStats', 'mList', 'mExportBtn', 'mImportBtn', 'mTemplateBtn',
      'mClearBtn', 'mFile', 'mBuiltin',
    ].forEach(function (id) { els[id] = $(id); });
  }

  var engine = null;
  var lastResult = null;
  var debounceTimer = null;

  /**
   * 改前基线快照。内容运营的真实节奏是"检测 → 改 → 再检测 → 再改"，
   * 所以光有一把尺子不够，还得能回答"这一轮我改干净了没、有没有改出新问题"。
   * 只存在内存里：刷新即失效，不落盘，也就不会有原文残留。
   */
  var baseline = null;

  // ============================================================ 工具函数

  var ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ESC_MAP[c]; });
  }

  /** 复制文本：优先 Clipboard API，降级 execCommand（老浏览器 / 非 HTTPS）。 */
  function copyText(txt, done) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(function () { done(true); },
        function () { done(false); });
      return;
    }
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

  function scoreColor(score) {
    if (score >= 90) return 'var(--ok)';
    if (score >= 70) return SEV_VAR.medium;
    if (score >= 40) return SEV_VAR.high;
    return SEV_VAR.critical;
  }

  /** 是否处于窄屏布局。断点与 style.css 的 @media (max-width: 720px) 一致。 */
  function isNarrow() {
    if (window.matchMedia) return window.matchMedia('(max-width: 720px)').matches;
    return window.innerWidth <= 720;
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
      industries: industryIds(els.industry.value),
      useVariants: els.variants.checked,
      autoReplace: els.autoReplace.checked,
    };
  }

  /** 把当前设置压成一句话，供窄屏折叠状态下仍能看清"现在按什么标准判"。 */
  function optionsBrief(prefix) {
    var p = els[prefix + 'Platform'] ? els[prefix + 'Platform'].value : els.platform.value;
    var a = els[prefix + 'AccountType'] ? els[prefix + 'AccountType'].value : els.accountType.value;
    var ind = els[prefix + 'Industry'] ? els[prefix + 'Industry'].value : els.industry.value;
    var parts = [
      PLATFORM_LABEL[p] || '全部平台',
      a === 'blue_v' ? '蓝 V 认证' : '普通账号',
      ind === 'all' ? (PACKS.length + ' 个行业包')
        : ind === 'none' ? '仅通用词库'
          : (INDUSTRY_LABEL[ind] || '行业包'),
    ];
    if (myActiveCount()) parts.push('我的词库 ' + myActiveCount() + ' 条');
    return parts.join(' · ');
  }

  // ============================================================ 差异演示

  // 底部「和通用工具有什么不同」四张卡片上的演示按钮，各配一段最能
  // 说明问题的文案。这些不是随机举例：
  //   platform → 同一句话在三平台命运不同（通用工具不分平台，给不出这个结论）
  //   industry → 这句在通用违禁词库里是干净的，只有移民行业包能识别
  //   variant  → 全是规避写法，人工审核最容易漏的一类
  var DEMOS = {
    platform: {
      text: '想了解澳洲雇主担保的朋友，加微信详聊，我把项目资料发你。',
      platform: 'all',
      accountType: 'non_blue_v',
      industry: 'all',
      focus: 'matrix',
    },
    industry: {
      text: '保证获批，不过全额退款，名额有限，有意向的朋友请尽快联系。',
      platform: 'all',
      accountType: 'non_blue_v',
      industry: 'all',
      // 这段文案在通用词库里是干净的，对照实验最能说明问题，所以滚到那里
      focus: 'ab',
    },
    variant: {
      text: '全网最低價！加薇芯詳聊，保 签 包 过，成功率１００％，本公司首创该模式。',
      platform: 'all',
      accountType: 'non_blue_v',
      industry: 'all',
      focus: 'variant',
    },
    // 第 ④ 张卡不讲文案，讲"规则本身可查证"，所以直接切到词库页
    rules: { tab: 'rules' },
  };

  /** 把底部的统计数字换成真实词库数据 —— 作品自证不能靠写死的形容词。 */
  function fillDiffStats() {
    var rules = (window.GUARDIAN_RULES && window.GUARDIAN_RULES.rules) || [];
    if (!rules.length) return;

    var platRules = 0;
    var plats = {};
    var industry = 0;
    var blueV = 0;
    rules.forEach(function (r) {
      var p = r.p || ['*'];
      if (p.indexOf('*') === -1) {
        platRules++;
        p.forEach(function (k) { plats[k] = 1; });
      }
      if (r.i) industry++;
      // sa = severity by account type：同一词在蓝 V / 普通账号下定级不同
      if (r.sa) blueV++;
    });

    if (els.dPlatform) els.dPlatform.textContent = String(platRules);
    if (els.dPlatforms) els.dPlatforms.textContent = String(Object.keys(plats).length);
    if (els.dPacks) els.dPacks.textContent = String(PACKS.length);
    if (els.dIndustry) els.dIndustry.textContent = String(industry);
    if (els.dBlueV) els.dBlueV.textContent = String(blueV);
    if (els.fPacks) {
      els.fPacks.textContent = '行业包：' +
        PACKS.map(function (p) { return p.short || p.id; }).join(' / ');
    }
  }

  // ============================================================ 差异演示

  function bindDemoButtons() {
    var box = document.querySelector('.diff');
    if (!box) return;
    box.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('.dcard__demo') : null;
      if (!btn) return;
      var demo = DEMOS[btn.getAttribute('data-demo')];
      if (!demo) return;

      // 有的演示不讲文案（如"规则可查证"），只负责切换标签页
      if (demo.tab) {
        switchTab(demo.tab);
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }

      switchTab('single');

      els.input.value = demo.text;
      els.platform.value = demo.platform;
      els.accountType.value = demo.accountType;
      els.industry.value = demo.industry;
      els.variants.checked = true;
      runDetect();

      // 滚到能看见结论的位置：三种演示各有各的"证据在哪里"
      //   matrix → 三平台对比表
      //   ab     → 对照实验（关掉行业词库就抓不到，这是最有力的证据）
      //   其余   → 命中明细
      var target = demo.focus === 'matrix' ? els.matrixBox
        : demo.focus === 'ab' ? els.abBox
          : els.findings;
      if (target && target.scrollIntoView) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }

  // ============================================================ 检测主流程

  function runDetect() {
    if (!engine) return;

    var text = els.input.value;
    var opts = currentOptions();
    var res = engine.detect(text, opts);
    lastResult = res;

    els.counter.textContent = Array.from(text).length + ' 字';
    if (els.singleBrief) els.singleBrief.textContent = optionsBrief('');
    if (els.settingsBrief) els.settingsBrief.textContent = optionsBrief('');
    render(res, text, opts);
    scheduleHistory(text, res);
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

    // ---- 对照实验（关掉行业词库，看这段文案还剩几处风险）----
    renderAB(text, opts, res);

    // ---- 改前/改后迭代对比 ----
    renderIter(text, res);

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

    // ---- 跨平台对比矩阵 ----
    renderMatrix(text, opts, res);

    // ---- AI 改写入口（判定已完成，AI 只负责把话说圆）----
    renderAi(text, opts, res);

    els.exportBtn.disabled = !text.trim();
    els.copyBtn.disabled = !text.trim();
    updateBaselineBtn(text);
  }

  // ============================================================ 改前/改后迭代

  /**
   * 命中的身份标识。
   *
   * 用「词面 + 类别」而不是位置下标来配对——因为改文案会整体挪动字符位置，
   * 用下标比对会把"同一处被改掉了"误判成"消失一处、新增一处"。
   * 代价是同一段里重复出现的同一违规词只能算一处，对"有没有改干净"这个
   * 问题来说，这个粒度恰好够用。
   */
  function iterKey(f) {
    return (f.matchedText || '') + '|' + (f.category || '');
  }

  function scorePill(score) {
    return '<span class="iter__score" style="color:' + scoreColor(score) + '">' +
      score + '</span>';
  }

  function wordChips(list, limit, cls) {
    if (!list.length) return '<span class="iter__none">无</span>';
    var shown = list.slice(0, limit).map(function (f) {
      return '<span class="iter__chip' + (cls ? ' ' + cls : '') + '">' +
        esc(f.matchedText) + '</span>';
    }).join('');
    var more = list.length > limit
      ? '<span class="iter__more">+另有 ' + (list.length - limit) + ' 处</span>' : '';
    return shown + more;
  }

  function renderIter(text, res) {
    var box = els.iterBox;
    if (!box) return;

    // 没存过基线、文案还没动过、或者已清空 —— 都不该出现这块
    if (!baseline || !text.trim() || text === baseline.text) {
      box.hidden = true;
      box.innerHTML = '';
      return;
    }

    var nowKeys = {};
    res.findings.forEach(function (f) { nowKeys[iterKey(f)] = true; });
    var beforeKeys = {};
    baseline.findings.forEach(function (f) { beforeKeys[iterKey(f)] = true; });

    var fixed = baseline.findings.filter(function (f) { return !nowKeys[iterKey(f)]; });
    var left = res.findings.filter(function (f) { return beforeKeys[iterKey(f)]; });
    // 「新引入」是这块最该被看见的东西：很多工具只告诉你"还剩几处"，
    // 不告诉你"你刚才那一刀又砍出个新问题"。
    var added = res.findings.filter(function (f) { return !beforeKeys[iterKey(f)]; });

    var delta = res.summary.score - baseline.score;
    var arrow, deltaColor;
    if (delta > 0) { arrow = '↑ +' + delta; deltaColor = 'var(--ok)'; }
    else if (delta < 0) { arrow = '↓ ' + delta; deltaColor = 'var(--sev-critical)'; }
    else { arrow = '持平'; deltaColor = 'var(--text-3)'; }

    var clean = res.findings.length === 0;

    box.hidden = false;
    box.innerHTML =
      '<div class="iter__head">这一轮改动' +
      '<span class="iter__tag">基线只存在内存里 · 刷新即失效</span></div>' +

      '<div class="iter__scores">' +
      '<div class="iter__side"><span class="iter__lb">改前</span>' +
      scorePill(baseline.score) +
      '<span class="iter__cnt">' + baseline.findings.length + ' 处</span></div>' +
      '<div class="iter__arrow" style="color:' + deltaColor + '">→<b>' + arrow + '</b></div>' +
      '<div class="iter__side"><span class="iter__lb">改后</span>' +
      scorePill(res.summary.score) +
      '<span class="iter__cnt">' + res.findings.length + ' 处</span></div>' +
      '</div>' +

      '<div class="iter__rows">' +
      '<div class="iter__row" data-k="fixed"><span class="iter__k">已消除 ' +
      fixed.length + ' 处</span><div class="iter__v">' +
      wordChips(fixed, 6, 'is-ok') + '</div></div>' +

      '<div class="iter__row" data-k="left"><span class="iter__k">仍未处理 ' +
      left.length + ' 处</span><div class="iter__v">' +
      wordChips(left, 6) + '</div></div>' +

      '<div class="iter__row" data-k="added"><span class="iter__k">新引入 ' +
      added.length + ' 处</span><div class="iter__v">' +
      wordChips(added, 6, 'is-bad') + '</div></div>' +
      '</div>' +

      (clean
        ? '<div class="iter__done">这一版已经清零，可以发了。如果要继续改，记得重新存一次基线。</div>'
        : (added.length
          ? '<div class="iter__warn">注意：改动带出了 ' + added.length +
            ' 处新命中，别只看总分涨了就放过它们。</div>'
          : ''));
  }

  /** 基线按钮的文案随状态变，用户一眼能看出"现在有没有基线"。 */
  function updateBaselineBtn(text) {
    var b = els.baselineBtn;
    if (!b) return;
    var hasText = !!(text && text.trim());
    if (baseline) {
      b.textContent = '改前 ' + baseline.score + ' 分 · 重新存';
      b.title = '当前基线：' + baseline.score + ' 分 / ' + baseline.findings.length +
        ' 处命中。点一下用现在的文案覆盖它；文案没动过时点一下则取消基线。';
    } else {
      b.textContent = '存为改前';
      b.title = '先存下这一版作为基线，改完再来对比"改干净了没、有没有改出新问题"。';
    }
    b.disabled = !hasText;
  }

  // ============================================================ 跨平台对比

  //: 对比用的三个平台。不包含"全部平台"——那是并集，拿来做对比没有意义。
  var MATRIX_PLATFORMS = [
    { key: 'xiaohongshu', label: '小红书' },
    { key: 'douyin', label: '抖音' },
    { key: 'weixin', label: '微信' },
  ];

  /** 同一段文案分别按三个平台跑一遍，返回每平台的独立结果。 */
  function runMatrix(text, opts) {
    return MATRIX_PLATFORMS.map(function (p) {
      var o = {};
      Object.keys(opts).forEach(function (k) { o[k] = opts[k]; });
      o.platform = p.key;
      return { key: p.key, label: p.label, res: engine.detect(text, o) };
    });
  }

  // ============================================================ AI 改写

  /**
   * AI 改写区的渲染。
   *
   * 这里体现了本项目对 AI 的定位：**判定归规则引擎，改写才交给模型**。
   * 页面因此不需要把文案发给任何服务器，也就不需要 API Key、不需要后端——
   * 它把"规则引擎的精确命中 + 改写约束"打包成一段指令，用户复制走即可，
   * 用什么 AI 由用户自己决定（BYO-AI）。这比"内置一个模型"更轻、更私密，
   * 也让这个页面可以纯静态部署。
   */
  function renderAi(text, opts, res) {
    if (!text.trim() || !res.findings.length) {
      els.aiBox.hidden = true;
      els.aiBox.innerHTML = '';
      return;
    }

    els.aiBox.hidden = false;
    els.aiBox.innerHTML =
      '<div class="ai__head">' +
      '<span class="ai__title">AI 改写这一版</span>' +
      '<span class="ai__hint">判定已完成 · 这里只负责改写</span>' +
      '</div>' +
      '<div class="ai__note">' +
      '违规点已由规则引擎定位（' + res.findings.length + ' 处，带法条来源与可用替换词）。' +
      '改写是语言活儿，交给 AI 更快——但<b>判定不能交给它</b>：模型会漏检、会编造、' +
      '同一句话问两次给两个结论。所以这里只把「精确命中清单 + 改写约束」交给 AI，' +
      '结论仍以规则引擎为准。' +
      '</div>' +
      '<div class="ai__actions">' +
      '<button class="btn" id="aiCopyBtn" type="button">复制 AI 改写指令</button>' +
      '<button class="btn btn--ghost" id="aiPeekBtn" type="button">预览指令</button>' +
      '</div>' +
      '<div class="ai__result" id="aiResult"></div>' +
      '<div class="ai__note">' +
      '本页不上传文案，所以不内置模型：复制后粘到任意 AI（豆包 / DeepSeek / ChatGPT）即可得到改写。' +
      '桌面版可直连本地 Ollama 或云端 API，检测完一键出结果。' +
      '</div>';

    var copyBtn = $('aiCopyBtn');
    var peekBtn = $('aiPeekBtn');
    var result = $('aiResult');

    function promptText() {
      return window.GuardianEngine.buildRewritePrompt(
        els.input.value, lastResult.findings, {
          platform: opts.platform,
          accountType: opts.accountType,
          industryLabel: els.industry.options[els.industry.selectedIndex].text,
        });
    }

    copyBtn.addEventListener('click', function () {
      copyText(promptText(), function (ok) {
        var old = copyBtn.textContent;
        copyBtn.textContent = ok ? '已复制，去粘给 AI 吧' : '复制失败，请用「预览指令」手动复制';
        setTimeout(function () { copyBtn.textContent = old; }, 2000);
      });
    });

    peekBtn.addEventListener('click', function () {
      if (result.getAttribute('data-open') === '1') {
        result.innerHTML = '';
        result.removeAttribute('data-open');
        peekBtn.textContent = '预览指令';
        return;
      }
      result.innerHTML = '<pre id="aiPromptPre">' + esc(promptText()) + '</pre>';
      result.setAttribute('data-open', '1');
      peekBtn.textContent = '收起指令';
    });
  }

  /**
   * 渲染跨平台对比表。
   *
   * 这里有一条**必须守住的产品底线**：三平台同分时，绝不能挑一个平台说
   * "它最严"。同分恰恰说明命中的是跨平台通用规则（广告法红线），平台之间
   * 没有差异——把这种情况说成"某平台最严"是在编结论，用户会据此做出错误
   * 的投放决策。所以并列时必须明说"无平台差异"。
   */
  function renderMatrix(text, opts, res) {
    if (!text.trim() || !res.findings.length) {
      els.matrixBox.hidden = true;
      els.matrixBox.innerHTML = '';
      return;
    }

    var rows = runMatrix(text, opts);
    var scores = rows.map(function (r) { return r.res.summary.score; });
    var uniq = [];
    scores.forEach(function (v) { if (uniq.indexOf(v) === -1) uniq.push(v); });

    var verdict;
    if (uniq.length === 1) {
      verdict = '三平台判定一致（均 <b>' + uniq[0] + '</b> 分）——说明命中的是' +
        '<b>跨平台通用规则</b>（《广告法》红线一类），平台之间没有额外差异。';
    } else {
      var min = Math.min.apply(null, scores);
      var strictest = rows.filter(function (r) { return r.res.summary.score === min; })
        .map(function (r) { return r.label; }).join('、');
      verdict = '存在平台差异：<b>' + strictest + '</b> 判定最严（' + min +
        ' 分）。差异可能来自平台专属规则，也可能是同一个词在不同平台的定级不同——见右侧「平台差异」列。';
    }

    var head = '<div class="matrix__head">' +
      '跨平台对比<span class="matrix__verdict">' + verdict + '</span></div>';

    var body = rows.map(function (r) {
      // 建"每平台的 命中词 → 严重度"映射。
      //
      // 平台差异有两种，缺一不可：
      //   ① 命中项差异：这个词只有本平台管（如「加微信」只在小红书是导流违规）
      //   ② 严重度差异：三个平台都管这个词，但判得轻重不同
      //      （真实数据里「加微信」在小红书/抖音是高危、在微信只是中危）
      // 只比①会漏掉大量真实差异——同一句话在不同平台的危险程度不同，
      // 恰恰是用户最需要知道的事。
      var sevAt = {};
      rows.forEach(function (o) {
        var m = {};
        o.res.findings.forEach(function (f) { m[f.matchedText] = f.severity; });
        sevAt[o.key] = m;
      });

      var only = [];     // 其他平台完全没有的命中
      var harder = [];   // 其他平台也有，但本平台判得更重
      r.res.findings.forEach(function (f) {
        var others = [];
        rows.forEach(function (o) {
          if (o.key === r.key) return;
          var s = sevAt[o.key][f.matchedText];
          if (s !== undefined) others.push({ label: o.label, sev: s });
        });
        if (!others.length) {
          only.push(f.matchedText);
          return;
        }
        var lighter = others.filter(function (x) {
          return SEV_ORDER.indexOf(f.severity) < SEV_ORDER.indexOf(x.sev);
        });
        if (lighter.length) {
          harder.push(f.matchedText + '（本平台' + SEV_LABEL[f.severity] + '，' +
            lighter.map(function (x) { return x.label + SEV_LABEL[x.sev]; }).join('、') +
            '）');
        }
      });

      var isCurrent = (opts.platform === r.key);
      var sc = r.res.summary;
      var color = scoreColor(sc.score);

      var diffs = '';
      if (only.length) {
        diffs += '<span class="only">仅此平台：' +
          only.slice(0, 4).map(esc).join('、') +
          (only.length > 4 ? ' 等 ' + only.length + ' 处' : '') + '</span>';
      }
      if (harder.length) {
        if (diffs) diffs += '<br>';
        diffs += '<span class="only">' +
          harder.slice(0, 3).map(esc).join('；') +
          (harder.length > 3 ? ' 等 ' + harder.length + ' 处' : '') + '</span>';
      }
      if (!diffs) diffs = '<span class="none">与其他平台一致</span>';

      return '<tr data-current="' + (isCurrent ? 1 : 0) + '">' +
        '<td><span class="plat"><span class="dot" style="background:' + color +
        '"></span>' + esc(r.label) + '</span></td>' +
        '<td class="num" style="color:' + color + '">' + sc.score + '</td>' +
        '<td>' + esc(sc.riskLevel) + '</td>' +
        '<td>' + r.res.findings.length + '</td>' +
        '<td>' + diffs + '</td></tr>';
    }).join('');

    els.matrixBox.hidden = false;
    els.matrixBox.innerHTML = head +
      '<table><thead><tr><th>平台</th><th>合规分</th><th>风险等级</th>' +
      '<th>命中</th><th>平台差异</th></tr></thead><tbody>' + body +
      '</tbody></table>';
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
    // 依据：条款号 + 规则说明。合规工具说"违规"还不够，得说清"违反哪一条"，
    // 否则用户没法复核、也没法拿去跟平台/法务对话。
    if (f.lawRef || f.note) {
      tips += '<div class="finding__tip finding__tip--law"><b>依据</b><span>' +
        (f.lawRef ? '<code>' + esc(f.lawRef) + '</code>' : '') +
        (f.lawRef && f.note ? ' · ' : '') +
        (f.note ? esc(f.note) : '') +
        '</span></div>';
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
        '<td>' + (f.lawRef ? esc(f.lawRef) : '<span class="dim">—</span>') + '</td>' +
        '<td>' + (f.matchType === 'variant' ? '疑似规避写法' :
          f.matchType === 'regex' ? '组合词' : '字面') + '</td>' +
        '<td>' + esc(f.suggestion || '') +
        (f.replacements && f.replacements.length
          ? '<br><span class="dim">建议改为：' + esc(f.replacements.join(' / ')) + '</span>' : '') +
        '</td>' +
        '</tr>';
    }).join('');

    var emptyRow = '<tr><td colspan="9" class="dim">未发现风险词。</td></tr>';

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
      '<th>类别</th><th>来源</th><th>法规依据</th><th>类型</th><th>建议</th></tr></thead><tbody>' +
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
    copyText(buildPlainList(), function (ok) {
      var old = els.copyBtn.textContent;
      els.copyBtn.textContent = ok ? '已复制' : '复制失败，请手动选择';
      setTimeout(function () { els.copyBtn.textContent = old; }, 1600);
    });
  }

  // ============================================================ 标签页

  var currentTab = 'single';

  function switchTab(name) {
    if (name === currentTab && $('pane-' + name) && !$('pane-' + name).hidden) return;

    ['single', 'batch', 'rules', 'my'].forEach(function (t) {
      var pane = els['pane-' + t];
      if (pane) pane.hidden = (t !== name);
    });

    if (els.tabbar) {
      Array.prototype.forEach.call(els.tabbar.querySelectorAll('.tabs__btn'), function (b) {
        var on = b.getAttribute('data-tab') === name;
        if (on) b.classList.add('is-on'); else b.classList.remove('is-on');
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    }

    currentTab = name;

    // 懒渲染：切过去才算，避免首屏白干四份工
    if (name === 'rules') renderRules();
    if (name === 'batch') runBatch();
    if (name === 'my') renderMyLib();

    // 窄屏在底部 tab bar 上切换时，页面若不回到顶部，会停在上一页的滚动位置，
    // 看到的是一屏空白——"点了没反应"的另一种形态。
    if (isNarrow()) window.scrollTo(0, 0);
  }

  // ============================================================ 对照实验

  /**
   * 「关掉行业词库 vs 打开行业词库」的对照。
   *
   * 这是整个页面最重要的一块，因为它把"我们和通用违禁词工具不一样"这句
   * 自夸，变成了**一个访客可以自己复现的实验**：同一个引擎、同一段文案，
   * 唯一变量是行业词库开关。
   *
   * 措辞上刻意克制：不说"通用工具等于关掉词库的我们"（那是过度宣称，
   * 人家的词表和我们并不相同），只说"关掉后剩下的这部分，是通用工具
   * 结构上覆盖不到的地方"。
   */
  function renderAB(text, opts, res) {
    var box = els.abBox;
    if (!box) return;

    var enabled = !!(opts.industries && opts.industries.length);
    var industryHits = res.findings.filter(function (f) { return !!f.industry; });

    // 只在"确实抓到了行业红线"时才展示。否则这块会显得像在凑数。
    if (!text.trim() || !enabled || !industryHits.length) {
      box.hidden = true;
      box.innerHTML = '';
      return;
    }

    var offOpts = {};
    Object.keys(opts).forEach(function (k) { offOpts[k] = opts[k]; });
    offOpts.industries = [];
    var off = engine.detect(text, offOpts);

    function verdictOf(r) {
      if (!r.findings.length) return '未发现风险词';
      return '抓到 ' + r.findings.length + ' 处';
    }

    function wordList(list, limit) {
      if (!list.length) return '';
      var items = list.slice(0, limit).map(function (f) {
        return '<li>' + esc(f.matchedText) +
          ' <span style="color:' + SEV_VAR[f.severity] + '">' +
          SEV_LABEL[f.severity] + '</span></li>';
      }).join('');
      var more = list.length > limit
        ? '<li>…另有 ' + (list.length - limit) + ' 处</li>' : '';
      return '<ul class="ab__list">' + items + more + '</ul>';
    }

    var offColor = scoreColor(off.summary.score);
    var onColor = scoreColor(res.summary.score);

    // 行业包名字，用于说明"多出来的这些是谁抓的"
    var packNames = [];
    industryHits.forEach(function (f) {
      var n = INDUSTRY_LABEL[f.industry] || f.industry;
      if (packNames.indexOf(n) === -1) packNames.push(n);
    });

    box.hidden = false;
    box.innerHTML =
      '<div class="ab__head">对照实验' +
      '<span class="ab__tag">同一引擎 · 同一文案 · 唯一变量是行业词库</span></div>' +

      '<div class="ab__grid">' +
      '<div class="ab__col">' +
      '<div class="ab__label">关闭行业词库 —— 约等于通用违禁词工具能覆盖到的范围</div>' +
      '<div class="ab__score" style="color:' + offColor + '">' + off.summary.score +
      '<span class="ab__unit">合规分</span></div>' +
      '<div class="ab__verdict">' + esc(verdictOf(off)) +
      (off.findings.length ? '：' + off.findings.slice(0, 3)
        .map(function (f) { return esc(f.matchedText); }).join('、') : '') + '</div>' +
      wordList(off.findings, 3) +
      '</div>' +

      '<div class="ab__col">' +
      '<div class="ab__label">打开行业词库 —— 本页默认（' +
      esc(packNames.join(' + ')) + '）</div>' +
      '<div class="ab__score" style="color:' + onColor + '">' + res.summary.score +
      '<span class="ab__unit">合规分</span></div>' +
      '<div class="ab__verdict">' + esc(verdictOf(res)) + '</div>' +
      wordList(industryHits, 4) +
      '</div>' +
      '</div>' +

      '<div class="ab__note">' +
      '左边这组就是「只查广告法极限词」能看到的东西；多出来的 <b>' +
      industryHits.length + ' 处</b>全部来自行业专属规则（' +
      esc(packNames.join('、')) + '）——' +
      '这类词不违法，但会直接触发平台限流或封号，而且通用工具的词表里根本没有它们。' +
      '</div>';
  }

  // ============================================================ 批量检测

  //: 批量示例：4 条违规 + 1 条合规。最后那条是反例——如果它也被判违规，
  //: 说明词库误报了，用户会因此不信整批结果。
  var BATCH_SAMPLE = [
    '澳洲雇主担保移民，官方授权渠道，包安排雇主，无需英语、无需工作经验。',
    '保签不过全额退款，成功率 100%，全网最低价，名额有限先到先得。',
    '留学申请保录取，考不上全额退费，名师一对一短期提分保过。',
    '现成雇主资源，挂靠即可递交，内部名额还剩几个，抓紧私信。',
    '本月项目说明会欢迎有兴趣的朋友了解详情，我们会结合您的学历与工作经历评估可行路径。',
  ].join('\n\n');

  var lastBatch = null;

  /** 切分批量条目：空行分隔，纯分隔线忽略。 */
  function parseBatch(text) {
    return String(text || '')
      .split(/\n[ \t]*\n+/)
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s && !/^[-—–=]{3,}$/.test(s); });
  }

  function batchOptions() {
    return {
      platform: els.bPlatform.value,
      accountType: els.bAccountType.value,
      industries: industryIds(els.bIndustry.value),
      useVariants: els.bVariants.checked,
      autoReplace: false,
    };
  }

  var BATCH_OK_SCORE = 90;   // 「可放心发」的门槛，与引擎的"基本合规"口径一致

  function runBatch() {
    if (!engine) return;

    var items = parseBatch(els.bInput.value);
    els.bCounter.textContent = items.length + ' 条';
    if (els.bBrief) els.bBrief.textContent = optionsBrief('b');
    if (els.bSettingsBrief) els.bSettingsBrief.textContent = optionsBrief('b');

    if (!items.length) {
      lastBatch = null;
      els.bStats.innerHTML = '';
      els.bMeta.textContent = '';
      els.bResults.innerHTML = '<div class="empty"><div class="empty__big">▤</div>' +
        '粘贴多条文案后，这里给出每条的分数与主要风险</div>';
      els.bExportCsv.disabled = true;
      els.bCopyPass.disabled = true;
      return;
    }

    var opts = batchOptions();
    var rows = items.map(function (t, i) {
      return { idx: i + 1, text: t, res: engine.detect(t, opts) };
    });
    lastBatch = { rows: rows, opts: opts };
    renderBatch(rows);
  }

  function renderBatch(rows) {
    var pass = rows.filter(function (r) { return r.res.summary.score >= BATCH_OK_SCORE; });
    var fail = rows.length - pass.length;
    var worst = rows.reduce(function (a, b) {
      return b.res.summary.score < a.res.summary.score ? b : a;
    }, rows[0]);
    var total = rows.reduce(function (s, r) { return s + r.res.summary.score; }, 0);

    els.bStats.innerHTML =
      '<div class="bcard"><b>' + rows.length + '</b><span>条文案</span></div>' +
      '<div class="bcard"><b style="color:var(--ok)">' + pass.length +
      '</b><span>可放心发（≥' + BATCH_OK_SCORE + ' 分）</span></div>' +
      '<div class="bcard"><b style="color:var(--sev-critical)">' + fail +
      '</b><span>需要改</span></div>' +
      '<div class="bcard"><b>' + Math.round(total / rows.length) +
      '</b><span>平均分</span></div>';

    els.bMeta.textContent = '最需要改的是第 ' + worst.idx + ' 条（' +
      worst.res.summary.score + ' 分 · ' + worst.res.summary.riskLevel + '）';

    var body = rows.map(function (r) {
      var s = r.res.summary;
      var color = scoreColor(s.score);
      // 主要风险词：按严重度取前 3 个
      var picks = SEV_ORDER.reduce(function (acc, k) {
        return acc.concat(r.res.findings.filter(function (f) { return f.severity === k; }));
      }, []).slice(0, 3);
      var words = picks.length
        ? picks.map(function (f) {
          // 悬停给出条款号——批量表列宽有限，依据放进 tooltip
          // 比再塞一列更实际，需要完整依据可导出报告或 CSV。
          var tip = f.lawRef ? ' title="依据' + esc(f.lawRef) + '"' : '';
          return '<em' + tip + ' style="color:' + SEV_VAR[f.severity] + '">' +
            esc(f.matchedText) + '</em>';
        }).join('、')
        : '<span style="color:var(--ok)">未发现风险词</span>';

      return '<tr>' +
        '<td class="idx">' + r.idx + '</td>' +
        '<td><div class="btext">' + esc(r.text) + '</div></td>' +
        '<td class="num" style="color:' + color + '">' + s.score + '</td>' +
        '<td>' + esc(s.riskLevel) + '</td>' +
        '<td class="num">' + r.res.findings.length + '</td>' +
        '<td class="bwords">' + words + '</td>' +
        '</tr>';
    }).join('');

    els.bResults.innerHTML = '<table><thead><tr>' +
      '<th>#</th><th>文案</th><th>合规分</th><th>风险等级</th><th>命中</th><th>主要风险</th>' +
      '</tr></thead><tbody>' + body + '</tbody></table>';

    els.bExportCsv.disabled = false;
    els.bCopyPass.disabled = !pass.length;
  }

  /** 导出 CSV。加 BOM，否则 Excel 打开中文是乱码（Windows 上必踩）。 */
  function exportBatchCsv() {
    if (!lastBatch) return;
    var head = ['序号', '合规分', '风险等级', '高危', '中危', '低危', '命中数',
                '主要风险词', '法规依据', '原文'];
    var q = function (v) { return '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"'; };

    var lines = [head.map(q).join(',')];
    lastBatch.rows.forEach(function (r) {
      var s = r.res.summary;
      var words = r.res.findings.slice(0, 5)
        .map(function (f) { return f.matchedText; }).join('、');
      // 同一段文案常命中同一法条多次，去重后按首次出现顺序排列
      var laws = [];
      r.res.findings.forEach(function (f) {
        if (f.lawRef && laws.indexOf(f.lawRef) === -1) laws.push(f.lawRef);
      });
      lines.push([
        r.idx, s.score, s.riskLevel,
        s.counts.critical || 0, s.counts.high || 0, s.counts.medium || 0,
        r.res.findings.length, words, laws.join('；'), r.text,
      ].map(q).join(','));
    });

    var blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = '合规批量检测_' + stamp() + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function copyPassList() {
    if (!lastBatch) return;
    var pass = lastBatch.rows.filter(function (r) {
      return r.res.summary.score >= BATCH_OK_SCORE;
    });
    if (!pass.length) return;
    copyText(pass.map(function (r) { return r.text; }).join('\n\n'), function (ok) {
      var old = els.bCopyPass.textContent;
      els.bCopyPass.textContent = ok
        ? '已复制 ' + pass.length + ' 条'
        : '复制失败，请用导出 CSV';
      setTimeout(function () { els.bCopyPass.textContent = old; }, 1800);
    });
  }

  // ============================================================ 我的词库
  //
  // 内置词库解决的是"通用红线"，但每家公司还有自己的内部禁用名单：某个项目名
  // 被明令不许再提、某个竞品词要回避、某个渠道名不能再出现。这类词没有法规依据，
  // 也永远不该进公共词库——公共词库一旦为某一家公司定制，对其它用户就是噪音。
  //
  // 所以把它做成用户自己的资产：存 localStorage、立刻参与检测、可导出 JSON 搬到
  // 别的设备或桌面端（桌面端 `rules/user_custom.json` 用的是同一套字段名）。
  //
  // 隐私上与"最近检测"同一原则：这些词是用户的商业信息，只留在本机、不上传。
  // 导出走的是 Blob + a[download]，全程不经过任何服务器。

  var MY_KEY = 'adcompli-my-rules';
  var MY_MAX = 500;
  var MY_SEV = { critical: '高危', high: '中危', medium: '低危', low: '提示' };

  //: 内存中的唯一副本，写回时整体覆盖 localStorage。
  //: 不做局部写，是因为"界面有、存储没有"这种分叉最难查，而代价只有几十 KB。
  var myRules = [];

  //: 内置关键词索引（判重用），首次用到时构建。
  var builtinKw = null;

  function loadMyRules() {
    try {
      var raw = JSON.parse(localStorage.getItem(MY_KEY) || '[]');
      if (Object.prototype.toString.call(raw) !== '[object Array]') return [];
      return raw.filter(function (r) {
        return r && typeof r.keyword === 'string' && r.keyword.trim();
      });
    } catch (e) { return []; }
  }

  function saveMyRules() {
    try { localStorage.setItem(MY_KEY, JSON.stringify(myRules)); }
    catch (e) { /* 无痕模式 / 配额满：不阻断检测，用户仍可导出带走 */ }
  }

  function myActiveCount() {
    var n = 0;
    for (var i = 0; i < myRules.length; i++) if (myRules[i].enabled !== false) n++;
    return n;
  }

  /** 稳定短哈希：同一关键词重复添加时用来判重（无需依赖 crypto）。 */
  function hashStr(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    return h;
  }

  function myRuleId(kw) {
    return 'u_' + Date.now().toString(36) + '_' +
      Math.abs(hashStr(kw)).toString(36).slice(0, 4);
  }

  /** 内置词库里是否已有这个词（避免用户做重复劳动）。 */
  function isBuiltinKw(kw) {
    if (!builtinKw) {
      builtinKw = {};
      ((window.GUARDIAN_RULES || {}).rules || []).forEach(function (r) {
        builtinKw[r.k] = true;
      });
    }
    return !!builtinKw[kw];
  }

  /**
   * 添加一条词。
   *
   * 返回值带 `dup` 区分"重复"与"无效"：批量导入时这两类要分别计数，
   * 否则用户看到"跳过 8 条"却不知道是格式错还是已经存在。
   */
  function addMyRule(entry) {
    var kw = String((entry && entry.keyword) || '').trim();
    if (!kw) return { ok: false, dup: false, msg: '关键词不能为空' };
    if (Array.from(kw).length > 40) {
      return { ok: false, dup: false, msg: '关键词太长（最多 40 字）' };
    }
    var exist = null;
    for (var i = 0; i < myRules.length; i++) {
      if (myRules[i].keyword === kw) { exist = myRules[i]; break; }
    }
    if (exist) return { ok: false, dup: true, msg: '「' + kw + '」已经在你的词库里' };

    // 内置已收录的词直接挡下，而不是"加进来再提醒一句"。
    //
    // 放进来看着更宽容，代价是**同一处命中会同时挂"内置"和"我的词库"两个来源**：
    // 用户看到同一个词被判了两遍，只会以为是 bug，还说不清到底按哪条算分。
    // 真实需求里确实有人想动内置词（比如觉得该定成高危）—— 但那属于
    // "覆盖内置定级"，和"补一条工具没收录的词"是两件事，不该共用这个入口。
    if (isBuiltinKw(kw)) {
      return { ok: false, dup: true, msg: '「' + kw + '」内置词库已收录，无需重复添加' };
    }
    if (myRules.length >= MY_MAX) {
      return { ok: false, dup: false, msg: '最多存 ' + MY_MAX + ' 条，请先清理' };
    }

    var sev = MY_SEV[entry.severity] ? entry.severity : 'high';
    myRules.unshift({
      id: myRuleId(kw),
      keyword: kw,
      category: String(entry.category || '').trim() || '内部禁用',
      severity: sev,
      suggestion: String(entry.suggestion || '').trim(),
      law_ref: String(entry.law_ref || '').trim(),
      note: '',
      enabled: true,
      created: Date.now(),
    });
    return { ok: true, dup: false, msg: '' };
  }

  /** 把内存词条装进引擎，并刷新界面上所有与"我的词库"有关的数字。 */
  function applyMyRules() {
    if (engine && engine.setUserRules) {
      engine.setUserRules(myRules.filter(function (r) { return r.enabled !== false; }));
    }
    updateMyBadge();
  }

  function updateMyBadge() {
    if (!els.tabMyCount) return;
    var n = myActiveCount();
    els.tabMyCount.textContent = n ? String(n) : '';
    els.tabMyCount.hidden = !n;
  }

  var msgTimers = [];
  function setMsg(el, text, isBad) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'myform__msg' + (isBad ? ' is-bad' : ' is-ok');
    if (el._t) clearTimeout(el._t);
    if (text) el._t = setTimeout(function () { el.textContent = ''; }, 6000);
    msgTimers.push(el);
  }

  function renderMyLib() {
    if (!els.mList) return;

    var q = (els.mSearch && els.mSearch.value || '').trim().toLowerCase();
    var rows = myRules.filter(function (r) {
      if (!q) return true;
      return (r.keyword + ' ' + r.category + ' ' + (r.suggestion || '') + ' ' +
        (r.law_ref || '')).toLowerCase().indexOf(q) !== -1;
    });

    if (!myRules.length) {
      els.mList.innerHTML = '<div class="empty"><div class="empty__big">＋</div>' +
        '还没有自定义词条。上面填一个试试——加完立刻参与检测。</div>';
    } else if (!rows.length) {
      els.mList.innerHTML = '<div class="empty"><div class="empty__big">∅</div>' +
        '没有匹配「' + esc(q) + '」的词条。</div>';
    } else {
      els.mList.innerHTML = rows.map(function (r) {
        return myItemHtml(r, myRules.indexOf(r));
      }).join('');
    }

    var on = myActiveCount();
    if (els.mStats) {
      els.mStats.innerHTML = '我的词库共 <b>' + myRules.length + '</b> 条，其中 <b>' +
        on + '</b> 条生效中' + (myRules.length > rows.length
          ? '，当前显示 <b>' + rows.length + '</b> 条' : '');
    }
    if (els.mMeta) {
      els.mMeta.textContent = myRules.length
        ? (on + ' / ' + myRules.length + ' 条生效')
        : '尚未添加词条';
    }
    updateMyBadge();
  }

  function myItemHtml(r, idx) {
    var off = r.enabled === false;
    var tags = '<span class="sev-tag" data-sev="' + esc(r.severity) + '">' +
      esc(MY_SEV[r.severity] || r.severity) + '</span>' +
      '<span class="tag tag--mine">我的词库</span>';
    if (r.category) tags += '<span class="tag">' + esc(r.category) + '</span>';

    var mineKw = esc(r.keyword);
    var g = r.suggestion
      ? '<div class="ritem__g">' + esc(r.suggestion) + '</div>' : '';
    var law = r.law_ref
      ? '<div class="ritem__law">' + esc(r.law_ref) + '</div>' : '';

    return '<div class="ritem ritem--mine' + (off ? ' is-off' : '') + '">' +
      '<div class="ritem__k">' + mineKw + '</div>' +
      '<div class="ritem__body">' +
      '<div class="ritem__meta">' + tags + '</div>' + g + law +
      '</div>' +
      '<div class="ritem__ops">' +
      '<label class="switch switch--sm" title="停用后不参与检测，词条仍保留">' +
      '<input type="checkbox" data-my-toggle="' + idx + '"' +
      (off ? '' : ' checked') + '>启用</label>' +
      '<button class="linkbtn" type="button" data-my-del="' + idx + '">删除</button>' +
      '</div></div>';
  }

  // ---- 导入 / 导出 ----
  //
  // 导出成**裸数组**而不是包一层 {meta, rules}：桌面端的
  // `rules/user_custom.json` 就是一个裸数组，包一层导过去就读不出来。
  // 互导零摩擦的前提是格式真的只有一种。

  function downloadJson(data, filename) {
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function myRulesPayload() {
    return myRules.map(function (r) {
      return {
        keyword: r.keyword,
        category: r.category,
        severity: r.severity,
        suggestion: r.suggestion || '',
        note: r.note || '',
        law_ref: r.law_ref || '',
      };
    });
  }

  function exportMyRules() {
    if (!myRules.length) {
      setMsg(els.mAddMsg, '词库是空的，没有可导出的内容', true);
      return;
    }
    downloadJson(myRulesPayload(), 'my-rules-' + stamp() + '.json');
    setMsg(els.mAddMsg, '已导出 ' + myRules.length + ' 条为 JSON', false);
  }

  function downloadMyTemplate() {
    downloadJson([{
      keyword: '把这里换成你的关键词',
      category: '内部禁用',
      severity: 'high',
      suggestion: '可选：换成什么更安全',
      note: '',
      law_ref: '可选：依据，例如"公司内部合规要求"',
    }], 'my-rules-template.json');
  }

  function importMyRules(file) {
    var reader = new FileReader();
    reader.onload = function () {
      var data;
      try { data = JSON.parse(String(reader.result)); }
      catch (e) {
        setMsg(els.mAddMsg, '这个文件不是合法的 JSON', true);
        return;
      }
      // 宽容一点：裸数组、{"rules": [...]}、纯字符串数组都收
      if (!Array.isArray(data) && data && Array.isArray(data.rules)) data = data.rules;
      if (!Array.isArray(data)) {
        setMsg(els.mAddMsg, 'JSON 顶层应当是数组，每项一个词条', true);
        return;
      }
      var added = 0, dup = 0, bad = 0;
      data.forEach(function (item) {
        if (typeof item === 'string') item = { keyword: item };
        var res = addMyRule(item || {});
        if (res.ok) added++; else if (res.dup) dup++; else bad++;
      });
      saveMyRules();
      applyMyRules();
      renderMyLib();
      runDetect();
      renderRules();
      var parts = ['新增 ' + added + ' 条'];
      if (dup) parts.push('重复跳过 ' + dup + ' 条');
      if (bad) parts.push('无效跳过 ' + bad + ' 条');
      setMsg(els.mAddMsg, '导入完成：' + parts.join('，'), added === 0);
    };
    reader.onerror = function () { setMsg(els.mAddMsg, '读取文件失败', true); };
    reader.readAsText(file);
  }

  function addMyBulk() {
    var lines = String(els.mBulk.value || '').split(/\r?\n/);
    var added = 0, dup = 0, bad = 0;
    lines.forEach(function (raw) {
      var kw = raw.trim();
      if (!kw || kw.charAt(0) === '#') return;   // 空行与 # 注释行跳过
      var res = addMyRule({
        keyword: kw,
        category: els.mCategory.value.trim() || '内部禁用',
        severity: els.mSeverity.value,
        suggestion: els.mSuggestion.value.trim(),
        law_ref: els.mLaw.value.trim(),
      });
      if (res.ok) added++; else if (res.dup) dup++; else bad++;
    });
    if (!added && !dup && !bad) {
      setMsg(els.mBulkMsg, '没读到有效行（每行一个词）', true);
      return;
    }
    saveMyRules();
    applyMyRules();
    renderMyLib();
    runDetect();
    renderRules();
    els.mBulk.value = '';
    var parts = ['新增 ' + added + ' 条'];
    if (dup) parts.push('重复跳过 ' + dup + ' 条');
    if (bad) parts.push('无效跳过 ' + bad + ' 条');
    setMsg(els.mBulkMsg, parts.join('，'), added === 0);
  }

  function clearMyRules() {
    if (!myRules.length) { setMsg(els.mAddMsg, '词库已经是空的', true); return; }
    if (!window.confirm('确定清空我的词库里的 ' + myRules.length +
        ' 条词吗？清空后无法恢复（建议先导出 JSON 备份）。')) return;
    myRules = [];
    saveMyRules();
    applyMyRules();
    renderMyLib();
    runDetect();
    renderRules();
    setMsg(els.mAddMsg, '已清空', false);
  }

  // ============================================================ 词库浏览 · 筛选

  var RULES_PAGE_SIZE = 40;
  var rulesPage = 0;

  /**
   * 词库浏览的数据源 = 内置词库 + 我的词条。
   *
   * 把两者统一成同一种"规则视图"再过滤，而不是写两套渲染：
   * 用户真正想问的是"哪条规则会管到我这段话"，而不是"这属于哪个仓库"。
   * 来源徽章已经把两者区分开了。
   */
  function rulesUnion() {
    var builtin = (window.GUARDIAN_RULES && window.GUARDIAN_RULES.rules) || [];
    var mine = myRules.map(function (r) {
      return {
        k: r.keyword, c: r.category, s: r.severity, o: 'custom', p: ['*'],
        g: r.suggestion || '', l: r.law_ref || '', n: r.note || '',
        // 停用的词条在词库页仍然列出（否则用户找不到它），但标注为未生效
        _enabled: r.enabled !== false,
      };
    });
    return builtin.concat(mine);
  }

  function rulesFiltered() {
    var all = rulesUnion();
    var q = (els.rSearch.value || '').trim().toLowerCase();
    var src = els.rSource.value;
    var sev = els.rSeverity.value;
    var plat = els.rPlatform.value;
    var scope = els.rScope ? els.rScope.value : '';

    return all.filter(function (r) {
      if (scope === 'builtin' && r.o === 'custom') return false;
      if (scope === 'mine' && r.o !== 'custom') return false;
      if (src && (r.o || '') !== src) return false;
      if (sev && r.s !== sev) return false;
      if (plat) {
        var p = r.p || ['*'];
        // "仅某平台"= 明确点名该平台且不是全平台规则
        if (p.indexOf(plat) === -1 || p.indexOf('*') !== -1) return false;
      }
      if (q) {
        var hay = [r.k, r.c, r.g, r.l, r.n, (r.r || []).join(' ')]
          .join(' ').toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  /** 窄屏下把"已启用几个筛选条件"标在筛选按钮上，避免筛选后忘了自己筛过什么。 */
  function syncFilterBadge() {
    if (!els.rFilterN) return;
    var n = 0;
    if (els.rSource.value) n++;
    if (els.rSeverity.value) n++;
    if (els.rPlatform.value) n++;
    if (els.rScope && els.rScope.value) n++;
    els.rFilterN.textContent = n ? String(n) : '';
    els.rFilterN.hidden = !n;
  }

  // ============================================================ 词库健康度

  /**
   * 词库复核状态。
   *
   * 为什么值得在页面上单开一块
   * --------------------------
   * 规则驱动型工具不会"坏掉"，只会**过期**：平台规则改了、监管口径变了，
   * 静态词库仍在照常打分，只是分数开始失真。功能不报错、测试不变红，
   * 这是最隐蔽也最致命的失效模式。所以把它摆到明面上。
   *
   * 台账里只存**事实**（上次复核日、复核周期），"还剩几天"在这里现算。
   * 一旦把剩余天数写进产物文件，产物就会每天漂移，双端对拍门禁天天变红。
   */
  var REVIEW_SOON_RATIO = 0.2;

  function daysSince(dateStr, today) {
    var p = String(dateStr || '').split('-');
    if (p.length !== 3) return null;
    var from = new Date(+p[0], +p[1] - 1, +p[2]);
    if (isNaN(from.getTime())) return null;
    return Math.round((today - from) / 86400000);
  }

  function reviewStatus(row, today) {
    var elapsed = daysSince(row.last, today);
    if (elapsed === null || !row.days) {
      return { status: 'unknown', elapsed: null, remain: null };
    }
    var remain = row.days - elapsed;
    var status = remain < 0
      ? 'overdue'
      : (remain <= row.days * REVIEW_SOON_RATIO ? 'due_soon' : 'ok');
    return { status: status, elapsed: elapsed, remain: remain };
  }

  var REVIEW_LABEL = {
    ok: '有效', due_soon: '临近复核', overdue: '已过期', unknown: '未登记',
  };

  //: 依据是"法条"的来源。platform / blue_v 的依据是平台规范，不在此列。
  var LAW_BASED = /^(ad_law|industry:|regex)/;

  function renderHealth() {
    if (!els.rHealthBody) return;
    var meta = (window.GUARDIAN_RULES && window.GUARDIAN_RULES.meta) || {};
    var log = meta.review_log || {};
    var cov = meta.coverage_by_source || {};

    var srcs = Object.keys(log);
    if (!srcs.length) {
      els.rHealthBrief.textContent = '未登记复核信息';
      els.rHealthBody.innerHTML = '<div class="health__empty">' +
        '这份词库产物里没有复核台账，无法判断规则是否已过期。</div>';
      return;
    }

    var today = new Date();
    var rows = srcs.map(function (src) {
      var r = log[src] || {};
      var c = cov[src] || { n: 0, ref: 0 };
      return { src: src, row: r, st: reviewStatus(r, today), n: c.n, ref: c.ref };
    });

    var overdue = rows.filter(function (x) { return x.st.status === 'overdue'; });
    var soon = rows.filter(function (x) { return x.st.status === 'due_soon'; });

    // 依据覆盖率只对"法条类来源"统计。平台规则/蓝V规则的依据是平台规范
    // 而非法律，把它们算进分母会把真实覆盖率压低，反过来说也说不通。
    var lawSrcs = rows.filter(function (x) { return LAW_BASED.test(x.src); });
    var lawRef = lawSrcs.reduce(function (s, x) { return s + x.ref; }, 0);
    var lawAll = lawSrcs.reduce(function (s, x) { return s + x.n; }, 0);
    var pctText = lawAll ? Math.round(lawRef * 100 / lawAll) + '%' : '—';

    // 摘要先给结论，明细按需展开——健康度是"扫一眼就知道"的指标
    els.rHealthDot.className = 'health__dot health__dot--' +
      (overdue.length ? 'bad' : (soon.length ? 'warn' : 'ok'));
    els.rHealthBrief.textContent = overdue.length
      ? (overdue.length + ' 个来源已超过复核周期')
      : (soon.length
        ? (soon.length + ' 个来源临近复核')
        : ('全部 ' + rows.length + ' 个来源在复核周期内 · ' +
          '法条类词库 ' + lawRef + '/' + lawAll + ' 条标注条款依据（' + pctText + '）'));

    var body = rows.map(function (x) {
      var remain = x.st.remain === null ? '—' : (x.st.remain + ' 天');
      return '<tr>' +
        '<td>' + esc(x.row.label || x.src) + '</td>' +
        '<td class="num">' + x.n + '</td>' +
        '<td class="num">' + (x.n ? (x.ref + ' / ' + x.n) : '—') + '</td>' +
        '<td class="num">' + esc(x.row.last || '—') + '</td>' +
        '<td class="num">' + (x.row.days ? x.row.days + ' 天' : '—') + '</td>' +
        '<td class="num">' + esc(remain) + '</td>' +
        '<td><span class="hstat" data-status="' + esc(x.st.status) + '">' +
        esc(REVIEW_LABEL[x.st.status]) + '</span></td>' +
        '</tr>';
    }).join('');

    // 超期/临近的来源才展开依据与复核要点——不超期的不占视线
    var notes = rows.filter(function (x) { return x.st.status !== 'ok'; })
      .map(function (x) {
        return '<div class="health__note"><b>' + esc(x.row.label || x.src) + '</b>' +
          '<span>依据：' + esc(x.row.basis || '—') + '</span>' +
          '<span>' + esc(x.row.note || '') + '</span></div>';
      }).join('');

    els.rHealthBody.innerHTML =
      '<table><thead><tr><th>来源</th><th>规则</th><th>标注依据</th>' +
      '<th>上次复核</th><th>周期</th><th>剩余</th><th>状态</th>' +
      '</tr></thead><tbody>' + body + '</tbody></table>' +
      (notes ? '<div class="health__notes">' + notes + '</div>' : '') +
      '<div class="health__legend">「标注依据」= 该来源中有多少条规则写明具体法条。' +
      '平台规则与蓝V规则的依据是平台规范而非法律，因此不标注法条，这是预期行为。</div>';
  }

  // ============================================================ 词库浏览 · 列表

  function renderRules() {
    var list = rulesFiltered();
    var pages = Math.max(1, Math.ceil(list.length / RULES_PAGE_SIZE));
    if (rulesPage >= pages) rulesPage = pages - 1;
    if (rulesPage < 0) rulesPage = 0;

    var slice = list.slice(rulesPage * RULES_PAGE_SIZE,
      rulesPage * RULES_PAGE_SIZE + RULES_PAGE_SIZE);

    var total = rulesUnion().length;
    els.rStats.innerHTML = '共 <b>' + total + '</b> 条规则（内置 ' +
      (((window.GUARDIAN_RULES || {}).rules || []).length) + ' + 我的 ' +
      myRules.length + '），当前筛选命中 <b>' + list.length + '</b> 条';

    if (!list.length) {
      els.rList.innerHTML = '<div class="empty"><div class="empty__big">∅</div>' +
        '没有匹配的规则。换个关键词，或把筛选条件放宽。</div>';
    } else {
      els.rList.innerHTML = slice.map(ruleItemHtml).join('');
    }

    els.rPageInfo.textContent = '第 ' + (rulesPage + 1) + ' / ' + pages + ' 页';
    els.rPrev.disabled = rulesPage <= 0;
    els.rNext.disabled = rulesPage >= pages - 1;
    syncFilterBadge();
  }

  function ruleItemHtml(r) {
    var tags = '<span class="sev-tag" data-sev="' + esc(r.s) + '">' +
      SEV_LABEL[r.s] + '</span>';

    var src = SOURCE_LABEL[r.o] || r.o;
    if (src) {
      tags += '<span class="tag ' + (r.o === 'custom' ? 'tag--mine' : 'tag--src') + '">' +
        esc(src) + '</span>';
    }

    if (r.c) tags += '<span class="tag">' + esc(r.c) + '</span>';

    var p = r.p || ['*'];
    if (p.indexOf('*') === -1) {
      tags += '<span class="tag tag--src">' +
        p.map(function (k) { return esc(PLATFORM_LABEL[k] || k); }).join('/') + '</span>';
    }
    if (r.m === 'regex') tags += '<span class="tag tag--warn">组合正则</span>';
    if (r.sa) tags += '<span class="tag" title="同一词在蓝V号与普通号下定级不同">蓝V定级不同</span>';
    if (r._enabled === false) {
      tags += '<span class="tag tag--off" title="这个词条已在「我的词库」里停用，不参与检测">已停用</span>';
    }

    var g = r.g ? '<div class="ritem__g">' + esc(r.g) + '</div>' : '';
    var rep = (r.r && r.r.length)
      ? '<div class="ritem__r">可改为：' + r.r.map(esc).join(' / ') + '</div>' : '';
    // 依据：条款号 + 说明。词库页是唯一能逐条看清"我们的规则站在哪些
    // 法条上"的地方，缺了它就退化成一张违禁词表。
    var law = (r.l || r.n)
      ? '<div class="ritem__law">' +
        (r.l ? '<code>' + esc(r.l) + '</code>' : '') +
        (r.l && r.n ? ' · ' : '') +
        (r.n ? esc(r.n) : '') +
        '</div>'
      : '';

    return '<div class="ritem' + (r._enabled === false ? ' is-off' : '') + '">' +
      '<div class="ritem__k">' + esc(r.k) + '</div>' +
      '<div class="ritem__body">' +
      '<div class="ritem__meta">' + tags + '</div>' +
      g + rep + law +
      '</div></div>';
  }

  // ============================================================ 最近检测

  /**
   * 留痕与隐私的取舍。
   *
   * 这个页面一直宣称"文案不出本机、关掉即消失"。如果为了做"历史记录"
   * 就把原文默默写进 localStorage，那句宣称就成了假话。所以这里的选择是：
   *
   *   - 默认**只记元数据**（时间 / 分数 / 命中数 / 风险词），不落原文
   *   - 想回看原文，用户显式打开开关；关掉开关时**已存原文一并清除**
   *   - 数据只在 localStorage，清空按钮随时可用
   *
   * 隐私默认关闭，本身就比"默认全存、藏在设置里"更值得说。
   */
  var HIST_KEY = 'adcompli-history';
  var HIST_TEXT_KEY = 'adcompli-store-text';
  var HIST_MAX = 12;
  var HIST_SETTLE_MS = 2500;   // 停笔 2.5 秒才算"一次检测"，避免边打边记
  var historyTimer = null;

  function histStoreOn() {
    return !!(els.histStoreText && els.histStoreText.checked);
  }

  function loadHist() {
    try {
      var raw = JSON.parse(localStorage.getItem(HIST_KEY) || '[]');
      return Object.prototype.toString.call(raw) === '[object Array]' ? raw : [];
    } catch (e) { return []; }
  }

  function saveHist(list) {
    try { localStorage.setItem(HIST_KEY, JSON.stringify(list.slice(0, HIST_MAX))); }
    catch (e) { /* 无痕模式或配额满：静默放弃，不影响检测 */ }
  }

  function fmtClock(ts) {
    var d = new Date(ts);
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
      p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function scheduleHistory(text, res) {
    if (historyTimer) clearTimeout(historyTimer);
    if (!text.trim() || !res) return;
    historyTimer = setTimeout(function () {
      // 期间用户又改了 → 那是个半成品，不记
      if (els.input.value !== text) return;
      pushHistory(text, res);
    }, HIST_SETTLE_MS);
  }

  function pushHistory(text, res) {
    var list = loadHist();
    var len = Array.from(text).length;
    var top = list[0];
    // 连续检测同一段（分/命中数/长度都一致）不重复记，否则调参数会刷屏
    if (top && top.score === res.summary.score && top.n === res.findings.length &&
        top.len === len) return;

    var entry = {
      t: Date.now(),
      score: res.summary.score,
      risk: res.summary.riskLevel,
      n: res.findings.length,
      len: len,
      words: res.findings.slice(0, 3).map(function (f) { return f.matchedText; }),
    };
    if (histStoreOn()) entry.text = text;

    list.unshift(entry);
    saveHist(list);
    renderHistory();
  }

  function renderHistory() {
    var list = loadHist();
    var on = histStoreOn();

    els.histHint.innerHTML = on
      ? '已开启：原文存在<b>你自己的浏览器</b>里（localStorage），不上传任何服务器。点记录可回看，关掉开关会一并清除已存原文。'
      : '默认<b>不保存原文</b>，只记时间 / 分数 / 命中数。想回看原文请打开左侧开关——数据只留在你自己的浏览器里。';

    if (!list.length) {
      els.histList.innerHTML = '<div class="hist__hint">还没有记录。停下约 3 秒后会自动记一条。</div>';
      return;
    }

    els.histList.innerHTML = list.map(function (e, i) {
      var color = scoreColor(e.score);
      var body;
      if (on && e.text) {
        var chars = Array.from(e.text);
        body = esc(chars.slice(0, 42).join('').replace(/\s+/g, ' ')) +
          (chars.length > 42 ? '…' : '');
      } else {
        body = e.words && e.words.length
          ? esc(e.words.join('、'))
          : '<span style="color:var(--ok)">未发现风险词</span>';
      }
      var clickable = !!(on && e.text);
      return '<div class="hitem' + (clickable ? ' hitem--click' : '') + '"' +
        (clickable ? ' role="button" tabindex="0" data-hi="' + i + '"' : '') + '>' +
        '<span class="hitem__score" style="color:' + color + '">' + e.score + '</span>' +
        '<span class="hitem__txt">' + body + '</span>' +
        '<span class="hitem__time">' + fmtClock(e.t) + '</span>' +
        '</div>';
    }).join('');
  }

  function restoreHistory(i) {
    var e = loadHist()[i];
    if (!e || !e.text) return;
    els.input.value = e.text;
    runDetect();
    els.input.focus();
  }

  function clearHistory() {
    saveHist([]);
    renderHistory();
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

  var batchTimer = null;
  function scheduleBatch() {
    if (batchTimer) clearTimeout(batchTimer);
    batchTimer = setTimeout(runBatch, 220);
  }

  var rulesTimer = null;
  function scheduleRules() {
    if (rulesTimer) clearTimeout(rulesTimer);
    rulesTimer = setTimeout(function () { rulesPage = 0; renderRules(); }, 140);
  }

  /** 读取"是否在本机保存文案"的偏好，并据此渲染最近检测。 */
  function initHistoryPref() {
    var on = false;
    try { on = localStorage.getItem(HIST_TEXT_KEY) === '1'; } catch (e) { /* ignore */ }
    if (els.histStoreText) els.histStoreText.checked = on;
    renderHistory();
  }

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

    // 存/覆盖/取消"改前"基线。文案没动过时再点一下 = 取消，避免用户
    // 存了一个基线却不知道怎么撤。
    els.baselineBtn.addEventListener('click', function () {
      var text = els.input.value;
      if (!text.trim()) return;

      if (baseline && text === baseline.text) {
        baseline = null;
      } else {
        baseline = {
          text: text,
          score: lastResult ? lastResult.summary.score : 100,
          findings: lastResult ? lastResult.findings.slice() : [],
        };
      }
      // 按钮文案与对比块都由 render 统一刷新，这里不用单独改
      runDetect();
    });

    els.clearBtn.addEventListener('click', function () {
      els.input.value = '';
      // 清空意味着"这一轮结束了"，基线一并撤掉，免得下一段新文案
      // 莫名其妙地跟上一段的分数作对比。
      baseline = null;
      els.input.focus();
      runDetect();
    });

    els.themeBtn.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      applyTheme(cur === 'dark' ? 'light' : 'dark');
    });

    // ---- 标签页 ----
    if (els.tabbar) {
      els.tabbar.addEventListener('click', function (e) {
        var btn = e.target.closest ? e.target.closest('.tabs__btn') : null;
        if (btn) switchTab(btn.getAttribute('data-tab'));
      });
    }

    // ---- 批量检测 ----
    els.bInput.addEventListener('input', function () {
      els.bCounter.textContent = parseBatch(els.bInput.value).length + ' 条';
      scheduleBatch();
    });
    ['bPlatform', 'bAccountType', 'bIndustry', 'bVariants'].forEach(function (id) {
      els[id].addEventListener('change', runBatch);
    });
    els.bSampleBtn.addEventListener('click', function () {
      els.bInput.value = BATCH_SAMPLE;
      runBatch();
    });
    els.bClearBtn.addEventListener('click', function () {
      els.bInput.value = '';
      runBatch();
      els.bInput.focus();
    });
    els.bExportCsv.addEventListener('click', exportBatchCsv);
    els.bCopyPass.addEventListener('click', copyPassList);

    // ---- 词库浏览 ----
    els.rSearch.addEventListener('input', scheduleRules);
    ['rSource', 'rSeverity', 'rPlatform', 'rScope'].forEach(function (id) {
      if (!els[id]) return;
      els[id].addEventListener('change', function () {
        rulesPage = 0;
        renderRules();
      });
    });
    els.rPrev.addEventListener('click', function () {
      if (rulesPage > 0) { rulesPage--; renderRules(); }
    });
    els.rNext.addEventListener('click', function () {
      rulesPage++; renderRules();
    });

    // ---- 我的词库 ----
    if (els.mForm) {
      els.mForm.addEventListener('submit', function (e) {
        e.preventDefault();          // 不加这句，回车会刷新整页，刚填的内容全没了
        var res = addMyRule({
          keyword: els.mKeyword.value,
          category: els.mCategory.value,
          severity: els.mSeverity.value,
          suggestion: els.mSuggestion.value,
          law_ref: els.mLaw.value,
        });
        if (!res.ok) { setMsg(els.mAddMsg, res.msg, true); return; }
        saveMyRules();
        applyMyRules();
        renderMyLib();
        runDetect();
        renderRules();
        els.mKeyword.value = '';
        els.mSuggestion.value = '';
        els.mLaw.value = '';
        els.mKeyword.focus();
        setMsg(els.mAddMsg, res.msg || '已加入词库，立刻生效', false);
      });
    }
    if (els.mBulkBtn) els.mBulkBtn.addEventListener('click', addMyBulk);
    if (els.mList) {
      els.mList.addEventListener('click', function (e) {
        var del = e.target.closest ? e.target.closest('[data-my-del]') : null;
        if (!del) return;
        var idx = Number(del.getAttribute('data-my-del'));
        var row = myRules[idx];
        if (!row) return;
        myRules.splice(idx, 1);
        saveMyRules();
        applyMyRules();
        renderMyLib();
        runDetect();
        renderRules();
        setMsg(els.mAddMsg, '已删除「' + row.keyword + '」', false);
      });
      // 停用/启用：用 change 而不是 click —— 直接点 label 或键盘操作
      // 都不会触发 click，用 change 三种操作方式都能覆盖。
      els.mList.addEventListener('change', function (e) {
        var box = e.target.closest ? e.target.closest('[data-my-toggle]') : null;
        if (!box) return;
        var idx = Number(box.getAttribute('data-my-toggle'));
        if (!myRules[idx]) return;
        myRules[idx].enabled = box.checked;
        saveMyRules();
        applyMyRules();
        renderMyLib();
        runDetect();
        renderRules();
      });
    }
    if (els.mSearch) {
      els.mSearch.addEventListener('input', function () { renderMyLib(); });
    }
    if (els.mExportBtn) els.mExportBtn.addEventListener('click', exportMyRules);
    if (els.mTemplateBtn) els.mTemplateBtn.addEventListener('click', downloadMyTemplate);
    if (els.mClearBtn) els.mClearBtn.addEventListener('click', clearMyRules);
    if (els.mImportBtn && els.mFile) {
      els.mImportBtn.addEventListener('click', function () { els.mFile.click(); });
      els.mFile.addEventListener('change', function () {
        if (els.mFile.files && els.mFile.files[0]) importMyRules(els.mFile.files[0]);
        els.mFile.value = '';      // 清空，否则同一个文件第二次选不会触发 change
      });
    }

    // ---- 最近检测 ----
    els.histStoreText.addEventListener('change', function () {
      var on = histStoreOn();
      try { localStorage.setItem(HIST_TEXT_KEY, on ? '1' : '0'); } catch (e) { /* ignore */ }
      // 关掉开关时把已经存下的原文一并清除 —— 用户关它就是要"别再留着"
      if (!on) {
        var list = loadHist();
        list.forEach(function (e) { delete e.text; });
        saveHist(list);
      }
      renderHistory();
    });
    els.histClear.addEventListener('click', clearHistory);
    els.histList.addEventListener('click', function (e) {
      var row = e.target.closest ? e.target.closest('.hitem--click') : null;
      if (row) restoreHistory(Number(row.getAttribute('data-hi')));
    });
    els.histList.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var row = e.target.closest ? e.target.closest('.hitem--click') : null;
      if (!row) return;
      e.preventDefault();
      restoreHistory(Number(row.getAttribute('data-hi')));
    });

    bindDemoButtons();
  }

  // ============================================================ 启动

  function fatal(msg) {
    els.engineInfo.textContent = msg;
    els.findings.innerHTML = '<div class="empty"><div class="empty__big">⚠</div>' + esc(msg) + '</div>';
  }

  // ============================================================ 下拉填充

  /** 填充行业下拉：内容全部来自词库产物（见 PACKS 的说明）。 */
  function fillIndustrySelect() {
    ['industry', 'bIndustry'].forEach(function (id) {
      var sel = els[id];
      if (!sel) return;
      PACKS.forEach(function (p) {
        var opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = (p.short || p.name) + '（' + p.rule_count + ' 条）';
        sel.appendChild(opt);
      });
      // "仅通用词库"是特殊项，排在一长串行业包之后更好找
      var none = sel.querySelector('option[value="none"]');
      if (none) sel.appendChild(none);
    });
  }

  /** 填充来源下拉：内置来源固定，行业包来源随产物生成。 */
  function fillSourceSelect() {
    if (!els.rSource) return;
    var add = function (val, text) {
      var o = document.createElement('option');
      o.value = val;
      o.textContent = text;
      els.rSource.appendChild(o);
    };
    add('ad_law', '广告法');
    add('platform', '平台规则');
    add('blue_v', '蓝V规则');
    PACKS.forEach(function (p) {
      add('industry:' + p.id, (p.short || p.name) + '红线（' + p.rule_count + '）');
    });
    add('regex', '组合正则');
    add('custom', '我的词库');
  }

  /**
   * 窄屏默认收起"检测设置"。
   *
   * 手机上把三行设置全摊开，首屏就只剩下设置面板——而这几项选好一次基本不用再动。
   * 桌面端放着不动（横向空间本来就有余）。
   */
  /**
   * 窄屏把「检测设置」折成一行摘要 —— 平台/账号/行业/变体几个控件在小屏上
   * 要占掉整屏，用户根本滚不到下面的检测结果。
   *
   * 两个容易做错的地方：
   *  1. 只在**跨过断点那一刻**重设，而不是每次 resize 都设。移动端滚动时
   *     地址栏收放会持续触发 resize，每次都折回去的话，用户手动展开的设置
   *     会被立刻抢走。
   *  2. 切回宽屏时恢复的是**各面板自己的初始状态**，不是一律展开 ——
   *     批量页的设置本来就是收起的，强行打开等于改掉了桌面端原有行为。
   */
  function initSettingsCollapse() {
    var ids = ['settingsBox', 'bSettingsBox'];
    var initial = {};
    ids.forEach(function (id) { if (els[id]) initial[id] = els[id].open; });

    var apply = function (narrow) {
      ids.forEach(function (id) {
        if (els[id]) els[id].open = narrow ? false : initial[id];
      });
    };

    var wasNarrow = isNarrow();
    apply(wasNarrow);
    window.addEventListener('resize', function () {
      var now = isNarrow();
      if (now === wasNarrow) return;
      wasNarrow = now;
      apply(now);
    });
  }

  function init() {
    cacheEls();
    fillIndustrySelect();
    fillSourceSelect();
    initSettingsCollapse();
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

    // 自定义词库要在首次检测**之前**装进引擎，否则用户会看到"加了词但没生效"
    myRules = loadMyRules();
    applyMyRules();

    var meta = window.GUARDIAN_RULES.meta || {};
    var total = meta.rule_count || window.GUARDIAN_RULES.rules.length;
    els.heroRuleCount.textContent = String(total);
    els.fRuleCount.textContent = String(total);
    // 「我的词库」说明里的"内置 N 条"必须跟着词库走。写死在 HTML 里的话，
    // 每次扩词都要记得回来改文案 —— 而那种"记得"迟早会忘。
    if (els.mBuiltin) els.mBuiltin.textContent = String(total);
    els.engineInfo.textContent = '词库 ' + total + ' 条 · 引擎 ' + (meta.engine || '—');

    // 标签页上的规则数角标
    if (els.tabRuleCount) els.tabRuleCount.textContent = String(total);

    renderHealth();
    fillDiffStats();
    initHistoryPref();
    renderMyLib();
    runDetect();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
