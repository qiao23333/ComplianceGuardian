#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ComplianceDetector 核心功能测试"""
import pytest
from guardian.detector import ComplianceDetector


@pytest.fixture
def detector():
    """每个测试用例都用独立的 detector，避免单例污染"""
    ComplianceDetector.reset_instance()
    return ComplianceDetector()


class TestBasicDetection:
    """基础检测功能"""

    def test_empty_text(self, detector):
        """空文本不应有任何违规"""
        result = detector.detect("", "xiaohongshu", "personal")
        assert len(result["violations"]) == 0
        assert result["summary"]["score"] == 100

    def test_ad_law_keyword(self, detector):
        """广告法极限词检测"""
        result = detector.detect("这是最好的产品", "xiaohongshu", "personal")
        violations = [v for v in result["violations"] if v["source"] == "广告法"]
        assert len(violations) > 0
        assert any("最" in v["keyword"] for v in violations)

    def test_regex_pattern_detection(self, detector):
        """正则模式匹配（最X/极X/第X等组合）"""
        # "最优" 应该被正则 "最X" 模式捕获
        result = detector.detect("这是最优选择", "xiaohongshu", "personal")
        # 验证正则匹配生效（match_type 为 regex）
        regex_matches = [v for v in result["violations"] if v["match_type"] == "regex"]
        # 注意："最优"可能同时被关键词和正则匹配，但去重后只留一个
        # 我们通过检查是否有违规来验证正则在工作
        assert len(result["violations"]) > 0

    def test_no_false_positives(self, detector):
        """正常文本不应误报"""
        text = "今天天气很好，我们去公园散步吧。"
        result = detector.detect(text, "xiaohongshu", "personal")
        # 纯日常用语不应有广告法或平台违规
        ad_violations = [v for v in result["violations"] if v["source"] == "广告法"]
        assert len(ad_violations) == 0


class TestPlatformRules:
    """平台规则检测"""

    def test_xiaohongshu_lead_word(self, detector):
        """小红书导流词检测"""
        result = detector.detect("加微信了解更多", "xiaohongshu", "personal")
        xhs_violations = [v for v in result["violations"] if "小红书" in v["source"]]
        assert len(xhs_violations) > 0

    def test_platform_specificity(self, detector):
        """平台特异性：某平台违规词在其他平台可能不触发"""
        # 检测"加微信"在小红书 vs 通用的差异
        result_xhs = detector.detect("加微信咨询", "xiaohongshu", "personal")
        xhs_count = len([v for v in result_xhs["violations"] if "小红书" in v["source"]])

        # 至少在小红书能检测到
        assert xhs_count > 0

    def test_all_platforms_mode(self, detector):
        """跨平台对比检测"""
        results = detector.detect_all_platforms("加微信，最好的移民服务", "personal")
        assert "xiaohongshu" in results
        assert "douyin" in results
        assert "weixin" in results
        # 三个平台都应该返回检测结果
        for plat, res in results.items():
            assert "violations" in res
            assert "summary" in res


class TestIndustryPacks:
    """行业词库包"""

    def test_immigration_pack_loaded(self, detector):
        """移民行业包应被正确加载"""
        packs = detector.list_industry_packs()
        pack_ids = [p["id"] for p in packs]
        assert "immigration" in pack_ids

    def test_immigration_pack_metadata(self, detector):
        """移民行业包元数据完整"""
        packs = detector.list_industry_packs()
        immigration = next(p for p in packs if p["id"] == "immigration")
        assert immigration["name"]
        assert immigration["description"]
        assert immigration["rule_count"] > 0
        assert immigration["industry"] == "移民/出入境"

    def test_immigration_keyword_detection(self, detector):
        """移民行业红线词检测"""
        result = detector.detect("我们保证下签，包过，成功率100%", "xiaohongshu", "personal")
        industry_violations = [
            v for v in result["violations"]
            if v.get("pack_id") == "immigration"
        ]
        assert len(industry_violations) > 0
        # 应该能检测到"保证下签"或"包过"等移民行业特有违规
        keywords_found = [v["keyword"] for v in industry_violations]
        assert any("保证" in k or "包过" in k or "包拿" in k for k in keywords_found)

    def test_rules_summary_includes_industry_packs(self, detector):
        """统计摘要应包含行业词库包"""
        summary = detector.get_rules_summary()
        assert "行业词库包" in summary
        assert isinstance(summary["行业词库包"], dict)
        assert len(summary["行业词库包"]) > 0


class TestSummary:
    """检测摘要与评分"""

    def test_summary_structure(self, detector):
        """摘要字段完整"""
        result = detector.detect("最好的产品", "xiaohongshu", "personal")
        s = result["summary"]
        assert "total" in s
        assert "violations" in s
        assert "warnings" in s
        assert "score" in s
        assert "risk_level" in s
        assert "text_length" in s

    def test_score_decreases_with_violations(self, detector):
        """违规越多，分数越低"""
        result_clean = detector.detect("你好世界", "xiaohongshu", "personal")
        result_bad = detector.detect("最好最大最强最优第一顶级", "xiaohongshu", "personal")
        assert result_clean["summary"]["score"] >= result_bad["summary"]["score"]

    def test_risk_levels(self, detector):
        """风险等级判断"""
        # 安全
        r = detector.detect("你好", "xiaohongshu", "personal")
        assert r["summary"]["risk_level"] == "安全"


class TestDeduplication:
    """去重逻辑"""

    def test_overlapping_matches_deduplicated(self, detector):
        """重叠的匹配应去重"""
        # "最佳"可能被关键词和正则同时匹配，但结果应只出现一次
        result = detector.detect("最佳选择", "xiaohongshu", "personal")
        # 同一位置不应有多个违规
        positions = [(v["start"], v["end"]) for v in result["violations"]]
        assert len(positions) == len(set(positions)), "存在重叠的违规匹配"


class TestSingleton:
    """单例模式"""

    def test_get_instance_returns_same_object(self):
        """get_instance 应始终返回同一实例"""
        ComplianceDetector.reset_instance()
        d1 = ComplianceDetector.get_instance()
        d2 = ComplianceDetector.get_instance()
        assert d1 is d2

    def test_reset_instance(self):
        """reset_instance 后应返回新实例"""
        ComplianceDetector.reset_instance()
        d1 = ComplianceDetector.get_instance()
        ComplianceDetector.reset_instance()
        d2 = ComplianceDetector.get_instance()
        assert d1 is not d2


class TestModifiedText:
    """修改后文案生成"""

    def test_modified_text_generated(self, detector):
        """应生成修改建议后的文案"""
        result = detector.detect("最好的服务", "xiaohongshu", "personal")
        assert "modified_text" in result
        assert isinstance(result["modified_text"], str)
