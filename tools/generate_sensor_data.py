#!/usr/bin/env python3
"""智维 (ZhiWei) 工业设备传感器数据生成器.

模拟一台离心泵机组（电机 + 联轴器 + 离心泵 + 轴承座）的多传感器时序数据，
用于「异常检测 -> 故障诊断 -> 维修方案 -> 模拟维修 -> 维修后验证」的闭环验证。

只依赖 Python 标准库，无需第三方包。

用法:
    python generate_sensor_data.py --out-dir ../data
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

COLUMNS = [
    "timestamp",
    "temperature_c",
    "vibration_mm_s",
    "speed_rpm",
    "current_a",
    "pressure_mpa",
    "flow_m3h",
]

# 设备额定工况（正常运行基线）
BASE = {
    "temperature_c": 62.0,
    "vibration_mm_s": 2.10,
    "speed_rpm": 2980.0,
    "current_a": 42.0,
    "pressure_mpa": 0.620,
    "flow_m3h": 55.0,
}

# 正常工况下的随机噪声标准差
NOISE = {
    "temperature_c": 0.35,
    "vibration_mm_s": 0.080,
    "speed_rpm": 4.0,
    "current_a": 0.35,
    "pressure_mpa": 0.008,
    "flow_m3h": 0.60,
}

# 周期性工况波动（模拟负载缓慢变化），周期单位：秒
CYCLE = {
    "temperature_c": (0.60, 900.0),
    "vibration_mm_s": (0.060, 300.0),
    "speed_rpm": (3.0, 600.0),
    "current_a": (0.80, 480.0),
    "pressure_mpa": (0.010, 400.0),
    "flow_m3h": (0.90, 400.0),
}

SCENARIOS = {
    "normal": {
        "description": "正常运行基线（无故障）",
        "onset_s": None,
        "ramp_s": None,
        "delta": {},
        "noise_gain": {},
        "expected_fault": None,
    },
    "bearing_wear": {
        "description": "轴承磨损：摩擦增大，轴承温度与振动同步上升",
        "onset_s": 180.0,
        "ramp_s": 180.0,
        "delta": {"temperature_c": 19.0, "vibration_mm_s": 6.4, "current_a": 3.2},
        "noise_gain": {"vibration_mm_s": 3.0, "temperature_c": 2.0},
        "expected_fault": "bearing_wear",
    },
    "misalignment": {
        "description": "联轴器不对中 / 转子不平衡：振动剧烈上升，温度次之",
        "onset_s": 180.0,
        "ramp_s": 150.0,
        "delta": {"vibration_mm_s": 9.2, "temperature_c": 7.0, "current_a": 4.0},
        "noise_gain": {"vibration_mm_s": 3.5},
        "expected_fault": "misalignment",
    },
    "overload": {
        "description": "负载过大 / 转动卡涩：电流与温度上升，转速下降",
        "onset_s": 180.0,
        "ramp_s": 120.0,
        "delta": {"current_a": 15.5, "temperature_c": 13.5, "speed_rpm": -75.0, "vibration_mm_s": 2.6},
        "noise_gain": {"current_a": 2.5},
        "expected_fault": "overload",
    },
    "cavitation": {
        "description": "泵气蚀 / 入口堵塞：出口压力与流量下降，振动上升",
        "onset_s": 180.0,
        "ramp_s": 150.0,
        "delta": {"pressure_mpa": -0.28, "flow_m3h": -23.0, "vibration_mm_s": 5.0, "temperature_c": 4.5},
        "noise_gain": {"pressure_mpa": 4.0, "flow_m3h": 3.0, "vibration_mm_s": 2.5},
        "expected_fault": "cavitation",
    },
}


def ramp_factor(t: float, onset, ramp) -> float:
    """故障从 onset 秒开始，在 ramp 秒内线性增强到满强度。"""
    if onset is None:
        return 0.0
    if t <= onset:
        return 0.0
    if not ramp or ramp <= 0:
        return 1.0
    return min(1.0, (t - onset) / ramp)


def generate_rows(spec: dict, samples: int, seed: int, start: datetime) -> list[dict]:
    rng = random.Random(seed)
    delay = spec.get("onset_s")
    ramp = spec.get("ramp_s")
    delta = spec.get("delta", {})
    gain = spec.get("noise_gain", {})
    rows: list[dict] = []

    for i in range(samples):
        t = float(i)
        f = ramp_factor(t, delay, ramp)
        row = {"timestamp": (start + timedelta(seconds=i)).isoformat(timespec="seconds")}
        for key in COLUMNS[1:]:
            amplitude, period = CYCLE[key]
            value = BASE[key] + amplitude * math.sin(2.0 * math.pi * t / period)
            value += delta.get(key, 0.0) * f
            sigma = NOISE[key] * (1.0 + gain.get(key, 0.0) * f)
            value += rng.gauss(0.0, sigma)
            row[key] = round(value, 3 if key in ("pressure_mpa",) else 2)
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成工业设备多传感器时序数据")
    parser.add_argument("--out-dir", default="../data", help="输出目录")
    parser.add_argument("--samples", type=int, default=600, help="每个场景的采样点数（1Hz）")
    parser.add_argument("--seed", type=int, default=20261009, help="随机种子")
    parser.add_argument("--start", default="2026-10-09T08:00:00", help="起始时间")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(args.start)

    manifest = {
        "asset": "离心泵机组 P-101（电机 + 联轴器 + 离心泵 + 轴承座）",
        "sampling_hz": 1.0,
        "samples_per_scenario": args.samples,
        "columns": COLUMNS,
        "units": {
            "temperature_c": "°C",
            "vibration_mm_s": "mm/s",
            "speed_rpm": "rpm",
            "current_a": "A",
            "pressure_mpa": "MPa",
            "flow_m3h": "m³/h",
        },
        "normal_baseline": BASE,
        "scenarios": {},
    }

    for index, (name, spec) in enumerate(SCENARIOS.items()):
        rows = generate_rows(spec, args.samples, args.seed + index * 17, start)
        file_name = f"sensor_{name}.csv"
        write_csv(out_dir / file_name, rows)
        manifest["scenarios"][name] = {
            "file": file_name,
            "description": spec["description"],
            "expected_fault": spec["expected_fault"],
            "fault_onset_s": spec["onset_s"],
            "fault_full_s": (spec["onset_s"] + spec["ramp_s"]) if spec["onset_s"] and spec["ramp_s"] else None,
            "rows": len(rows),
        }
        print(f"[ok] {file_name:<28} {len(rows)} rows  -> {spec['description']}")

    (out_dir / "scenarios.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已生成 {len(SCENARIOS)} 个场景，输出目录: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())