import json
import subprocess
import sys
from pathlib import Path

from evaluation.dataset_builder import (
    build_testset,
    load_recipe_catalog,
    summarize_testset_coverage,
)
from evaluation.run_evaluation import _default_data_root
from evaluation.run_evaluation import summarize_diagnostic_trends
from evaluation.scoring import score_rule_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT.parents[1] / "data" / "C8"


def test_load_recipe_catalog_extracts_real_recipe_metadata():
    catalog = load_recipe_catalog(DATA_ROOT)

    assert len(catalog) >= 300
    assert any(item["dish_name"] == "鸡蛋三明治" for item in catalog)
    assert any(item["category"] == "早餐" for item in catalog)
    assert any(item["category"] == "荤菜" for item in catalog)
    assert all("sections" in item for item in catalog)


def test_build_testset_hits_target_scale_and_case_mix():
    catalog = load_recipe_catalog(DATA_ROOT)
    testset = build_testset(catalog)
    coverage = summarize_testset_coverage(testset)

    assert testset["schema_version"] == "1.0"
    assert 100 <= len(testset["cases"]) <= 150
    assert coverage["single_turn_cases"] >= 70
    assert coverage["multi_turn_cases"] >= 10
    assert coverage["irrelevant_cases"] >= 8
    assert coverage["temporal_unknown_cases"] >= 6
    assert coverage["ambiguous_cases"] >= 10
    assert coverage["categories_covered"] >= 6


def test_testset_cases_have_required_fields_and_turns():
    catalog = load_recipe_catalog(DATA_ROOT)
    testset = build_testset(catalog)

    for case in testset["cases"]:
        assert case["case_id"]
        assert case["scenario_type"]
        assert case["evaluation_mode"] in {"strict", "fallback", "boundary"}
        assert case["turns"]
        for turn in case["turns"]:
            assert turn["user"]
            assert "expectation" in turn


def test_rule_scoring_rewards_correct_grounded_detail_answer():
    result = score_rule_metrics(
        answer="鸡蛋三明治需要鸡蛋、吐司、培根、黄油、蛋黄酱、盐和黑胡椒。",
        expectation={
            "expected_dish": "鸡蛋三明治",
            "required_terms": ["鸡蛋", "吐司", "培根"],
            "forbidden_terms": ["红烧鲤鱼"],
            "response_policy": "grounded_answer",
        },
    )

    assert result["passed"] is True
    assert result["score"] >= 0.9
    assert result["checks"]["dish_match"] is True
    assert result["checks"]["required_terms"] is True


def test_rule_scoring_accepts_polite_fallback_for_unknown_or_irrelevant_questions():
    result = score_rule_metrics(
        answer="我不知道你昨天吃了什么。如果你愿意，我可以根据你现在想吃的口味给你推荐几道菜。",
        expectation={
            "response_policy": "polite_fallback",
            "required_terms_any": ["不知道", "可以", "推荐"],
            "forbidden_terms": ["鸡蛋三明治", "红烧鲤鱼"],
        },
    )

    assert result["passed"] is True
    assert result["score"] >= 0.8
    assert result["checks"]["policy_match"] is True


def test_built_testset_can_be_serialized_to_json():
    catalog = load_recipe_catalog(DATA_ROOT)
    testset = build_testset(catalog)
    serialized = json.dumps(testset, ensure_ascii=False)

    assert '"cases"' in serialized


def test_run_evaluation_cli_help_works():
    script_path = PROJECT_ROOT / "evaluation" / "run_evaluation.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Run RAG evaluation." in result.stdout


def test_run_evaluation_default_data_root_exists():
    assert _default_data_root().exists()


def test_summarize_diagnostic_trends_reports_retrieval_aggregates():
    results = [
        {
            "case_id": "a",
            "scenario_type": "single_turn_detail",
            "turns": [
                {
                    "diagnostics": {
                        "summary": {"primary_failure_layer": "none"},
                        "retrieval": {
                            "metrics": {
                                "final_target_purity": 1.0,
                                "purity_gain": 0.4,
                                "filter_overkill_risk": False,
                                "content_type_mismatch_ratio": 0.0,
                            }
                        },
                    }
                }
            ],
        },
        {
            "case_id": "b",
            "scenario_type": "single_turn_detail",
            "turns": [
                {
                    "diagnostics": {
                        "summary": {"primary_failure_layer": "retrieval"},
                        "retrieval": {
                            "metrics": {
                                "final_target_purity": 0.5,
                                "purity_gain": 0.1,
                                "filter_overkill_risk": True,
                                "content_type_mismatch_ratio": 0.5,
                            }
                        },
                    }
                }
            ],
        },
        {
            "case_id": "c",
            "scenario_type": "irrelevant_question",
            "turns": [
                {
                    "diagnostics": {
                        "summary": {"primary_failure_layer": "generation"},
                        "retrieval": {
                            "metrics": {
                                "final_target_purity": None,
                                "purity_gain": None,
                                "filter_overkill_risk": False,
                                "content_type_mismatch_ratio": None,
                            }
                        },
                    }
                }
            ],
        },
    ]

    trends = summarize_diagnostic_trends(results)

    assert trends["retrieval"]["avg_final_target_purity"] == 0.75
    assert trends["retrieval"]["avg_purity_gain"] == 0.25
    assert trends["retrieval"]["filter_overkill_count"] == 1
    assert trends["retrieval"]["avg_content_type_mismatch_ratio"] == 0.25
    assert trends["failures_by_layer"]["retrieval"] == 1
    assert trends["scenario_failure_counts"]["single_turn_detail"] == 1
