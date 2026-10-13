"""档案契约、数据目录定位、对账语义与确定性测试。"""

from __future__ import annotations

import json
import os

import pytest
from conftest import DATA, ROOT, param

from ebikecheck import paths, profile as profile_mod
from ebikecheck.benchmark import cases as case_mod
from ebikecheck.engine.findings import (
    COMPLIANT,
    NON_COMPLIANT,
    NOT_PROVIDED,
    Finding,
    CheckResult,
)


# ---- 档案契约 ----


def test_profile_requires_id_and_params(tmp_path):
    path = os.path.join(str(tmp_path), "bad.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"params": {}}))
    with pytest.raises(profile_mod.ProfileError):
        profile_mod.load_profile(path)


def test_profile_rejects_non_object_param(tmp_path):
    path = os.path.join(str(tmp_path), "bad2.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"profile_id": "P", "params": {"x": 1}}))
    with pytest.raises(profile_mod.ProfileError):
        profile_mod.load_profile(path)


def test_profile_rejects_param_without_value_key(tmp_path):
    path = os.path.join(str(tmp_path), "bad3.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"profile_id": "P", "params": {"x": {"unit": "kg"}}}))
    with pytest.raises(profile_mod.ProfileError):
        profile_mod.load_profile(path)


def test_profile_sha256_is_content_fingerprint(written_profile):
    path = written_profile({"max_design_speed": param("20", "km/h")})
    loaded = profile_mod.load_profile(path)
    assert loaded.sha256 == profile_mod.sha256_file(path)
    assert len(loaded.sha256) == 64


def test_null_value_param_is_not_provided_not_missing(data_dir, written_profile):
    """value 为 null 与参数缺失是两种原因码，都判未提供。"""
    from ebikecheck import service

    params = {
        "max_design_speed": param("20", "km/h"),
        "plastic_mass_ratio": {"value": None, "unit": "%"},
        "battery_type": param("lead_acid", ""),
    }
    result = service.check_profile(written_profile(params), data_dir)
    reasons = {f.param: f.reason for f in result.findings}
    assert reasons["plastic_mass_ratio"] == "null_value"


# ---- 数据目录定位 ----


def test_explicit_data_dir_is_authoritative(tmp_path):
    """显式目录不含 manifest → 返回 None，**不得**静默回落其他候选。

    否则会出现"以为在测 A、实际测了 B"的假绿。
    """
    empty = os.path.join(str(tmp_path), "empty")
    os.makedirs(empty, exist_ok=True)
    assert paths.find_data_dir(explicit=empty) is None


def test_find_data_dir_locates_repo_data():
    found = paths.find_data_dir()
    assert found is not None
    assert os.path.isfile(os.path.join(found, "rules", "manifest.json"))


def test_env_var_data_dir(tmp_path, monkeypatch):
    fake = os.path.join(str(tmp_path), "fakedata")
    os.makedirs(os.path.join(fake, "rules"), exist_ok=True)
    with open(
        os.path.join(fake, "rules", "manifest.json"), "w", encoding="utf-8", newline="\n"
    ) as handle:
        handle.write("{}")
    monkeypatch.setenv(paths.ENV_DATA_DIR, fake)
    assert paths.find_data_dir() == fake


def test_within_helper():
    assert paths.within(os.path.join("a", "b", "c"), os.path.join("a", "b"))
    assert not paths.within("/x/y", "/a/b")


def test_within_helper_handles_cross_drive():
    """跨盘符 commonpath 抛 ValueError → 必须回落 False 而不是崩。"""
    assert paths.within("C:\\a", "D:\\b") is False


def test_data_dir_candidates_order(tmp_path):
    import os as _os

    explicit = os.path.join(str(tmp_path), "explicit")
    ordered = paths.data_dir_candidates(explicit=explicit)
    assert ordered[0] == _os.path.abspath(explicit)


# ---- 对账语义（单一实现源） ----


def _result(states):
    findings = [
        Finding("R-{0}".format(i), param_name, "S", None, "pending", "<=", "1", "kg", "0", state)
        for i, (param_name, state) in enumerate(states.items())
    ]
    return CheckResult("P", "f.json", "x", "K", {}, findings=findings)


def test_expected_states_merges_and_detects_conflict():
    case = {
        "expect": {"findings": {"a": COMPLIANT}},
        "also_expect": {"b": NOT_PROVIDED},
    }
    assert case_mod.expected_states(case) == {"a": COMPLIANT, "b": NOT_PROVIDED}

    conflicting = {
        "expect": {"findings": {"a": COMPLIANT}},
        "also_expect": {"a": NON_COMPLIANT},
    }
    with pytest.raises(ValueError):
        case_mod.expected_states(conflicting)


def test_observed_states_takes_weakest_conclusion():
    """同一参数多条规则（不同适用条件）→ 取最弱结论。"""
    result = _result({"mass": COMPLIANT, "other": NON_COMPLIANT})
    observed = case_mod.observed_states(result)
    assert observed["mass"] == COMPLIANT

    findings = [
        Finding("R1", "mass", "S", None, "pending", "<=", "1", "kg", "0", COMPLIANT),
        Finding("R2", "mass", "S", None, "pending", "<=", "1", "kg", "0", NON_COMPLIANT),
    ]
    mixed = CheckResult("P", "f.json", "x", "K", {}, findings=findings)
    assert case_mod.observed_states(mixed)["mass"] == NON_COMPLIANT


def test_zero_hit_declaration_detects_false_positive():
    case = {"expect_findings": []}
    result = _result({"a": NON_COMPLIANT})
    problems = case_mod.compare_case(result, case)
    assert problems, "声明应零命中却检出不符合 → 必须报差异"


def test_severity_warning_declaration():
    case = {"expect_severity_warning": True}
    result = _result({"a": COMPLIANT})
    assert case_mod.compare_case(result, case), "无降级结论时必须报差异"


def test_nonpass_set_excludes_not_applicable():
    """非通过集 = 不符合 ∪ 未提供；不适用**不算**非通过。"""
    result = _result({"a": COMPLIANT, "b": NON_COMPLIANT, "c": NOT_PROVIDED, "d": "not_applicable"})
    nonpass = dict(case_mod.observed_nonpass(result))
    assert set(nonpass) == {"b", "c"}


# ---- 报告模型 ----


def test_result_serialization_is_deterministic(data_dir, written_profile):
    from ebikecheck import service
    from ebikecheck.io_utils import dumps_json

    path = written_profile({"max_design_speed": param("20", "km/h")})
    first = service.check_profile(path, data_dir)
    second = service.check_profile(path, data_dir)
    assert dumps_json(first.to_dict()) == dumps_json(second.to_dict())


def test_result_carries_source_blocks(data_dir, written_profile):
    """报告必须能给出"这个数值哪来的"（NFR-09）。"""
    from ebikecheck import service

    path = written_profile({"max_design_speed": param("20", "km/h")})
    result = service.check_profile(path, data_dir)
    assert result.source_blocks
    first = result.source_blocks[0]
    for key in ("param", "standard", "clause_status", "source_kind", "retrieved_on"):
        assert key in first


def test_excluded_rules_are_reported_in_result(data_dir, written_profile):
    from ebikecheck import service

    path = written_profile({"max_design_speed": param("20", "km/h")})
    result = service.check_profile(path, data_dir)
    assert result.excluded_rules
    assert all(item.status == "pending" for item in result.excluded_rules)


def test_profile_sha256_recorded(data_dir, written_profile):
    from ebikecheck import service

    path = written_profile({"max_design_speed": param("20", "km/h")})
    result = service.check_profile(path, data_dir)
    assert len(result.profile_sha256) == 64
