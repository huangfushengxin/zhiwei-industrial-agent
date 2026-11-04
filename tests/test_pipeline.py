import pytest

from closed_loop import run
from fault_diagnose import diagnose
from verify_repair import verify


@pytest.mark.parametrize("fault", ["normal", "bearing_wear", "misalignment", "overload", "cavitation"])
def test_simulated_diagnosis_matches_fixture_truth(data_dir, fault):
    result = diagnose(data_dir / f"sensor_{fault}.csv", 120.0, 4.0)
    if fault == "normal":
        assert result["status"] == "normal"
        assert result["primary_diagnosis"] is None
    else:
        assert result["status"] == "diagnosed"
        assert result["primary_diagnosis"]["fault"] == fault


@pytest.mark.parametrize("fault", ["bearing_wear", "misalignment", "overload", "cavitation"])
def test_successful_repair_has_verification_evidence(data_dir, tmp_path, fault):
    result = run(data_dir / f"sensor_{fault}.csv", out_dir=tmp_path)
    assert result["status"] == "repaired"
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["verify_status"] == "success"
    assert any(step["step"] == "verify_repair" for step in result["trace"])


def test_normal_equipment_does_not_trigger_repairs(data_dir, tmp_path):
    result = run(data_dir / "sensor_normal.csv", out_dir=tmp_path)
    assert result["status"] == "healthy"
    assert not result["attempts"]
    assert not list(tmp_path.iterdir())


def test_failed_verification_triggers_replanning(data_dir, tmp_path):
    result = run(data_dir / "sensor_overload.csv", 0.5, out_dir=tmp_path)
    assert result["status"] == "repaired"
    assert [a["verify_status"] for a in result["attempts"]][0] != "success"
    assert result["attempts"][1]["verify_status"] == "success"
    assert any(s["step"] == "replan" for s in result["trace"])


def test_attempt_limit_reports_unresolved_instead_of_false_success(data_dir, tmp_path):
    result = run(data_dir / "sensor_overload.csv", 0.0, max_attempts=1, out_dir=tmp_path)
    assert result["status"] == "unresolved"
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["verify_status"] != "success"


def test_post_repair_data_uses_pre_repair_baseline(data_dir):
    result = verify(data_dir / "test/test_02_bearing_fault.csv",
                    data_dir / "test/test_03_repair_failed.csv", 120.0, 4.0)
    assert result["status"] != "success"
    assert result["worst_residual_sigma"] >= 4.0


@pytest.mark.parametrize("kwargs", [{"max_attempts": 0}, {"repair_effectiveness": -0.1},
                                    {"repair_effectiveness": 1.1}])
def test_invalid_loop_limits_are_rejected(data_dir, kwargs):
    with pytest.raises(ValueError):
        run(data_dir / "sensor_overload.csv", **kwargs)


def test_missing_input_is_reported_as_error(tmp_path):
    result = run(tmp_path / "missing.csv", out_dir=tmp_path)
    assert result["status"] == "error"
    assert result["trace"][0]["status"] == "failed"
