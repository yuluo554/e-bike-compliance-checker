"""共享测试夹具与路径常量。

本文件**不需要** ``__init__.py``（pytest 同目录直 import）。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DATA = os.path.join(ROOT, "data")
TOOLS = os.path.join(ROOT, "tools")

if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture(scope="session")
def repo_root():
    return ROOT


@pytest.fixture(scope="session")
def data_dir():
    return DATA


@pytest.fixture()
def written_profile(tmp_path):
    """把一份参数表落成临时档案文件，返回路径。"""

    def _write(params, profile_id="SYN-EB-TEST", design_date="2025-10-01", **extra):
        payload = {
            "schema": "ebikecheck.profile/1.0",
            "profile_id": profile_id,
            "manufacturer": "示例车业（合成）有限公司",
            "uscc": "90000000SYN0000001X",
            "params": params,
        }
        if design_date:
            payload["model_design_date"] = design_date
        payload.update(extra)
        path = os.path.join(str(tmp_path), "{0}.json".format(profile_id))
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
        return path

    return _write


def param(value, unit=""):
    return {"value": value, "unit": unit}


def load_rule_values(data_dir):
    """读取规则包里某几个关键限值（测试断言用，不写死数值）。"""
    with open(
        os.path.join(data_dir, "rules", "gb17761-2024.json"), "r", encoding="utf-8"
    ) as handle:
        raw = json.load(handle)
    out = {}
    for rule in raw["rules"]:
        if rule["status"] == "verified" and rule["value"] is not None:
            out[rule["param"]] = rule
    return out
