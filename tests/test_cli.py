"""CLI 契约测试：退出码三语义、门控可见性、JSON 输出。"""

from __future__ import annotations

import io
import json
import os

import pytest
from conftest import DATA, load_rule_values, param

from ebikecheck import cli

VALUES = load_rule_values(DATA)


def _run(argv):
    return cli.main(argv)


def test_selfcheck_exit_zero_and_reports_gating(capsys):
    code = _run(["selfcheck", "--data-dir", DATA, "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verified_total"] > 0
    assert payload["pending_total"] > 0
    assert payload["frozen"] is False
    # 非冻结态该断言为 None（不报 FAIL），不让源码运行被误判。
    assert payload["data_dir_within_exe_dir"] is None


def test_check_clean_profile_exit_zero(capsys, written_profile, tmp_path):
    speed = VALUES["max_design_speed"]
    plastic = VALUES["plastic_mass_ratio"]
    mass = VALUES["vehicle_mass"]
    params = {
        "max_design_speed": param(str(float(speed["value"]) - 1), speed["unit"]),
        "plastic_mass_ratio": param(str(float(plastic["value"]) - 1), plastic["unit"]),
        "vehicle_mass": param(str(float(mass["value"]) - 1), mass["unit"]),
        "battery_type": param("lead_acid", ""),
        "over_speed_power_cutoff": param(True, ""),
        "anti_tamper_battery_pack": param(True, ""),
        "anti_tamper_controller": param(True, ""),
        "anti_tamper_speed_limiter": param(True, ""),
    }
    path = written_profile(params)
    code = _run(["check", path, "--data-dir", DATA])
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "整体结论: 符合" in out


def test_check_non_compliant_exit_one(capsys, written_profile):
    speed = VALUES["max_design_speed"]
    from decimal import Decimal

    over = str(Decimal(str(speed["value"])) + Decimal("0.1"))
    params = {
        "max_design_speed": param(over, speed["unit"]),
        "battery_type": param("lead_acid", ""),
    }
    path = written_profile(params)
    code = _run(["check", path, "--data-dir", DATA])
    assert code == cli.EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "整体结论: 不符合" in out


def test_not_provided_does_not_change_exit_code(capsys, written_profile):
    """**退出码语义的关键**：未提供 ≠ 检出不符合，退出码必须仍为 0。"""
    params = {
        "max_design_speed": param("20", "km/h"),
        "battery_type": param("lead_acid", ""),
        "over_speed_power_cutoff": param(True, ""),
        "anti_tamper_battery_pack": param(True, ""),
        "anti_tamper_controller": param(True, ""),
        "anti_tamper_speed_limiter": param(True, ""),
    }
    path = written_profile(params)
    code = _run(["check", path, "--data-dir", DATA, "--json"])
    assert code == cli.EXIT_OK, "存在 not_provided 不应判为检出违规"
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["not_provided"] > 0
    assert payload["counts"]["non_compliant"] == 0
    assert payload["overall"] == "not_provided"


def test_check_reports_excluded_rules_explicitly(capsys, written_profile):
    """门控必须"不留空"：未启用规则要显式列出。"""
    path = written_profile({"max_design_speed": param("20", "km/h")})
    code = _run(["check", path, "--data-dir", DATA])
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "未启用" in out
    assert "not_verified" in out


def test_missing_file_exit_two(capsys, tmp_path):
    code = _run(["check", os.path.join(str(tmp_path), "nope.json"), "--data-dir", DATA])
    assert code == cli.EXIT_USAGE


def test_bad_json_exit_two(tmp_path):
    path = os.path.join(str(tmp_path), "bad.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("{ not json")
    assert _run(["check", path, "--data-dir", DATA]) == cli.EXIT_USAGE


def test_no_command_exit_two():
    assert _run([]) == cli.EXIT_USAGE


def test_bench_unknown_suite_exit_two(capsys):
    """``--only`` 传未知名必须走 exit 2（"跑了个不存在的基准"不得被读成成功）。"""
    code = _run(["bench", "--only", "definitely-not-a-suite", "--data-dir", DATA])
    assert code == cli.EXIT_USAGE


def test_bench_all_suites_pass(capsys):
    code = _run(["bench", "--data-dir", DATA, "--json"])
    assert code == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["thresholds_met"] is True
    assert payload["timing_met"] is True
    assert payload["suites"], "基准必须真的跑了套件"


def test_bench_single_suite(capsys):
    code = _run(["bench", "--only", "boundary", "--data-dir", DATA, "--json"])
    assert code == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert [item["name"] for item in payload["suites"]] == ["boundary"]


def test_version_subcommand(capsys):
    assert _run(["version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ebikecheck ")


def test_rules_overview(capsys):
    assert _run(["rules", "--data-dir", DATA, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["rulesets"]) == 4


def test_missing_data_dir_exit_two(capsys, tmp_path):
    empty = os.path.join(str(tmp_path), "empty")
    os.makedirs(empty, exist_ok=True)
    code = _run(["selfcheck", "--data-dir", empty])
    assert code == cli.EXIT_USAGE
