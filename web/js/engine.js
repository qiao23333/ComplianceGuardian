/**
 * 合规检测引擎 · 浏览器端实现（零依赖）
 * ============================================================
 *
 * 这份代码是 `guardian/` Python 内核在前端的等价实现，目标只有一个：
 * **让作品集页面点开就能试，不用下载、不用后端，文案不出浏览器。**
 *
 * 与大模型无关——合规判定是确定性的法规问题，靠的是词库 + 匹配，
 * 不是生成。这也让它能在毫秒级离线跑完。
 *
 * 镜像的能力（与 Python 端逐一对齐）：
 *   1. Aho-Corasick 多模式匹配（一次扫描命中全部关键词）
 *   2. 归一化管线：去噪声（空格/零宽/下划线）→ 全角转半角 → 繁转简 → 谐音替换
 *      全程带 index_map，命中坐标可精确回映射到原文（高亮不跑偏）
 *   3. 变体命中识别：命中片段 != 关键词本身 → 标记为规避写法
 *   4. 正则兜底（"最X""极X"这类组合型极限词）
 *   5. 去重择优：字面 > 变体 > 正则，正则只补词库未覆盖的区间
 *   6. 反误杀三道防线：全局豁免词组 + 规则级 contextExcludes + 短词降级
 *   7. 风险评分与四级风险等级
 *
 * 与 Python 端的已知差异（诚实说明，不假装完全一致）：
 *   - **不含拼音变体通道**：需要中文拼音库（pypinyin），前端体积不划算，
 *     且该通道天生误报率高（相邻汉字的拼音会跨字拼出别的关键词）。
 *     拼音规避检测请用桌面端。
 *   - 因此对"用拼音写的规避"（如 jiaweixin）前端不报，属预期行为。
 */
(function (global) {
  'use strict';

  var SEV_ORDER = ['critical', 'high', 'medium', 'low'];
  var SEV_WEIGHT = { critical: 10, high: 5, medium: 2, low: 0 };

  // ============================================================ Aho-Corasick

  /**
   * 多模式匹配自动机。
   * 一次线性扫描即可找出文本中出现的**全部**关键词，与关键词数量无关，
   * 这是"上千条词库也能毫秒级出结果"的原因。
   */
  function AhoCorasick() {
    this.nodes = [{ next: new Map(), fail: 0, out: [] }];
  }

  AhoCorasick.prototype.add = function (chars, payload) {
    var cur = 0;
    for (var i = 0; i < chars.length; i++) {
      var ch = chars[i];
      var nx = this.nodes[cur].next.get(ch);
      if (nx === undefined) {
        nx = this.nodes.length;
        this.nodes.push({ next: new Map(), fail: 0, out: [] });
        this.nodes[cur].next.set(ch, nx);
      }
      cur = nx;
    }
    this.nodes[cur].out.push(payload);
  };

  AhoCorasick.prototype.build = function () {
    var queue = [];
    var i;
    var rootNext = Array.from(this.nodes[0].next.values());
    for (i = 0; i < rootNext.length; i++) {
      this.nodes[rootNext[i]].fail = 0;
      queue.push(rootNext[i]);
    }
    while (queue.length) {
      var u = queue.shift();
      var entries = Array.from(this.nodes[u].next.entries());
      for (i = 0; i < entries.length; i++) {
        var ch = entries[i][0];
        var v = entries[i][1];
        var f = this.nodes[u].fail;
        while (f !== 0 && !this.nodes[f].next.has(ch)) f = this.nodes[f].fail;
        var cand = this.nodes[f].next.get(ch);
        this.nodes[v].fail = cand !== undefined && cand !== v ? cand : 0;
        // 失败指针的命中集合并入自身（保证不漏报重叠模式）
        var fo = this.nodes[this.nodes[v].fail].out;
        if (fo.length) this.nodes[v].out = this.nodes[v].out.concat(fo);
        queue.push(v);
      }
    }
  };

  /** 返回 [{start, end, len, payload}]，坐标为**字符**下标（非 UTF-16 码元）。 */
  AhoCorasick.prototype.search = function (chars) {
    var res = [];
    var cur = 0;
    for (var i = 0; i < chars.length; i++) {
      var ch = chars[i];
      while (cur !== 0 && !this.nodes[cur].next.has(ch)) cur = this.nodes[cur].fail;
      var nxt = this.nodes[cur].next.get(ch);
      cur = nxt === undefined ? 0 : nxt;
      var out = this.nodes[cur].out;
      for (var j = 0; j < out.length; j++) {
        var p = out[j];
        res.push({
          start: i - p.chars.length + 1,
          end: i + 1,
          len: p.chars.length,
          payload: p,
        });
      }
    }
    return res;
  };

  // ============================================================ 归一化

  var FULLWIDTH_START = 0xff01;
  var FULLWIDTH_END = 0xff5e;

  function toHalfWidth(ch) {
    var code = ch.charCodeAt(0);
    if (code >= FULLWIDTH_START && code <= FULLWIDTH_END) {
      return String.fromCharCode(code - 0xfee0);
    }
    return ch;
  }

  /**
   * 归一化：把"加了规避花招"的文本还原成规范形式。
   * 返回 { text, indexMap, chars }，indexMap[j] = 归一化第 j 个字符对应的原文**字符**下标。
   */
  function normalize(text, cfg) {
    var noise = cfg.noiseSet;
    var homophone = cfg.homophone;
    var t2s = cfg.t2s;

    var chars = Array.from(text);
    var buf = [];
    var indexMap = [];
    var i;

    // 步骤 1：去噪声（会删字符，重建 indexMap）
    for (i = 0; i < chars.length; i++) {
      if (noise.has(chars[i])) continue;
      buf.push(chars[i]);
      indexMap.push(i);
    }

    // 步骤 2~4：等长 1:1 替换（indexMap 含义不变）
    var out = new Array(buf.length);
    for (i = 0; i < buf.length; i++) {
      var c = toHalfWidth(buf[i]);
      if (t2s && t2s[c]) c = t2s[c];
      if (homophone && homophone[c]) c = homophone[c];
      out[i] = c;
    }

    return { text: out.join(''), chars: out, indexMap: indexMap };
  }

  // ============================================================ 引擎

  function GuardianEngine(data) {
    this.data = data;
    this.severityMeta = data.severity || {};
    this.noiseSet = new Set(data.noise || []);
    this.homophone = data.homophone || {};
    this.t2s = data.t2s || {};
    this.shortMaxLen = data.short_keyword_max_len != null ? data.short_keyword_max_len : 1;
    this.downgradeCats = new Set(data.downgrade_categories || []);

    // 全局豁免词组（扁平化：命中落在其中即视为正常用法）
    this.exemptPhrases = [];
    var ex = data.exempt || {};
    Object.keys(ex).forEach(function (k) {
      (ex[k] || []).forEach(function (p) { this.exemptPhrases.push(p); }, this);
    }, this);

    // 预建自动机：同一关键词可能对应多条规则（跨平台），故 payload 是数组
    this.exactIndex = new Map();
    this.regexRules = [];
    this.ruleById = {};
    for (var i = 0; i < data.rules.length; i++) {
      var r = data.rules[i];
      r._id = 'r' + i;                       // 稳定 ID（去重/豁免缓存用）
      this.ruleById[r._id] = r;
      if (r.m === 'regex') {
        this.regexRules.push(r);
      } else {
        var list = this.exactIndex.get(r.k);
        if (list) list.push(r);
        else this.exactIndex.set(r.k, [r]);
      }
    }
  }

  GuardianEngine.prototype.severityOf = function (rule, accountType) {
    if (rule.sa && rule.sa[accountType]) return rule.sa[accountType];
    return rule.s;
  };

  GuardianEngine.prototype.matchesPlatform = function (rule, platform) {
    if (platform === 'all') return true;
    var p = rule.p || ['*'];
    return p.indexOf('*') !== -1 || p.indexOf(platform) !== -1;
  };

  /** 按平台 / 账号类型 / 行业包 / 最低严重度筛出本次参与检测的规则。 */
  GuardianEngine.prototype.filterRules = function (opts) {
    var self = this;
    var out = [];
    for (var i = 0; i < this.data.rules.length; i++) {
      var r = this.data.rules[i];
      if (!this.matchesPlatform(r, opts.platform)) continue;
      // 行业：未指定 → 仅通用；指定 → 通用 + 指定行业包
      if (opts.industries && opts.industries.length) {
        if (r.i && opts.industries.indexOf(r.i) === -1) continue;
      } else if (r.i) {
        continue;
      }
      if (SEV_WEIGHT[self.severityOf(r, opts.accountType)] < SEV_WEIGHT[opts.minSeverity]) {
        continue;
      }
      out.push(r);
    }
    return out;
  };

  /** 为本次生效的规则构建自动机（只喂相关关键词，换取速度）。 */
  GuardianEngine.prototype.buildAutomaton = function (activeRules) {
    var activeSet = new Set();
    for (var a = 0; a < activeRules.length; a++) activeSet.add(activeRules[a]._id);

    var ac = new AhoCorasick();
    var done = new Set();
    for (var i = 0; i < activeRules.length; i++) {
      var r = activeRules[i];
      if (r.m === 'regex' || done.has(r.k)) continue;
      done.add(r.k);
      var byKw = this.exactIndex.get(r.k) || [];
      var subset = byKw.filter(function (x) { return activeSet.has(x._id); });
      if (!subset.length) continue;
      var chars = Array.from(r.k);
      ac.add(chars, { chars: chars, rules: subset, kw: r.k });
    }
    ac.build();
    return ac;
  };

  /** 默认允许自动改写的规则（与 Python 端 from_legacy 口径一致）。 */
  function defaultAllowReplace(rule) {
    var kwLen = Array.from(rule.k).length;
    return kwLen > 1 || String(rule.c || '').indexOf('极限') === -1;
  }

  function rankOf(matchType) {
    if (matchType === 'keyword') return 0;
    if (matchType === 'variant') return 1;
    return 2;
  }

  function makeHit(start, end, keyword, rule, matchType, severity, allowReplace, extra) {
    var h = {
      start: start,
      end: end,
      keyword: keyword,
      ruleId: rule._id,
      category: rule.c,
      severity: severity,
      source: rule.o,
      industry: rule.i || null,
      platform: (rule.p && rule.p[0]) || '*',
      suggestion: rule.g || '',
      replacements: rule.r || [],
      allowAutoReplace: allowReplace,
      matchType: matchType,
      variantOf: null,
      confidence: matchType === 'variant' ? 0.8 : 1.0,
      contextExcludes: rule.x || null,
    };
    if (extra) for (var k in extra) h[k] = extra[k];
    return h;
  }

  /** 贪心保留不重叠命中：位置 → 最长 → 类型(字面>变体) → 高严重度。 */
  function greedyPick(hits) {
    hits = hits.slice().sort(function (a, b) {
      if (a.start !== b.start) return a.start - b.start;
      if (b.keyword.length !== a.keyword.length) return b.keyword.length - a.keyword.length;
      var ra = rankOf(a.matchType), rb = rankOf(b.matchType);
      if (ra !== rb) return ra - rb;
      return SEV_WEIGHT[b.severity] - SEV_WEIGHT[a.severity];
    });
    var kept = [];
    for (var i = 0; i < hits.length; i++) {
      var h = hits[i], overlap = false;
      for (var j = 0; j < kept.length; j++) {
        if (h.start < kept[j].end && h.end > kept[j].start) { overlap = true; break; }
      }
      if (!overlap) kept.push(h);
    }
    return kept;
  }

  /** 合并去重：字面/变体优先，正则仅作兜底补未覆盖区间。 */
  function dedupe(hits) {
    var curated = [], fallback = [];
    for (var i = 0; i < hits.length; i++) {
      (hits[i].matchType === 'regex' ? fallback : curated).push(hits[i]);
    }
    var kept = greedyPick(curated);
    fallback.sort(function (a, b) {
      if (a.start !== b.start) return a.start - b.start;
      return b.keyword.length - a.keyword.length;
    });
    for (var j = 0; j < fallback.length; j++) {
      var h = fallback[j], overlap = false;
      for (var k = 0; k < kept.length; k++) {
        if (h.start < kept[k].end && h.end > kept[k].start) { overlap = true; break; }
      }
      if (!overlap) kept.push(h);
    }
    return kept.sort(function (a, b) { return a.start - b.start; });
  }

  /**
   * 主入口。
   * @param {string} text
   * @param {object} [options]
   * @returns {{text, findings, summary, safeText, meta}}
   */
  GuardianEngine.prototype.detect = function (text, options) {
    var t0 = (global.performance || Date).now();
    var opts = Object.assign({
      platform: 'all',
      accountType: 'non_blue_v',
      industries: (this.data.meta && this.data.meta.industries) || [],
      useVariants: true,
      minSeverity: 'low',
      autoReplace: false,
      maxTextLen: 20000,
    }, options || {});

    if (!text || !text.trim()) {
      return {
        text: text,
        findings: [],
        summary: { score: 100, riskLevel: '基本合规', counts: { critical: 0, high: 0, medium: 0, low: 0 }, textLength: text ? text.length : 0 },
        safeText: text,
        meta: { elapsedMs: 0, ruleCount: 0 },
      };
    }
    if (text.length > opts.maxTextLen) text = text.slice(0, opts.maxTextLen);

    var active = this.filterRules(opts);
    var ac = this.buildAutomaton(active);

    var rawHits = [];
    var textChars = Array.from(text);

    // 1) 字面命中
    var lit = ac.search(textChars);
    for (var i = 0; i < lit.length; i++) {
      var item = lit[i];
      for (var q = 0; q < item.payload.rules.length; q++) {
        var rule = item.payload.rules[q];
        rawHits.push(makeHit(item.start, item.end, item.payload.kw, rule,
          'keyword', this.severityOf(rule, opts.accountType),
          defaultAllowReplace(rule), null));
      }
    }

    // 正则兜底通道
    for (var ri = 0; ri < active.length; ri++) {
      var rr = active[ri];
      if (rr.m !== 'regex') continue;
      var re;
      try { re = new RegExp(rr.k, 'g'); } catch (e) { continue; }
      var m;
      while ((m = re.exec(text)) !== null) {
        var s = m.index, e = m.index + m[0].length;
        rawHits.push(makeHit(s, e, rr.k, rr, 'regex',
          this.severityOf(rr, opts.accountType), true, null));
        if (m[0].length === 0) re.lastIndex++;
      }
    }

    // 2) 变体命中（归一化后匹配，再回映射到原文）
    var variantHits = [];
    if (opts.useVariants) {
      var norm = normalize(text, this);
      var normChars = norm.chars;
      var vh = ac.search(normChars);
      for (var vi = 0; vi < vh.length; vi++) {
        var v = vh[vi];
        var oS = norm.indexMap[v.start];
        var oE = norm.indexMap[v.end - 1] + 1;
        var origSub = textChars.slice(oS, oE).join('');
        if (origSub === v.payload.kw) continue;   // 字面已命中，属重复
        for (var vr = 0; vr < v.payload.rules.length; vr++) {
          var vrule = v.payload.rules[vr];
          // 变体**不降级严重度**：规避写法在平台侧只会更严重，绝不会更轻。
          // 不确定性用 confidence 表达（0.8），UI 据此标注"疑似规避写法"。
          // 见 guardian/engine.py::_mk_hit 的同一处说明。
          variantHits.push(makeHit(oS, oE, v.payload.kw, vrule, 'variant',
            this.severityOf(vrule, opts.accountType), false,
            { variantOf: vrule.k, confidence: 0.8 }));
        }
      }

      // 2a) 正则通道（归一化文本）
      //     与 Python 端 guardian/engine.py 的同一处逻辑严格对齐。
      //     正则只跑原文会漏掉"用花招写出的组合型违规"：１００％（全角）、
      //     全網最低價（繁体）、首 创（跳字）。回映射逻辑与变体通道一致。
      var normStr = norm.text;
      for (var rj = 0; rj < active.length; rj++) {
        var nrr = active[rj];
        if (nrr.m !== 'regex') continue;
        var nre;
        try { nre = new RegExp(nrr.k, 'g'); } catch (e2) { continue; }
        var nm;
        while ((nm = nre.exec(normStr)) !== null) {
          var ns = nm.index, ne = nm.index + nm[0].length;
          if (ne <= ns) { nre.lastIndex++; continue; }
          var oS2 = norm.indexMap[ns];
          var oE2 = norm.indexMap[ne - 1] + 1;
          if (oS2 === undefined || oE2 === undefined) continue;
          // 归一化片段 == 原文片段 → 原文通道已产出同一命中，跳过
          if (textChars.slice(oS2, oE2).join('') === nm[0]) continue;
          variantHits.push(makeHit(oS2, oE2, nrr.k, nrr, 'regex',
            this.severityOf(nrr, opts.accountType), true, null));
        }
      }
    }

    // 3) 合并 + 去重
    var all = dedupe(rawHits.concat(variantHits));

    // 4) 规则级上下文豁免（context_excludes）
    all = this.applyRuleExcludes(all, textChars);

    // 5) 全局豁免 + 短词降级
    all = this.applyGuard(all, textChars);

    // 6) 转 finding
    var findings = all.map(function (h, idx) {
      return {
        id: idx + 1,
        start: h.start,
        end: h.end,
        matchedText: textChars.slice(h.start, h.end).join(''),
        keyword: h.keyword,
        ruleId: h.ruleId,
        category: h.category,
        severity: h.severity,
        source: h.source,
        industry: h.industry,
        platform: h.platform,
        suggestion: h.suggestion,
        replacements: h.replacements,
        allowAutoReplace: h.allowAutoReplace,
        matchType: h.matchType,
        variantOf: h.variantOf,
        confidence: h.confidence,
        context: excerpt(textChars, h.start, h.end),
      };
    });

    // 7) 汇总
    var counts = { critical: 0, high: 0, medium: 0, low: 0 };
    var penalty = 0;
    findings.forEach(function (f) {
      counts[f.severity] = (counts[f.severity] || 0) + 1;
      penalty += SEV_WEIGHT[f.severity] || 0;
    });
    var risk = '基本合规';
    if (counts.critical > 0) risk = '高风险';
    else if (counts.high > 0) risk = '中风险';
    else if (counts.medium > 0) risk = '低风险';

    var t1 = (global.performance || Date).now();

    return {
      text: text,
      findings: findings,
      summary: {
        score: Math.max(0, 100 - penalty),
        riskLevel: risk,
        counts: counts,
        textLength: text.length,
      },
      safeText: opts.autoReplace ? this.buildSafeText(text, textChars, findings, active) : text,
      meta: {
        elapsedMs: Math.round((t1 - t0) * 100) / 100,
        ruleCount: active.length,
        ruleTotal: this.data.rules.length,
      },
    };
  };

  /** 规则级豁免：命中落在该规则自己的 contextExcludes 词组内 → 丢弃。 */
  GuardianEngine.prototype.applyRuleExcludes = function (hits, textChars) {
    var cache = new Map();
    var kept = [];
    for (var i = 0; i < hits.length; i++) {
      var h = hits[i];
      var ex = h.contextExcludes;
      if (!ex || !ex.length) { kept.push(h); continue; }
      var spans = cache.get(h.ruleId);
      if (spans === undefined) {
        spans = [];
        for (var p = 0; p < ex.length; p++) {
          var phrase = Array.from(ex[p]);
          if (!phrase.length) continue;
          for (var s = 0; s + phrase.length <= textChars.length; s++) {
            var ok = true;
            for (var c = 0; c < phrase.length; c++) {
              if (textChars[s + c] !== phrase[c]) { ok = false; break; }
            }
            if (ok) spans.push([s, s + phrase.length]);
          }
        }
        cache.set(h.ruleId, spans);
      }
      var hit = false;
      for (var k = 0; k < spans.length; k++) {
        if (h.start >= spans[k][0] && h.end <= spans[k][1]) { hit = true; break; }
      }
      if (!hit) kept.push(h);
    }
    return kept;
  };

  /** 全局豁免词组 + 短词降级。 */
  GuardianEngine.prototype.applyGuard = function (hits, textChars) {
    var self = this;
    var spans = [];
    this.exemptPhrases.forEach(function (phrase) {
      var p = Array.from(phrase);
      if (!p.length) return;
      for (var s = 0; s + p.length <= textChars.length; s++) {
        var ok = true;
        for (var c = 0; c < p.length; c++) {
          if (textChars[s + c] !== p[c]) { ok = false; break; }
        }
        if (ok) spans.push([s, s + p.length]);
      }
    });
    spans.sort(function (a, b) { return a[0] - b[0]; });

    var kept = [];
    for (var i = 0; i < hits.length; i++) {
      var h = hits[i];
      var exempt = false;
      for (var j = 0; j < spans.length; j++) {
        if (spans[j][0] > h.start) break;
        if (h.start >= spans[j][0] && h.end <= spans[j][1]) { exempt = true; break; }
      }
      if (exempt) continue;

      var kwChars = Array.from(h.keyword);
      if (kwChars.length <= self.shortMaxLen && self.downgradeCats.has(h.category)) {
        h.severity = 'low';
        h.allowAutoReplace = false;
      }
      kept.push(h);
    }
    return kept;
  };

  /** 仅显式开启时改写；只有结构化替换词的命中才动。 */
  GuardianEngine.prototype.buildSafeText = function (text, textChars, findings, active) {
    var edits = [];
    var self = this;
    findings.forEach(function (f) {
      if (!f.allowAutoReplace) return;
      if (f.matchType !== 'keyword' && f.matchType !== 'regex') return;
      if (!f.replacements || !f.replacements.length) return;
      edits.push(f);
    });
    if (!edits.length) return text;
    edits.sort(function (a, b) { return b.start - a.start; });
    var chars = textChars.slice();
    edits.forEach(function (f) {
      var repl = Array.from(f.replacements[0]);
      chars.splice.apply(chars, [f.start, f.end - f.start].concat(repl));
    });
    return chars.join('');
  };

  function excerpt(chars, start, end, radius) {
    radius = radius || 10;
    var lo = Math.max(0, start - radius);
    var hi = Math.min(chars.length, end + radius);
    return (lo > 0 ? '…' : '') + chars.slice(lo, hi).join('') + (hi < chars.length ? '…' : '');
  }

  // ============================================================ AI 改写指令
  //
  // 与 Python 端 guardian/llm/prompts.py 是同一份提示词契约的两端实现。
  // 改这里必须同步改那边——否则桌面端和 Web 端给模型的指令会不一致，
  // 而"两边行为一致"正是本项目敢说纯前端等价实现的底气。
  //
  // 设计要点：这份提示词不是"让 AI 找违规"——违规已由上面的规则引擎
  // 精确找出并列在清单里。它的核心作用是**禁止模型做判定**，只让它改写。
  // 把判定交给模型会引入不确定性（漏检、幻觉、同问两答），这是本项目
  // 明确不要的。

  var PLATFORM_NAMES = {
    xiaohongshu: '小红书', douyin: '抖音', weixin: '微信', all: '多平台通用',
  };

  function formatFindingsForPrompt(findings, limit) {
    limit = limit || 40;
    if (!findings || !findings.length) return '（规则引擎未命中任何违规项）';
    var lines = [];
    findings.slice(0, limit).forEach(function (f, i) {
      var matched = f.matchedText || f.matched_text || f.keyword || '';
      var detail = [];
      if (f.keyword && f.keyword !== matched) detail.push('词条：' + f.keyword);
      if (f.category) detail.push('类别：' + f.category);
      if (f.severity) detail.push('等级：' + f.severity);
      if (f.source) detail.push('来源：' + f.source);
      if (f.matchType === 'variant') detail.push('疑似规避写法（谐音/跳字/全角/繁体）');
      if (f.suggestion) detail.push('规则建议：' + f.suggestion);
      if (f.replacements && f.replacements.length) {
        detail.push('可用替换词：' + f.replacements.join(' / '));
      }
      lines.push((i + 1) + '. 命中「' + matched + '」' +
        (detail.length ? '（' + detail.join('；') + '）' : ''));
    });
    if (findings.length > limit) {
      lines.push('……（另有 ' + (findings.length - limit) + ' 处未列出）');
    }
    return lines.join('\n');
  }

  var REWRITE_TASK = [
    '你是中文商业文案的合规改写专家。你的职责是改写，不是判定。',
    '',
    '## 你的唯一任务',
    '',
    '把下面这段文案**改写**到合规。**不要做合规判定**——违规点已由规则引擎',
    '精确找出并列在下方，你只需要按清单逐处改写。',
    '',
    '## 为什么判定不交给你',
    '',
    '规则引擎的判定确定、可复现、每条都能追溯到法条；模型做判定会漏检、会',
    '凭空发明违规、同一句话问两次给两个答案。所以：',
    '',
    '* **不要**新增清单以外的"我觉着也违规"的判断',
    '* **不要**删除清单以外的任何内容',
    '* **不要**在输出里讨论这段文案合不合规，只给改写结果',
    '',
    '## 改写铁律',
    '',
    '1. **最小改动**：只动清单命中的片段及其必要上下文，其余原文一字不改（含换行、标点、emoji）',
    '2. **保住卖点**：原文想传达的信息（项目优势、服务内容、目标客户）必须留住，只是换个说法',
    '3. **不编事实**：不得新增原文没有的数字、资质、年限、成功率、客户数量、结论',
    '4. **不弱化到废话**：把"保签"改成"提供签证材料协助"可以，改成"我们做移民的"不行——',
    '   改写后仍要是一句能用的商业文案，否则这次改写没有意义',
    '5. **程序化表述**：结果承诺（保过/包成功）改为过程性表述（协助准备、评估可行路径、',
    '   按流程递交）；医疗健康类改为"通常""因人而异"或直接删除效果承诺',
    '6. **导流话术**：平台禁止的导流说法（加微信/私信我）改为平台内的合规动作',
    '   （点击主页咨询、评论区留言、联系官方渠道）',
    '',
    '## 拿不准的时候',
    '',
    '如果某处无法在不失真的前提下改写（例如改了就构成虚假宣传、或必须补充真实',
    '资质才能说清），把它如实写进 `unresolved`，说明**为什么改不了**和**需要补充',
    '什么信息**。**不要硬凑一个假方案**——一个诚实的"这句需要人工确认"比一个',
    '编出来的合规说法有用得多。',
    '',
    '## 输出格式',
    '',
    '只输出如下 JSON，不要 markdown 代码块，不要任何额外文字：',
    '',
    '{"rewritten": "改写后的完整文案（含未改动部分）",',
    ' "changes": [{"before": "原文片段", "after": "改后片段", "reason": "为什么这么改", "rule": "对应清单第几条"}],',
    ' "kept": ["保留下来的核心卖点，逐条列出"],',
    ' "unresolved": [{"text": "无法处理的原句", "why": "为什么改不了", "need": "需要补充什么信息"}]}',
  ].join('\n');

  /**
   * 拼出「AI 改写指令」文本 —— 用户一键复制，粘到任意 AI 里用。
   *
   * 这是零配置路径：不需要在本页填任何 API Key、不需要联网、不需要后端，
   * 照样能得到改写结果。规则引擎的精确命中随指令一起带走，所以外部 AI
   * 拿到的信息量和桌面端直连模型时完全一样。
   */
  function buildRewritePrompt(text, findings, opts) {
    opts = opts || {};
    var ctx = ['目标平台：' + (PLATFORM_NAMES[opts.platform] || '多平台通用')];
    if (opts.accountType) {
      ctx.push('账号类型：' + (opts.accountType === 'blue_v' ? '蓝V 认证账号' : '普通账号'));
    }
    if (opts.industryLabel) ctx.push('行业词库：' + opts.industryLabel);

    var keepBlock = '';
    if (opts.mustKeep && opts.mustKeep.length) {
      keepBlock = '\n## 必须保留的信息（用户指定，改写时不得丢失）\n' +
        opts.mustKeep.map(function (k) { return '- ' + k; }).join('\n') + '\n';
    }

    return REWRITE_TASK +
      '\n## 本次上下文\n' + ctx.join('\n') + '\n' +
      keepBlock +
      '\n## 规则引擎命中的违规清单（共 ' + findings.length + ' 处）\n' +
      formatFindingsForPrompt(findings) +
      '\n\n## 待改写原文\n<<<\n' + text + '\n>>>\n';
  }

  // ============================================================ 导出

  GuardianEngine.buildRewritePrompt = buildRewritePrompt;
  GuardianEngine.formatFindingsForPrompt = formatFindingsForPrompt;

  GuardianEngine.SEV_ORDER = SEV_ORDER;
  GuardianEngine.SEV_LABELS = {
    critical: '高危', high: '中危', medium: '低危', low: '提示',
  };
  global.GuardianEngine = GuardianEngine;
})(typeof window !== 'undefined' ? window : globalThis);
