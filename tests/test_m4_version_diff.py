"""M4：版本差异对照（FR-07）。

三层都锁：

- 引擎层 ``engine/version_diff.py``：纯 diff 语义（配对/分类/方向），用内存构造
  的规则集测，不依赖仓库数据 —— 规则包将来变了，diff 语义的断言不跟着碎；
- 服务层 ``service.version_diff``：真实规则包端到端（2018 → 2024）+ 错误路径；
- CLI 层 ``diff``/``diff-profile`` 子命令：退出码与人类可读输出。

方向语义（plan/04 §6.3 的"收紧/放宽"）锁进测试：上限类运算符（``<=``）
新值更大 = 放宽；下限类（``>=``）新值更大 = 收紧。
"""

from __future__ import annotations

import json

import pytest

from conftest import DATA, ROOT, SRC

import os
import sys

sys.path.insert(0, os.path.join(SRC, "ebikecheck"))  # noqa: E402  (conftest 已注入，防御性)

from ebikecheck import service
from ebikecheck.engine import rules as rules_mod
from ebikecheck.engine import version_diff as diff_mod
from ebikecheck.engine.rules import Rule


# ---- 内存构造规则（不读仓库数据，语义断言零数据耦合） ----


def _rule(rule_id, param, op, value, unit="", clause="1.1", applies_if=None):
    return Rule(
        id=rule_id,
        param=param,
        op=op,
        value=value,
        unit=unit,
        clause=clause,
        clause_status="verified",
        source={"kind": "standard_text", "url": "https://example.invalid", "retrieved_on": "2026-10-14"},
        status="verified",
        applies_if=applies_if,
        applies_if_raw=applies_if,
        standard_code="GB X",
    )


def _diff(old_specs, new_specs):
    """``[(id, param, op, value, unit, applies_if), ...]`` → VersionDiff。"""
    old_rules = [_rule(*spec[:4], unit=spec[4] if len(spec) > 4 else "", applies_if=spec[5] if len(spec) > 5 else None) for spec in old_specs]
    new_rules = [_rule(*spec[:4], unit=spec[4] if len(spec) > 4 else "", applies_if=spec[5] if len(spec) > 5 else None) for spec in new_specs]
    return diff_mod.diff_rulesets("GBTEST", "V1", old_rules, "V2", new_rules)


def _kinds(diff):
    """``[(param, kind), ...]``（同参数多配对行都保留，不折叠）。"""
    return sorted((entry.param, entry.kind) for entry in diff.entries)


class TestDiffSemantics:
    """纯 diff 语义（收紧/放宽/新增/废止/运算符变化/条件配对）。"""

    def test_threshold_upper_relaxed_when_value_grows(self):
        diff = _diff(
            [("R1", "mass", "<=", 55, "kg")],
            [("R2", "mass", "<=", 63, "kg")],
        )
        assert _kinds(diff) == [("mass", diff_mod.DIFF_RELAXED)]

    def test_threshold_upper_tightened_when_value_shrinks(self):
        diff = _diff(
            [("R1", "speed", "<=", 25, "km/h")],
            [("R2", "speed", "<=", 20, "km/h")],
        )
        assert _kinds(diff) == [("speed", diff_mod.DIFF_TIGHTENED)]

    def test_threshold_lower_tightened_when_value_grows(self):
        diff = _diff(
            [("R1", "range", ">=", 30, "km")],
            [("R2", "range", ">=", 40, "km")],
        )
        assert _kinds(diff) == [("range", diff_mod.DIFF_TIGHTENED)]

    def test_threshold_lower_relaxed_when_value_shrinks(self):
        diff = _diff(
            [("R1", "range", ">=", 40, "km")],
            [("R2", "range", ">=", 30, "km")],
        )
        assert _kinds(diff) == [("range", diff_mod.DIFF_RELAXED)]

    def test_equal_op_change_is_value_changed_not_direction(self):
        """``==`` 目标变化不带收紧/放宽方向（如实记 value_changed）。"""
        diff = _diff(
            [("R1", "flag", "==", "A")],
            [("R2", "flag", "==", "B")],
        )
        assert _kinds(diff) == [("flag", diff_mod.DIFF_VALUE_CHANGED)]

    def test_operator_change_same_value(self):
        diff = _diff(
            [("R1", "x", "<=", 10)],
            [("R2", "x", "<", 10)],
        )
        assert _kinds(diff) == [("x", diff_mod.DIFF_OPERATOR_CHANGED)]

    def test_unchanged_when_op_and_value_equal(self):
        diff = _diff(
            [("R1", "speed", "<=", 25, "km/h")],
            [("R2", "speed", "<=", 25, "km/h")],
        )
        assert _kinds(diff) == [("speed", diff_mod.DIFF_UNCHANGED)]
        assert diff.substantive() == []

    def test_added_only_in_new(self):
        diff = _diff([], [("R2", "plastic", "<=", 5.5, "%")])
        assert _kinds(diff) == [("plastic", diff_mod.DIFF_ADDED)]
        assert diff.entries[0].old_rule_id is None

    def test_removed_only_in_old(self):
        diff = _diff([("R1", "voltage", "<=", 48, "V")], [])
        assert _kinds(diff) == [("voltage", diff_mod.DIFF_REMOVED)]
        assert diff.entries[0].new_rule_id is None

    def test_unconditional_old_pairs_with_split_new_branches(self):
        """旧版无条件 vs 新版条件拆分：逐分支配对，不误报整体新增。"""
        lead = {"param": "battery_type", "op": "==", "value": "lead_acid"}
        other = {"not": {"param": "battery_type", "op": "==", "value": "lead_acid"}}
        diff = _diff(
            [("R1", "mass", "<=", 55, "kg")],
            [
                ("R2a", "mass", "<=", 63, "kg", lead),
                ("R2b", "mass", "<=", 55, "kg", other),
            ],
        )
        kinds = sorted(
            (entry.kind, entry.new_rule_id) for entry in diff.entries
        )
        assert kinds == [
            (diff_mod.DIFF_RELAXED, "R2a"),       # 铅酸分支放宽
            (diff_mod.DIFF_UNCHANGED, "R2b"),     # 其他分支不变
        ]
        assert all("条件分支" in entry.pairing for entry in diff.entries)

    def test_reverse_split_old_pairs_with_unconditional_new(self):
        """旧版条件拆分 vs 新版无条件：反向同样逐分支配对。"""
        lead = {"param": "battery_type", "op": "==", "value": "lead_acid"}
        diff = _diff(
            [
                ("R1a", "mass", "<=", 63, "kg", lead),
                ("R1b", "mass", "<=", 55, "kg"),
            ],
            [("R2", "mass", "<=", 60, "kg")],
        )
        kinds = sorted(entry.kind for entry in diff.entries)
        assert kinds == sorted([diff_mod.DIFF_TIGHTENED, diff_mod.DIFF_RELAXED])

    def test_pending_rules_never_enter_diff(self):
        """diff 只吃生效规则（门控在 Ruleset 层已滤）；此处直接验证入参契约：
        混入 status=pending 的 Rule 属调用方 bug，本模块不做第二道门控。"""
        diff = _diff(
            [("R1", "x", "<=", 10)],
            [("R2", "x", "<=", 10), ("R2p", "y", "<=", 99)],
        )
        # 构造里全部是 verified —— 这里验证"新增参数才出现"而非隐式过滤。
        assert _kinds(diff) == [("x", diff_mod.DIFF_UNCHANGED), ("y", diff_mod.DIFF_ADDED)]

    def test_cross_op_same_value_is_operator_changed(self):
        """value 相同、op 变化（如 ``<=`` 收成 ``==``）如实记 operator_changed；
        不硬套收紧/放宽方向。value 与 op 都变才落 value_changed。"""
        diff = _diff(
            [("R1", "x", "<=", 10)],
            [("R2", "x", "==", 10)],
        )
        assert _kinds(diff) == [("x", diff_mod.DIFF_OPERATOR_CHANGED)]

    def test_to_dict_shape_and_counts(self):
        diff = _diff(
            [("R1", "a", "<=", 10)],
            [("R2", "a", "<=", 20), ("R3", "b", "<=", 1)],
        )
        payload = diff.to_dict()
        assert payload["schema"] == "ebikecheck.version_diff/1.0"
        assert payload["old_version_key"] == "V1"
        assert payload["new_version_key"] == "V2"
        assert payload["counts"] == {"relaxed": 1, "added": 1}
        assert all({"param", "kind", "old_side", "new_side"} <= set(e) for e in payload["entries"])


class TestDiffFromFindings:
    """同档案两版结论对照（动态半边）。"""

    def _dimension(self, findings):
        from ebikecheck.engine.findings import CheckResult

        return CheckResult(
            profile_id="P",
            ruleset_file="r.json",
            ruleset_sha256="0" * 64,
            version_key="V",
            version_anchor={},
            findings=findings,
        )

    def _finding(self, param, state):
        from ebikecheck.engine.findings import Finding

        return Finding(
            rule_id="R", param=param, standard="GB X", clause="1",
            clause_status="verified", op="<=", limit=1, unit="", observed=0,
            state=state,
        )

    def test_only_differing_params_listed(self):
        old = self._dimension([self._finding("a", "compliant"), self._finding("b", "non_compliant")])
        new = self._dimension([self._finding("a", "non_compliant"), self._finding("b", "non_compliant")])
        rows = diff_mod.diff_from_findings(old, new)
        assert rows == [{"param": "a", "old_state": "compliant", "new_state": "non_compliant"}]

    def test_worst_state_wins_per_param(self):
        from ebikecheck.engine.findings import NOT_PROVIDED, COMPLIANT, NON_COMPLIANT

        old = self._dimension([self._finding("a", NOT_PROVIDED), self._finding("a", COMPLIANT)])
        new = self._dimension([self._finding("a", NON_COMPLIANT)])
        rows = diff_mod.diff_from_findings(old, new)
        assert rows == [{"param": "a", "old_state": NOT_PROVIDED, "new_state": NON_COMPLIANT}]


class TestServiceVersionDiff:
    """真实规则包端到端 + 错误路径。"""

    @pytest.fixture(scope="class")
    def diff_payload(self):
        return service.version_diff(str(DATA))

    def test_old_to_new_by_publication_date(self, diff_payload):
        assert diff_payload["old_version_key"] == "GB17761-2018"
        assert diff_payload["new_version_key"] == "GB17761-2024"

    def test_real_ruleset_diff_matches_expected_shape(self, diff_payload):
        """对照 plan/04 §6.3 的登记事实：2024 新增多条 + 铅酸质量分支放宽。"""
        counts = diff_payload["counts"]
        assert counts["added"] == 7
        assert counts["unchanged"] == 2  # max_design_speed + 其他电池质量分支
        assert counts["relaxed"] == 1
        relaxed = [e for e in diff_payload["entries"] if e["kind"] == "relaxed"]
        assert len(relaxed) == 1
        assert relaxed[0]["param"] == "vehicle_mass"
        assert relaxed[0]["pairing"], "配对依据必须写明（可溯源）"

    def test_ruleset_coordinates_present(self, diff_payload):
        assert set(diff_payload["rulesets"]) == {"old", "new"}
        for side in diff_payload["rulesets"].values():
            assert side["file"].endswith(".json")
            assert len(side["sha256"]) == 64

    def test_unknown_version_key_is_usage_error(self):
        with pytest.raises(service.ServiceError):
            service.version_diff(str(DATA), old_version_key="NOPE")

    def test_same_key_rejected(self):
        with pytest.raises(service.ServiceError):
            service.version_diff(str(DATA), old_version_key="GB17761-2024", new_version_key="GB17761-2024")

    def test_explicit_order_override(self):
        payload = service.version_diff(
            str(DATA), old_version_key="GB17761-2024", new_version_key="GB17761-2018"
        )
        assert payload["old_version_key"] == "GB17761-2024"
        # 方向反转：新增变废止。
        assert payload["counts"]["removed"] == 7

    def test_manifest_sha_attached(self, diff_payload):
        assert len(diff_payload["manifest_sha256"]) == 64


class TestServiceVersionDiffProfile:
    """同档案两版结论对照（服务层装配）。"""

    @pytest.fixture(scope="class")
    def wrapped_profile(self, tmp_path_factory):
        """取 version_diff 真值例的档案（wrapper → 裸 profile 落临时文件）。"""
        raw = json.loads(
            open(os.path.join(DATA, "truth", "cases", "SYN-CASE-005.json"), encoding="utf-8").read()
        )
        path = tmp_path_factory.mktemp("m4") / "profile.json"
        path.write_text(json.dumps(raw["profile"], ensure_ascii=False), encoding="utf-8")
        return str(path)

    def test_direction_and_scope_split(self, wrapped_profile):
        payload = service.version_diff_profile(wrapped_profile, str(DATA))
        assert payload["versions"] == ["GB17761-2018", "GB17761-2024"]
        assert payload["profile_id"] == "SYN-EB-005"
        scopes = {item["scope"] for item in payload["scopes"]}
        assert {"vehicle", "battery", "charger"} <= scopes
        vehicle = next(item for item in payload["scopes"] if item["scope"] == "vehicle")
        changes = {row["param"]: (row["old_state"], row["new_state"]) for row in vehicle["state_changes"]}
        # 2018 无 plastic_mass_ratio 规则 → 该参数 2018 下无结论；2024 判不符合。
        assert changes["plastic_mass_ratio"] == (None, "non_compliant")

    def test_missing_profile_is_usage_error(self):
        from ebikecheck.profile import ProfileError

        with pytest.raises((service.ServiceError, ProfileError, os.error)):
            service.version_diff_profile(os.path.join(DATA, "no-such.json"), str(DATA))


class TestCliDiff:
    """CLI 子命令：退出码与人类可读输出。"""

    def _main(self, argv):
        from ebikecheck.cli import main

        return main(argv)

    def test_diff_exit_zero_and_lines(self, capsys):
        code = self._main(["diff"])
        out = capsys.readouterr().out
        assert code == 0
        assert "GB17761-2018" in out and "GB17761-2024" in out
        assert "[新增]" in out and "[放宽]" in out

    def test_diff_json_payload(self, capsys):
        code = self._main(["diff", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == 0
        assert payload["schema"] == "ebikecheck.version_diff/1.0"
        assert payload["counts"]["added"] == 7

    def test_diff_unknown_key_exit_two(self, capsys):
        code = self._main(["diff", "--old", "NOPE"])
        assert code == 2
        assert "错误" in capsys.readouterr().err

    def test_diff_profile_exit_zero(self, tmp_path, capsys):
        raw = json.loads(
            open(os.path.join(DATA, "truth", "cases", "SYN-CASE-005.json"), encoding="utf-8").read()
        )
        profile = tmp_path / "p.json"
        profile.write_text(json.dumps(raw["profile"], ensure_ascii=False), encoding="utf-8")
        code = self._main(["diff-profile", str(profile)])
        out = capsys.readouterr().out
        assert code == 0
        assert "plastic_mass_ratio" in out

    def test_diff_profile_missing_file_exit_two(self):
        assert self._main(["diff-profile", "no-such.json"]) == 2
