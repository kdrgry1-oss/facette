import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("audit_gate", Path(__file__).parents[2] / "scripts/check_dependency_audit.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_pip_findings_are_not_scanner_failure():
    data = json.dumps({"dependencies": [{"name": "example", "vulns": [{"id": "TEST"}]}]})
    assert gate.check("pip", data, 1)[0] is False


def test_pip_clean_completed_scan():
    assert gate.check("pip", json.dumps({"dependencies": [{"vulns": []}]}), 0)[0] is True


@pytest.mark.parametrize("content,status", [("{}", 0), ("", 2),
    ('{"dependencies":[{"skip_reason":"unresolved"}]}', 0), ('{"dependencies":[{"vulns":[]}]}', 2)])
def test_broken_pip_scan_never_passes(content, status):
    with pytest.raises(ValueError):
        gate.check("pip", content, status)


def yarn_summary(**counts):
    return json.dumps({"type": "auditSummary", "data": {"vulnerabilities": {
        "info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, **counts}}})


def test_yarn_gates_high_critical_not_lower_severity():
    assert gate.check("yarn", yarn_summary(high=2), 8)[0] is False
    assert gate.check("yarn", yarn_summary(critical=1), 16)[0] is False
    assert gate.check("yarn", yarn_summary(low=3, moderate=1), 6)[0] is True


@pytest.mark.parametrize("content,status", [("", 0), ('{"type":"error"}', 1), (yarn_summary(), 1)])
def test_yarn_incomplete_or_inconsistent_scan_never_passes(content, status):
    with pytest.raises(ValueError):
        gate.check("yarn", content, status)
