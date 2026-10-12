#!/usr/bin/env python3
"""生成「边界案例」数据：早期轻微故障（刚刚越过检测阈值的早期轴承磨损）.

与 sensor_bearing_wear.csv（满强度故障）不同，本案例的故障幅度很小，
预期落在 warning 级别，用于验证智维的早期发现与处置能力。

用法:
    python make_boundary_case.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_sensor_data import CYCLE, NOISE, BASE, generate_rows, write_csv  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"

# 早期轻微轴承磨损：幅度约为满强度的 25%，属于"刚越过检测阈值"的边界工况
SPEC = {
    "onset_s": 180.0,
    "ramp_s": 240.0,
    "delta": {"temperature_c": 1.8, "vibration_mm_s": 0.45, "current_a": 0.6},
    "noise_gain": {},
}


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = generate_rows(SPEC, 600, 20261010, datetime.fromisoformat("2026-10-10T08:00:00"))
    out = DATA_DIR / "sensor_boundary_bearing_early.csv"
    write_csv(out, rows)

    meta = {
        "scenario": "boundary_bearing_early",
        "file": out.name,
        "description": "边界案例：早期轻微轴承磨损（幅度约满强度 25%，刚越过检测阈值）",
        "expected_fault": "bearing_wear",
        "expected_severity": "warning",
        "fault_onset_s": SPEC["onset_s"],
        "fault_full_s": SPEC["onset_s"] + SPEC["ramp_s"],
        "delta": SPEC["delta"],
        "rows": len(rows),
    }
    (DATA_DIR / "boundary_case.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] {out.name}  {len(rows)} rows -> {meta['description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())