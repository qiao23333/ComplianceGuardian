#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合规检测引擎 — 核心（v2.0 升级版）

升级内容：
1. 正则模式匹配系统 — 覆盖"最X""极X""第X"等词根组合，不再穷举
2. Ollama LLM 语义增强 — 调用本地大模型检测语义违规
3. 性能优化 — 预计算行偏移表，O(1)索引转换
"""
import json
import re
import shutil
import threading
import subprocess
import time
from datetime import datetime
from pathlib import Path

try:
    import ahocorasick
    AHO_AVAILABLE = True
except ImportError:
    AHO_AVAILABLE = False

from guardian.context_guard import apply_guard, should_auto_replace


class ComplianceDetector:
    """多平台内容合规检测器（v2.1）

    采用单例模式，避免多个 UI 页面各自加载一份词库造成内存浪费。
    使用 get_instance() 获取全局唯一实例。
    """

    _instance = None
    _instance_lock = None  # 延迟导入 threading

    PLATFORM_NAMES = {
        "xiaohongshu": "小红书",
        "douyin": "抖音",
        "weixin": "微信视频号",
    }

    @classmethod
    def get_instance(cls, rules_dir=None):
        """获取单例实例（线程安全）"""
        if cls._instance is not None:
            return cls._instance
        if cls._instance_lock is None:
            import threading
            cls._instance_lock = threading.Lock()
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(rules_dir=rules_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例（测试用）"""
        cls._instance = None

    # 正则模式匹配 — 捕获关键词无法覆盖的组合
    REGEX_PATTERNS = [
        # "最X" — 捕获所有含"最"的极限词（排除标点和空白）
        {
            "pattern": r"最[^\W\s，。！？、；：（）【】\[\]{}.,!?;:]",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除'最'字或改为程度较弱的表述",
            "note": "正则捕获：含'最'字的极限用语",
            "source": "广告法",
        },
        # "极X" — 捕获所有含"极"的极限词
        {
            "pattern": r"极[^\W\s，。！？、；：（）【】\[\]{}.,!?;:]",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除'极'字或改为'非常'",
            "note": "正则捕获：含'极'字的极限用语",
            "source": "广告法",
        },
        # "第X" — 排名类
        {
            "pattern": r"第[一二三四五六七八九十\d]+",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除排名类表述",
            "note": "正则捕获：第X排名类极限用语",
            "source": "广告法",
        },
        # "国家级/世界级/宇宙级" 等
        {
            "pattern": r"[国家世界宇宙天地全球全行]级",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除'X级'表述",
            "note": "正则捕获：X级极限用语",
            "source": "广告法",
        },
        # "全网/全国/全球 + 最低/最便宜/首发/第一"
        {
            "pattern": r"(全网|全国|全球|全行|史上)(最低|最便宜|最优惠|首发|第一|首款|首创|最早|最强|最好|最大)",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除极限排名表述",
            "note": "正则捕获：全网/全国/全球+极限词组合",
            "source": "广告法",
        },
        # "首X" 系列
        {
            "pattern": r"首[创发家款次个批]",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除'首X'表述",
            "note": "正则捕获：首X类极限用语",
            "source": "广告法",
        },
        # "独X" 系列
        {
            "pattern": r"独[家创有特无]",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除'独X'表述或改为'特色'",
            "note": "正则捕获：独X类极限用语",
            "source": "广告法",
        },
        # "唯X" 系列
        {
            "pattern": r"唯[一独家]",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除'唯X'表述或改为'少有'",
            "note": "正则捕获：唯X类极限用语",
            "source": "广告法",
        },
        # "顶X" 系列
        {
            "pattern": r"顶[级尖配流端]",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除'顶X'表述或改为'高端'",
            "note": "正则捕获：顶X类极限用语",
            "source": "广告法",
        },
        # 数字+第一 / 第X（数字）
        {
            "pattern": r"\d+第一|第\d+",
            "category": "极限词",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "删除排名类表述",
            "note": "正则捕获：数字+第一或第X排名类",
            "source": "广告法",
        },
        # 100%效果类
        {
            "pattern": r"100%|百分之百|百分百",
            "category": "绝对化用语",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "改为'高比例'或具体数据",
            "note": "正则捕获：100%类绝对化用语",
            "source": "广告法",
        },
        # 永远/永久类
        {
            "pattern": r"永[久远]",
            "category": "绝对化用语",
            "severity": "violation",
            "law_ref": "《广告法》第九条",
            "suggestion": "改为'长期'并标注具体期限",
            "note": "正则捕获：永远/永久类绝对化用语",
            "source": "广告法",
        },
    ]

    def __init__(self, rules_dir=None):
        if rules_dir is None:
            rules_dir = Path(__file__).parent.parent / "rules"
        self.rules_dir = Path(rules_dir)
        self.ad_law = []
        self.platform_rules = {}
        self.blue_v_only = []
        self.user_custom = []
        # 行业词库包：{pack_id: {meta: {...}, rules: [...]}}
        self.industry_packs = {}
        self.load_rules()
        self._compile_regex_patterns()
        if AHO_AVAILABLE:
            self._build_aho_automaton()

    def load_rules(self):
        """加载所有词库 JSON 文件 + 行业词库包"""
        ad_path = self.rules_dir / "ad_law.json"
        if ad_path.exists():
            with open(ad_path, "r", encoding="utf-8") as f:
                self.ad_law = json.load(f)

        plat_path = self.rules_dir / "platform_rules.json"
        if plat_path.exists():
            with open(plat_path, "r", encoding="utf-8") as f:
                self.platform_rules = json.load(f)

        bluev_path = self.rules_dir / "blue_v_only.json"
        if bluev_path.exists():
            with open(bluev_path, "r", encoding="utf-8") as f:
                self.blue_v_only = json.load(f)

        custom_path = self.rules_dir / "user_custom.json"
        if custom_path.exists():
            with open(custom_path, "r", encoding="utf-8") as f:
                self.user_custom = json.load(f)

        # 加载行业词库包
        self._load_industry_packs()

    def _load_industry_packs(self):
        """扫描 industry_packs/ 目录，加载所有行业词库包

        每个行业包目录包含：
        - pack.json: 元数据（名称、描述、版本等）
        - rules.json: 规则列表
        """
        packs_dir = self.rules_dir / "industry_packs"
        if not packs_dir.exists():
            return

        self.industry_packs = {}
        for pack_dir in packs_dir.iterdir():
            if not pack_dir.is_dir():
                continue
            pack_meta_path = pack_dir / "pack.json"
            pack_rules_path = pack_dir / "rules.json"
            if not pack_meta_path.exists() or not pack_rules_path.exists():
                continue
            try:
                with open(pack_meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                with open(pack_rules_path, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                pack_id = meta.get("id", pack_dir.name)
                self.industry_packs[pack_id] = {
                    "meta": meta,
                    "rules": rules,
                }
            except (json.JSONDecodeError, OSError):
                continue  # 跳过损坏的行业包

    def list_industry_packs(self):
        """列出所有可用的行业词库包及其元数据"""
        result = []
        for pack_id, pack_data in self.industry_packs.items():
            meta = pack_data["meta"]
            result.append({
                "id": pack_id,
                "name": meta.get("name", pack_id),
                "description": meta.get("description", ""),
                "version": meta.get("version", "1.0.0"),
                "rule_count": len(pack_data["rules"]),
                "industry": meta.get("industry", ""),
                "categories": meta.get("categories", []),
            })
        return result

    def _compile_regex_patterns(self):
        """预编译正则表达式（提升性能）"""
        self.compiled_patterns = []
        for p in self.REGEX_PATTERNS:
            try:
                self.compiled_patterns.append({
                    "regex": re.compile(p["pattern"]),
                    **{k: v for k, v in p.items() if k != "pattern"}
                })
            except re.error:
                pass  # 跳过无效正则

    def _build_aho_automaton(self):
        """构建 Aho-Corasick 自动机（单次扫描匹配所有关键词）

        注意：同一个关键词可能出现在多个词库中（如"加微信"在小红书/抖音/视频号都有），
        因此用 list 存储每个关键词对应的所有规则条目，避免后添加的覆盖先添加的。
        """
        if not AHO_AVAILABLE:
            return
        try:
            self.aho_automaton = ahocorasick.Automaton()
            # 先用字典收集每个关键词对应的所有规则条目（list）
            keyword_map = {}

            def _add_keyword(keyword, entry):
                if not keyword:
                    return
                if keyword not in keyword_map:
                    keyword_map[keyword] = []
                keyword_map[keyword].append(entry)

            # 广告法
            for rule in self.ad_law:
                _add_keyword(rule.get("keyword", ""), rule)
            # 平台规则
            for plat, rules in self.platform_rules.items():
                for rule in rules:
                    _add_keyword(rule.get("keyword", ""), ("platform", plat, rule))
            # 蓝V限制
            for rule in self.blue_v_only:
                _add_keyword(rule.get("keyword", ""), ("blue_v", rule))
            # 用户自定义
            for rule in self.user_custom:
                _add_keyword(rule.get("keyword", ""), ("custom", rule))
            # 行业词库包
            for pack_id, pack_data in self.industry_packs.items():
                for rule in pack_data["rules"]:
                    _add_keyword(rule.get("keyword", ""), ("industry", pack_id, rule))

            # 批量加入 AC 自动机
            for keyword, entries in keyword_map.items():
                self.aho_automaton.add_word(keyword, entries)
            self.aho_automaton.make_automaton()
        except Exception:
            self.aho_automaton = None

    def reload_rules(self):
        """重新加载词库"""
        self.load_rules()
        self._compile_regex_patterns()
        if AHO_AVAILABLE:
            self._build_aho_automaton()

    def detect(self, text, platform, account_type):
        """
        执行合规检测（关键词 + 正则模式匹配）

        Args:
            text: 待检测文案
            platform: 平台 (xiaohongshu / douyin / weixin / all)
            account_type: 账号类型 (blue_v / non_blue_v)

        Returns:
            dict: 检测结果
        """
        if not text.strip():
            return {"violations": [], "summary": self._empty_summary(), "modified_text": "", "llm_analysis": None}

        violations = []
        match_id = 0
        matched_spans = set()  # 已匹配的区间，用于去重

        # 1. 关键词检测 — Aho-Corasick 自动机匹配（涵盖所有词库）
        if AHO_AVAILABLE and hasattr(self, 'aho_automaton') and self.aho_automaton:
            for end_idx, entries in self.aho_automaton.iter(text):
                # 每个关键词可能对应多条规则（不同词库/不同平台）
                for rule_data in entries:
                    if isinstance(rule_data, dict):
                        # 广告法词库
                        rule = rule_data
                        keyword = rule.get("keyword", "")
                        start_idx = end_idx - len(keyword) + 1
                        match_id += 1
                        v = {
                            "id": match_id,
                            "start": start_idx,
                            "end": start_idx + len(keyword),
                            "keyword": keyword,
                            "original": text[start_idx:start_idx + len(keyword)],
                            "category": rule.get("category", ""),
                            "severity": rule.get("severity", "violation"),
                            "source": "广告法",
                            "platform": "通用",
                            "blue_v_label": "",
                            "suggestion": rule.get("suggestion", ""),
                            "law_ref": rule.get("law_ref", ""),
                            "note": rule.get("note", ""),
                            "match_type": "keyword",
                        }
                        violations.append(v)
                        matched_spans.add((start_idx, start_idx + len(keyword)))
                    elif isinstance(rule_data, tuple):
                        # 平台规则 / 蓝V限制 / 用户自定义
                        tag = rule_data[0]
                        if tag == "platform":
                            plat, rule = rule_data[1], rule_data[2]
                            keyword = rule.get("keyword", "")
                            start_idx = end_idx - len(keyword) + 1
                            plat_name = self.PLATFORM_NAMES.get(plat, plat)
                            # 仅匹配与当前检测平台相关的规则
                            if platform == "all" or platform == plat:
                                match_id += 1
                                v = {
                                    "id": match_id,
                                    "start": start_idx,
                                    "end": start_idx + len(keyword),
                                    "keyword": keyword,
                                    "original": text[start_idx:start_idx + len(keyword)],
                                    "category": rule.get("category", ""),
                                    "severity": rule.get("severity", "warning"),
                                    "source": f"{plat_name}规则",
                                    "platform": plat_name if platform != "all" else "多平台",
                                    "blue_v_label": "",
                                    "suggestion": rule.get("suggestion", ""),
                                    "law_ref": "",
                                    "note": rule.get("note", ""),
                                    "match_type": "keyword",
                                }
                                violations.append(v)
                                matched_spans.add((start_idx, start_idx + len(keyword)))
                        elif tag == "blue_v":
                            rule = rule_data[1]
                            keyword = rule.get("keyword", "")
                            start_idx = end_idx - len(keyword) + 1
                            match_id += 1
                            if account_type == "non_blue_v":
                                severity = rule.get("non_blue_v", "violation")
                                blue_v_label = "非蓝V·违规"
                            else:
                                severity = rule.get("blue_v", "warning")
                                blue_v_label = "蓝V·警告"
                            v = {
                                "id": match_id,
                                "start": start_idx,
                                "end": start_idx + len(keyword),
                                "keyword": keyword,
                                "original": text[start_idx:start_idx + len(keyword)],
                                "category": rule.get("category", ""),
                                "severity": severity,
                                "source": "蓝V限制",
                                "platform": "通用",
                                "blue_v_label": blue_v_label,
                                "suggestion": rule.get("suggestion", ""),
                                "law_ref": "",
                                "note": rule.get("note", ""),
                                "match_type": "keyword",
                            }
                            violations.append(v)
                            matched_spans.add((start_idx, start_idx + len(keyword)))
                        elif tag == "custom":
                            rule = rule_data[1]
                            keyword = rule.get("keyword", "")
                            start_idx = end_idx - len(keyword) + 1
                            match_id += 1
                            v = {
                                "id": match_id,
                                "start": start_idx,
                                "end": start_idx + len(keyword),
                                "keyword": keyword,
                                "original": text[start_idx:start_idx + len(keyword)],
                                "category": rule.get("category", "行业红线"),
                                "severity": rule.get("severity", "violation"),
                                "source": "行业红线",
                                "platform": "通用",
                                "blue_v_label": "",
                                "suggestion": rule.get("suggestion", "根据公司规定修改"),
                                "law_ref": "",
                                "note": rule.get("note", ""),
                                "match_type": "keyword",
                            }
                            violations.append(v)
                            matched_spans.add((start_idx, start_idx + len(keyword)))
                        elif tag == "industry":
                            pack_id, rule = rule_data[1], rule_data[2]
                            keyword = rule.get("keyword", "")
                            start_idx = end_idx - len(keyword) + 1
                            pack_name = self.industry_packs.get(pack_id, {}).get("meta", {}).get("name", pack_id)
                            match_id += 1
                            v = {
                                "id": match_id,
                                "start": start_idx,
                                "end": start_idx + len(keyword),
                                "keyword": keyword,
                                "original": text[start_idx:start_idx + len(keyword)],
                                "category": rule.get("category", "行业合规"),
                                "severity": rule.get("severity", "violation"),
                                "source": f"{pack_name}",
                                "platform": "通用",
                                "blue_v_label": "",
                                "suggestion": rule.get("suggestion", ""),
                                "law_ref": "",
                                "note": rule.get("note", ""),
                                "match_type": "keyword",
                                "pack_id": pack_id,
                            }
                            violations.append(v)
                            matched_spans.add((start_idx, start_idx + len(keyword)))
        else:
            # 备用方案：逐关键词扫描
            for rule in self.ad_law:
                keyword = rule.get("keyword", "")
                if not keyword:
                    continue
                for pos in self._find_all(text, keyword):
                    match_id += 1
                    v = {
                        "id": match_id,
                        "start": pos,
                        "end": pos + len(keyword),
                        "keyword": keyword,
                        "original": text[pos:pos + len(keyword)],
                        "category": rule.get("category", ""),
                        "severity": rule.get("severity", "violation"),
                        "source": "广告法",
                        "platform": "通用",
                        "blue_v_label": "",
                        "suggestion": rule.get("suggestion", ""),
                        "law_ref": rule.get("law_ref", ""),
                        "note": rule.get("note", ""),
                        "match_type": "keyword",
                    }
                    violations.append(v)
                    matched_spans.add((pos, pos + len(keyword)))

        # 1b. 正则模式匹配 — 补充关键词无法覆盖的组合（使用预编译正则）
        for pattern_rule in self.compiled_patterns:
            regex = pattern_rule["regex"]
            for m in regex.finditer(text):
                pos = m.start()
                end = m.end()
                matched_text = m.group()

                # 跳过已被精确关键词匹配的区间
                already_matched = False
                for (s, e) in matched_spans:
                    if pos >= s and end <= e:
                        already_matched = True
                        break
                    if pos < e and end > s:
                        already_matched = True
                        break

                if already_matched:
                    continue

                match_id += 1
                v = {
                    "id": match_id,
                    "start": pos,
                    "end": end,
                    "keyword": matched_text,
                    "original": matched_text,
                    "category": pattern_rule.get("category", "极限词"),
                    "severity": pattern_rule.get("severity", "violation"),
                    "source": pattern_rule.get("source", "广告法"),
                    "platform": "通用",
                    "blue_v_label": "",
                    "suggestion": pattern_rule.get("suggestion", "修改极限用语"),
                    "law_ref": pattern_rule.get("law_ref", "《广告法》第九条"),
                    "note": pattern_rule.get("note", ""),
                    "match_type": "regex",
                }
                violations.append(v)
                matched_spans.add((pos, end))

        # 判断AC自动机是否可用（可用时跳过sections 2-4的冗余扫描）
        aho_active = AHO_AVAILABLE and hasattr(self, 'aho_automaton') and self.aho_automaton

        # 2. 平台规则检测（AC不可用时走备用扫描）
        if not aho_active:
            platforms_to_check = []
            if platform == "all":
                platforms_to_check = list(self.platform_rules.keys())
            elif platform in self.platform_rules:
                platforms_to_check = [platform]

            for plat in platforms_to_check:
                plat_name = self.PLATFORM_NAMES.get(plat, plat)
                for rule in self.platform_rules.get(plat, []):
                    keyword = rule.get("keyword", "")
                    if not keyword:
                        continue
                    for pos in self._find_all(text, keyword):
                        match_id += 1
                        severity = rule.get("severity", "warning")
                        v = {
                            "id": match_id,
                            "start": pos,
                            "end": pos + len(keyword),
                            "keyword": keyword,
                            "original": text[pos:pos + len(keyword)],
                            "category": rule.get("category", ""),
                            "severity": severity,
                            "source": f"{plat_name}规则",
                            "platform": plat_name if platform != "all" else "多平台",
                            "blue_v_label": "",
                            "suggestion": rule.get("suggestion", ""),
                            "law_ref": "",
                            "note": rule.get("note", ""),
                            "match_type": "keyword",
                        }
                        violations.append(v)

        # 3. 蓝V专属限制检测（AC不可用时走备用扫描）
        if not aho_active:
            for rule in self.blue_v_only:
                keyword = rule.get("keyword", "")
                if not keyword:
                    continue
                for pos in self._find_all(text, keyword):
                    match_id += 1
                    if account_type == "non_blue_v":
                        severity = rule.get("non_blue_v", "violation")
                        blue_v_label = "非蓝V·违规"
                    else:
                        severity = rule.get("blue_v", "warning")
                        blue_v_label = "蓝V·警告"

                    v = {
                        "id": match_id,
                        "start": pos,
                        "end": pos + len(keyword),
                        "keyword": keyword,
                        "original": text[pos:pos + len(keyword)],
                        "category": rule.get("category", ""),
                        "severity": severity,
                        "source": "蓝V限制",
                        "platform": "通用",
                        "blue_v_label": blue_v_label,
                        "suggestion": rule.get("suggestion", ""),
                        "law_ref": "",
                        "note": rule.get("note", ""),
                        "match_type": "keyword",
                    }
                    violations.append(v)

        # 4. 用户自定义行业红线检测（AC不可用时走备用扫描）
        if not aho_active:
            for rule in self.user_custom:
                keyword = rule.get("keyword", "")
                if not keyword:
                    continue
                for pos in self._find_all(text, keyword):
                    match_id += 1
                    v = {
                        "id": match_id,
                        "start": pos,
                        "end": pos + len(keyword),
                        "keyword": keyword,
                        "original": text[pos:pos + len(keyword)],
                        "category": rule.get("category", "行业红线"),
                        "severity": rule.get("severity", "violation"),
                        "source": "行业红线",
                        "platform": "通用",
                        "blue_v_label": "",
                        "suggestion": rule.get("suggestion", "根据公司规定修改"),
                        "law_ref": "",
                        "note": rule.get("note", ""),
                        "match_type": "keyword",
                    }
                    violations.append(v)

        # 5. 行业词库包检测（AC不可用时走备用扫描）
        if not aho_active:
            for pack_id, pack_data in self.industry_packs.items():
                pack_name = pack_data.get("meta", {}).get("name", pack_id)
                for rule in pack_data.get("rules", []):
                    keyword = rule.get("keyword", "")
                    if not keyword:
                        continue
                    for pos in self._find_all(text, keyword):
                        match_id += 1
                        v = {
                            "id": match_id,
                            "start": pos,
                            "end": pos + len(keyword),
                            "keyword": keyword,
                            "original": text[pos:pos + len(keyword)],
                            "category": rule.get("category", "行业合规"),
                            "severity": rule.get("severity", "violation"),
                            "source": f"{pack_name}",
                            "platform": "通用",
                            "blue_v_label": "",
                            "suggestion": rule.get("suggestion", ""),
                            "law_ref": "",
                            "note": rule.get("note", ""),
                            "match_type": "keyword",
                            "pack_id": pack_id,
                        }
                        violations.append(v)

        # 按位置排序
        violations.sort(key=lambda x: x["start"])

        # 去重（同一位置同一关键词只保留最长的）
        violations = self._deduplicate(violations)

        # 反误杀守卫：上下文排除 + 短词降级 + 禁止自动改写
        # 解决"最近"被判违规、且被改写成"近"的 P0 问题
        violations = apply_guard(violations, text)

        # 重新编号
        for i, v in enumerate(violations):
            v["id"] = i + 1

        # 生成摘要
        summary = self._generate_summary(violations, len(text))

        # 生成修改后文案
        modified_text = self._generate_modified_text(text, violations)

        return {
            "violations": violations,
            "summary": summary,
            "modified_text": modified_text,
            "llm_analysis": None,
        }

    def detect_all_platforms(self, text, account_type):
        """跨平台对比检测：同一文案同时检测三个平台"""
        results = {}
        for plat_key in ["xiaohongshu", "douyin", "weixin"]:
            results[plat_key] = self.detect(text, plat_key, account_type)
        return results

    def detect_with_llm(self, text, platform, account_type, callback=None):
        """
        检测 + LLM语义增强（异步）

        先执行关键词+正则检测（同步返回），
        LLM分析在后台线程执行，完成后调用callback。

        Args:
            callback: function(llm_result_dict) — LLM分析完成后的回调
        """
        # 1. 先执行本地检测（同步）
        result = self.detect(text, platform, account_type)

        # 2. 后台启动 LLM 分析
        def llm_worker():
            llm_result = self._llm_analyze(text, platform, account_type, result)
            result["llm_analysis"] = llm_result
            if callback:
                callback(llm_result)

        thread = threading.Thread(target=llm_worker, daemon=True)
        thread.start()

        return result

    def _llm_analyze(self, text, platform, account_type, keyword_result):
        """调用 Ollama qwen2.5:7b 进行语义合规分析（subprocess方式）"""
        platform_name = self.PLATFORM_NAMES.get(platform, platform)
        account_label = "蓝V" if account_type == "blue_v" else "非蓝V"

        # 精简prompt — 减少token消耗，提高响应速度
        detected = ""
        if keyword_result.get("violations"):
            detected = "已检出：" + "、".join(v["keyword"] for v in keyword_result["violations"][:5])

        prompt = f"""你是广告合规审核专家。审核以下文案在{platform_name}（{account_label}账号）的合规性。
{f'注意：以下词已被检出 - {detected}' if detected else ''}

文案：{text}

请补充分析关键词可能遗漏的语义风险（如隐性违规、虚假宣传、平台风险）。
只返回JSON，不要markdown标记：
{{"risks":[{{"type":"类型","severity":"violation或warning","description":"问题","suggestion":"建议"}}],"assessment":"整体评估","score":85}}"""

        try:
            # 使用subprocess调用ollama run — 比HTTP API更可靠
            result = subprocess.run(
                ["ollama", "run", "qwen2.5:7b"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )

            llm_text = result.stdout.strip()

            # 清理 ANSI 终端转义序列（ollama run 会输出这些）
            ansi_escape = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
            llm_text = ansi_escape.sub('', llm_text)
            # 清理其他控制字符（保留换行和制表符）
            llm_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', llm_text)
            # 清理 markdown 代码块标记
            llm_text = llm_text.replace("```json", "").replace("```", "").strip()

            if not llm_text:
                return {
                    "status": "error",
                    "error": "LLM返回空结果",
                    "risks": [],
                    "overall_assessment": "AI分析返回空结果，请重试",
                    "compliance_score": None,
                    "model": "qwen2.5:7b",
                }

            # 清理可能的 markdown 标记
            llm_text = llm_text.replace("```json", "").replace("```", "").strip()

            # 尝试解析JSON
            import json as json_mod
            llm_result = None
            try:
                llm_result = json_mod.loads(llm_text)
            except json_mod.JSONDecodeError:
                # 替换字面换行为空格（LLM可能在JSON字符串值中输出字面换行）
                compact = llm_text.replace('\n', ' ').replace('\r', ' ')
                try:
                    llm_result = json_mod.loads(compact)
                except json_mod.JSONDecodeError:
                    # 尝试括号匹配提取
                    llm_result = self._extract_json(llm_text)

            if llm_result is None:
                # 无法解析JSON，返回原始文本作为评估
                return {
                    "status": "success",
                    "risks": [],
                    "overall_assessment": llm_text[:300],
                    "compliance_score": None,
                    "model": "qwen2.5:7b",
                }

            llm_result["model"] = "qwen2.5:7b"
            llm_result["status"] = "success"
            return llm_result

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "LLM分析超时（120秒）",
                "risks": [],
                "overall_assessment": "AI分析超时，模型可能正在加载中，请稍后重试",
                "compliance_score": None,
                "model": "qwen2.5:7b",
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "risks": [],
                "overall_assessment": f"LLM分析失败：{e}",
                "compliance_score": None,
                "model": "qwen2.5:7b",
            }

    @staticmethod
    def check_ollama_available():
        """检查 Ollama 是否可用"""
        try:
            import urllib.request
            import json as json_mod
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json_mod.loads(resp.read().decode("utf-8"))
                models = [m["name"] for m in data.get("models", [])]
                return True, models
        except Exception:
            return False, []

    @staticmethod
    def _extract_json(text):
        """从文本中提取JSON对象（支持嵌套大括号）"""
        import json as json_mod
        # 找到第一个 {
        start = text.find("{")
        if start == -1:
            return None
        # 用括号匹配找到完整的JSON
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json_mod.loads(text[start:i + 1])
                    except json_mod.JSONDecodeError:
                        return None
        return None

    def _find_all(self, text, keyword):
        """查找文本中所有匹配位置"""
        positions = []
        start = 0
        while True:
            pos = text.find(keyword, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + len(keyword)
        return positions

    def _deduplicate(self, violations):
        """去重：重叠的匹配只保留最长的"""
        if not violations:
            return []

        # 先按 start 排序，再按长度降序
        violations.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))

        result = []
        occupied = []  # 已占用的区间列表 [(start, end), ...]

        for v in violations:
            # 检查是否与已占用的区间重叠
            overlaps = False
            for (s, e) in occupied:
                if v["start"] < e and v["end"] > s:
                    overlaps = True
                    break

            if not overlaps:
                result.append(v)
                occupied.append((v["start"], v["end"]))

        # 按位置重新排序
        result.sort(key=lambda x: x["start"])
        return result

    def _empty_summary(self):
        return {
            "total": 0,
            "violations": 0,
            "warnings": 0,
            "score": 100,
            "risk_level": "低风险",
            "text_length": 0,
        }

    def _generate_summary(self, violations, text_length):
        """生成检测摘要"""
        violation_count = sum(1 for v in violations if v["severity"] == "violation")
        warning_count = sum(1 for v in violations if v["severity"] == "warning")
        total = len(violations)

        # 合规分数计算
        if text_length == 0:
            score = 100
        else:
            # 基础分100，每个违规扣10分，每个警告扣5分
            score = max(0, 100 - violation_count * 10 - warning_count * 5)

        # 风险等级
        if violation_count >= 5:
            risk_level = "极高风险"
        elif violation_count >= 3:
            risk_level = "高风险"
        elif violation_count >= 1:
            risk_level = "中风险"
        elif warning_count >= 3:
            risk_level = "低风险"
        else:
            risk_level = "安全"

        return {
            "total": total,
            "violations": violation_count,
            "warnings": warning_count,
            "score": score,
            "risk_level": risk_level,
            "text_length": text_length,
        }

    def _generate_modified_text(self, text, violations):
        """生成修改后文案（用建议替换违规词）"""
        # 从后往前替换，避免位置偏移
        sorted_v = sorted(violations, key=lambda x: x["start"], reverse=True)
        modified = text
        for v in sorted_v:
            # 安全网：短词与被标记为 allow_auto_replace=False 的项绝不自动改写，
            # 只允许给提示。这是防止"最近"→"近"这类原文被改坏事故的最后防线。
            if not should_auto_replace(v):
                continue
            suggestion = v.get("suggestion", "")
            keyword = v["keyword"]
            # 尝试提取建议中的替换词
            replacement = self._extract_replacement(suggestion, keyword)
            if replacement is not None:
                modified = modified[:v["start"]] + replacement + modified[v["end"]:]
        return modified

    def _extract_replacement(self, suggestion, keyword):
        """从建议中提取替换词"""
        # 尝试匹配 "改为'XXX'" 格式（引号包围的）
        match = re.search(r"改为['\"](.+?)['\"]", suggestion)
        if match:
            return match.group(1).strip()

        # 尝试匹配 "→ 'XXX'" 格式
        match = re.search(r"→\s*['\"](.+?)['\"]", suggestion)
        if match:
            return match.group(1).strip()

        # 如果建议包含"删除"且不包含"改为"，返回空字符串（删除关键词）
        if "删除" in suggestion and "改为" not in suggestion:
            return ""

        # 如果建议包含"删除或改为"，返回空字符串（保守处理，选择删除）
        if "删除" in suggestion and "改为" in suggestion:
            return ""

        # 默认：不做替换
        return None

    def get_rules_summary(self):
        """获取词库统计摘要"""
        plat_counts = {}
        for plat, rules in self.platform_rules.items():
            plat_name = self.PLATFORM_NAMES.get(plat, plat)
            plat_counts[plat_name] = len(rules)

        # 行业词库包统计
        industry_pack_counts = {}
        total_industry_rules = 0
        for pack_id, pack_data in self.industry_packs.items():
            pack_name = pack_data.get("meta", {}).get("name", pack_id)
            count = len(pack_data.get("rules", []))
            industry_pack_counts[pack_name] = count
            total_industry_rules += count

        total = (
            len(self.ad_law)
            + sum(len(r) for r in self.platform_rules.values())
            + len(self.blue_v_only)
            + len(self.user_custom)
            + total_industry_rules
        )

        return {
            "广告法违禁词": len(self.ad_law),
            "平台规则": plat_counts,
            "蓝V专属限制": len(self.blue_v_only),
            "行业红线(自定义)": len(self.user_custom),
            "行业词库包": industry_pack_counts,
            "正则模式": len(self.REGEX_PATTERNS),
            "总计": total,
        }

    def add_custom_rule(self, keyword, category, severity, suggestion, note=""):
        """添加自定义规则到 user_custom.json"""
        rule = {
            "keyword": keyword,
            "category": category or "行业红线",
            "severity": severity or "violation",
            "suggestion": suggestion or "根据公司规定修改",
            "note": note or "",
        }
        self.user_custom.append(rule)
        self._save_user_custom()
        return rule

    def add_rule_to_category(self, tab_name, keyword, category, severity, suggestion, note=""):
        """添加规则到指定分类词库（供词库管理页面分流保存）

        Args:
            tab_name: 词库标签页名（"广告法" / "蓝V限制" / "行业红线"）
        """
        rule = {
            "keyword": keyword,
            "category": category or "",
            "severity": severity or "violation",
            "suggestion": suggestion or "",
            "note": note or "",
        }
        if tab_name == "广告法":
            rule["source"] = "广告法"
            rule["law_ref"] = "《广告法》第九条"
            self.ad_law.append(rule)
            self._save_rules("广告法")
        elif tab_name == "蓝V限制":
            rule["blue_v"] = "warning"
            rule["non_blue_v"] = "violation"
            self.blue_v_only.append(rule)
            self._save_rules("蓝V限制")
        elif tab_name == "行业红线":
            rule["category"] = category or "行业红线"
            rule["suggestion"] = suggestion or "根据公司规定修改"
            self.user_custom.append(rule)
            self._save_user_custom()
        return rule

    def remove_custom_rule(self, index):
        """删除自定义规则"""
        if 0 <= index < len(self.user_custom):
            self.user_custom.pop(index)
            self._save_user_custom()

    def _save_user_custom(self):
        """保存用户自定义词库"""
        custom_path = self.rules_dir / "user_custom.json"
        with open(custom_path, "w", encoding="utf-8") as f:
            json.dump(self.user_custom, f, ensure_ascii=False, indent=2)

    def _save_rules(self, tab_name):
        """保存指定词库到JSON文件（供词库管理页面调用）

        Args:
            tab_name: 词库标签页名（"广告法" / "平台规则" / "蓝V限制" / "行业红线"）
        """
        if tab_name == "广告法":
            file_path = self.rules_dir / "ad_law.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.ad_law, f, ensure_ascii=False, indent=2)
        elif tab_name == "平台规则":
            file_path = self.rules_dir / "platform_rules.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.platform_rules, f, ensure_ascii=False, indent=2)
        elif tab_name == "蓝V限制":
            file_path = self.rules_dir / "blue_v_only.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.blue_v_only, f, ensure_ascii=False, indent=2)
        elif tab_name == "行业红线":
            self._save_user_custom()

    def backup_rules(self):
        """备份当前词库到 rules/backup/YYYY-MM-DD_HHMM/ 目录"""
        backup_dir = self.rules_dir / "backup" / datetime.now().strftime("%Y-%m-%d_%H%M")
        backup_dir.mkdir(parents=True, exist_ok=True)
        for filename in ["ad_law.json", "platform_rules.json", "blue_v_only.json", "user_custom.json"]:
            src = self.rules_dir / filename
            if src.exists():
                shutil.copy2(src, backup_dir / filename)
        # 备份行业词库包
        packs_dir = self.rules_dir / "industry_packs"
        if packs_dir.exists():
            backup_packs_dir = backup_dir / "industry_packs"
            shutil.copytree(packs_dir, backup_packs_dir, dirs_exist_ok=True)
        return str(backup_dir)

    def list_backups(self):
        """列出所有备份目录（按时间倒序）"""
        backup_root = self.rules_dir / "backup"
        if not backup_root.exists():
            return []
        backups = []
        for d in sorted(backup_root.iterdir(), reverse=True):
            if d.is_dir():
                file_count = sum(1 for f in d.iterdir() if f.is_file())
                backups.append({
                    "name": d.name,
                    "path": str(d),
                    "file_count": file_count,
                    "timestamp": d.name,
                })
        return backups

    def restore_backup(self, backup_name):
        """从指定备份恢复词库"""
        backup_dir = self.rules_dir / "backup" / backup_name
        if not backup_dir.exists():
            raise FileNotFoundError(f"备份不存在：{backup_name}")
        for filename in ["ad_law.json", "platform_rules.json", "blue_v_only.json", "user_custom.json"]:
            src = backup_dir / filename
            dst = self.rules_dir / filename
            if src.exists():
                shutil.copy2(src, dst)
        # 恢复行业词库包
        backup_packs_dir = backup_dir / "industry_packs"
        if backup_packs_dir.exists():
            packs_dir = self.rules_dir / "industry_packs"
            if packs_dir.exists():
                shutil.rmtree(packs_dir)
            shutil.copytree(backup_packs_dir, packs_dir)
        self.load_rules()
        self._compile_regex_patterns()
        if AHO_AVAILABLE:
            self._build_aho_automaton()

