#!/usr/bin/env python3
"""智维 (ZhiWei) 工业设备故障诊断工具.

输入传感器 CSV（内部先跑异常检测），把「各传感器的持续偏移特征」
与故障特征库做方向 + 相对强度匹配（余弦相似度），输出排序后的故障候选、
判据证据和维修建议。

关键设计：
  1. 只有被异常检测判定为「持续偏移」的传感器才进入特征向量，
     避免正常工况的轻微漂移被当成故障证据。
  2. 偏移强度按 z 分数保留相对大小（饱和值 50σ），
     因此「振动暴涨但温度只微升」与「振动/温度同步上升」可区分。

只依赖 Python 标准库；复用同目录的 anomaly_detect.py。

用法:
    python fault_diagnose.py ../data/sensor_bearing_wear.csv
    python fault_diagnose.py ../data/x.csv --json out.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_detect import SENSOR_LABELS, SENSOR_UNITS, detect as detect_anomalies  # noqa: E402

from fault_library import FAULT_LIBRARY  # noqa: E402

SENSOR_ORDER = ["temperature_c", "vibration_mm_s", "speed_rpm", "current_a", "pressure_mpa", "flow_m3h"]
SIGMA_K = 50.0           # 软饱和常数：magnitude = |z| / (|z| + K)
                         # 用软饱和替代硬截断，避免强信号被削平后破坏测点间的相对强度
                         # （硬截断会让"温度也很大但振动更大"的残留信号误判成振动主导型故障）
NOISE_FLOOR_Z = 1.5      # 低于噪声下限视为"无偏移"


def observed_vector(sensors: dict) -> tuple[list[float], dict, list[str]]:
    """只把出现『持续偏移』的传感器计入特征向量。"""
    vector: list[float] = []
    shifts: dict[str, float] = {}
    active: list[str] = []
    for name in SENSOR_ORDER:
        entry = sensors.get(name) or {}
        z = float(entry.get("tail_shift_sigma", 0.0))
        persistent = int(entry.get("persistent_anomaly_points", 0))
        shifts[name] = z
        if persistent <= 0 or abs(z) < NOISE_FLOOR_Z:
            vector.append(0.0)
            continue
        magnitude = abs(z) / (abs(z) + SIGMA_K)
        vector.append(math.copysign(magnitude, z))
        active.append(name)
    return vector, shifts, active


def target_vector(signature: dict) -> list[float]:
    return [signature.get(name, (0.0, 0))[0] * signature.get(name, (0.0, 0))[1] for name in SENSOR_ORDER]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def health_index(anomaly: dict, max_shift: float) -> int:
    summary = anomaly["summary"]
    if summary["status"] == "normal":
        return 100
    affected = len(summary.get("affected_sensors", []))
    score = 100 - 15 * affected
    score -= 20 if summary.get("severity") == "critical" else 10
    if max_shift >= 50:
        score -= 10
    return int(max(0, min(100, round(score))))


def diagnose(path: Path, baseline_s: float, z_threshold: float, baseline_csv: Path | None = None) -> dict:
    anomaly = detect_anomalies(path, baseline_s, 61, z_threshold, 5, 6.0, baseline_csv)
    sensors = anomaly["sensors"]
    observed, shifts, active = observed_vector(sensors)
    max_shift = max((abs(v) for v in shifts.values()), default=0.0)
    healthy = not active or anomaly["summary"]["status"] == "normal"

    candidates = []
    for key, spec in FAULT_LIBRARY.items():
        similarity = cosine(observed, target_vector(spec["signature"]))
        expected = list(spec["signature"])
        matched = [s for s in expected if s in active]
        candidates.append({
            "fault": key,
            "name": spec["name"],
            "confidence": round(max(0.0, similarity), 3),
            "signature_match": f"{len(matched)}/{len(expected)}",
            "evidence": [
                {
                    "sensor": s,
                    "label": SENSOR_LABELS.get(s, s),
                    "unit": SENSOR_UNITS.get(s, ""),
                    "observed_shift_sigma": round(shifts.get(s, 0.0), 2),
                    "expected_direction": "上升" if spec["signature"][s][1] > 0 else "下降",
                    "matched": s in active,
                }
                for s in expected
            ],
            "actions": spec["actions"],
            "parts": spec["parts"],
        })

    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    primary = candidates[0]

    if healthy:
        status, verdict = "normal", "健康（无持续异常）"
        primary_block = None
    elif primary["confidence"] >= 0.75:
        status, verdict = "diagnosed", primary["name"]
        primary_block = {
            "fault": primary["fault"],
            "name": primary["name"],
            "confidence": primary["confidence"],
            "signature_match": primary["signature_match"],
            "evidence": primary["evidence"],
            "recommended_actions": primary["actions"],
            "parts": primary["parts"],
        }
    else:
        status = "uncertain"
        verdict = f"疑似 {primary['name']}（证据不足，需人工复核）"
        primary_block = {
            "fault": primary["fault"],
            "name": primary["name"],
            "confidence": primary["confidence"],
            "signature_match": primary["signature_match"],
            "evidence": primary["evidence"],
            "recommended_actions": primary["actions"],
            "parts": primary["parts"],
        }

    runner_up = candidates[1] if len(candidates) > 1 else None
    differential = None
    if not healthy and runner_up and runner_up["confidence"] > 0:
        differential = (
            f"主判「{primary['name']}」相似度 {primary['confidence']}，"
            f"次选「{runner_up['name']}」相似度 {runner_up['confidence']}，"
            f"差值 {round(primary['confidence'] - runner_up['confidence'], 3)}"
        )

    return {
        "tool": "fault_diagnose",
        "file": path.name,
        "asset": "离心泵机组 P-101（电机 + 联轴器 + 离心泵 + 轴承座）",
        "status": status,
        "verdict": verdict,
        "health_index": health_index(anomaly, max_shift),
        "active_sensors": active,
        "observed_shifts_sigma": {SENSOR_LABELS.get(k, k): round(v, 2) for k, v in shifts.items()},
        "candidates": candidates,
        "primary_diagnosis": primary_block,
        "differential": differential,
        "anomaly_summary": anomaly["summary"],
        "next_step": (
            "进入维修方案与模拟维修阶段"
            if status == "diagnosed"
            else ("设备健康，保持状态监测" if status == "normal" else "建议人工复核或补充数据后再诊断")
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="工业设备故障诊断")
    parser.add_argument("csv", help="传感器 CSV 路径")
    parser.add_argument("--baseline-s", type=float, default=120.0)
    parser.add_argument("--z-threshold", type=float, default=4.0)
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--compact", action="store_true", help="省略异常检测明细")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    report = diagnose(path, args.baseline_s, args.z_threshold)
    if args.compact:
        report.pop("anomaly_summary", None)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())