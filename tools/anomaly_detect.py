#!/usr/bin/env python3
"""智维 (ZhiWei) 工业设备传感器异常检测工具.

方法：基线比对 + 局部滚动中位数 + 鲁棒 z 分数（中位数 / MAD）。

为什么用滚动中位数：真实工况本身有周期性缓慢波动（负载、环境温度），
直接用全局基线会把正常波动误判为异常。这里先把周期性趋势用局部中位数
吸收掉，再检测「持续偏移（缓变故障）」和「瞬时尖峰」两类异常。

只依赖 Python 标准库。

用法:
    python anomaly_detect.py ../data/sensor_bearing_wear.csv
    python anomaly_detect.py ../data/x.csv --baseline-s 120 --window-s 61 --z-threshold 4
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

SENSOR_UNITS = {
    "temperature_c": "°C",
    "vibration_mm_s": "mm/s",
    "speed_rpm": "rpm",
    "current_a": "A",
    "pressure_mpa": "MPa",
    "flow_m3h": "m³/h",
}

SENSOR_LABELS = {
    "temperature_c": "轴承温度",
    "vibration_mm_s": "振动速度",
    "speed_rpm": "转速",
    "current_a": "电机电流",
    "pressure_mpa": "出口压力",
    "flow_m3h": "出口流量",
}

NON_SENSOR_COLUMNS = {"timestamp", "time", "label", "scenario", "fault", "fault_type"}


def read_series(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = [c for c in (reader.fieldnames or []) if c and c not in NON_SENSOR_COLUMNS]
        timestamps: list[str] = []
        series: dict[str, list[float]] = {c: [] for c in columns}
        for row in reader:
            timestamps.append(str(row.get("timestamp", "")))
            for c in columns:
                try:
                    series[c].append(float(row.get(c)))
                except (TypeError, ValueError):
                    series[c].append(float("nan"))
    return timestamps, series


def robust_stats(values: list[float]) -> tuple[float, float]:
    clean = [v for v in values if v == v]
    if not clean:
        return 0.0, 0.0
    median = statistics.median(clean)
    mad = statistics.median([abs(v - median) for v in clean])
    sigma = 1.4826 * mad
    if sigma <= 0:
        sigma = statistics.pstdev(clean) if len(clean) > 1 else 0.0
    return median, sigma


def rolling_median(values: list[float], window: int) -> list[float]:
    half = max(1, window // 2)
    n = len(values)
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = [v for v in values[lo:hi] if v == v]
        out.append(statistics.median(chunk) if chunk else float("nan"))
    return out


def find_runs(flags: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    current: list[int] = []
    last = -10
    for index in flags:
        if index == last + 1:
            current.append(index)
        else:
            if current:
                runs.append(current)
            current = [index]
        last = index
    if current:
        runs.append(current)
    return runs


def _display_path(value) -> str:
    """相对项目根输出路径，避免绝对路径（含用户名）写进报告。"""
    try:
        return str(Path(value).resolve().relative_to(Path(__file__).resolve().parents[1]))
    except Exception:
        return Path(value).name


def detect(path: Path, baseline_s: float, window_s: int, z_threshold: float,
           min_run: int, spike_threshold: float, baseline_csv: Path | None = None):
    timestamps, series = read_series(path)
    n = len(timestamps)
    if n == 0:
        raise SystemExit(f"no rows in {path}")

    baseline_count = max(10, min(n, int(baseline_s)))
    window = max(3, min(n, window_s))

    # 可选：用另一个文件（例如维修前数据）的基线做对比。
    # 这样"从第一秒就存在"的残留故障不会被当成正常基线而漏检。
    external_baseline: dict[str, list[float]] | None = None
    if baseline_csv is not None:
        _, base_series = read_series(Path(baseline_csv))
        external_baseline = {key: vals[:baseline_count] for key, vals in base_series.items()}

    report = {
        "tool": "anomaly_detect",
        "file": path.name,
        "path": _display_path(path),
        "method": "robust rolling-median residual (median/MAD)",
        "samples": n,
        "baseline_samples": baseline_count,
        "rolling_window": window,
        "z_threshold": z_threshold,
        "spike_threshold": spike_threshold,
        "min_run": min_run,
        "baseline_source": _display_path(baseline_csv) if baseline_csv is not None else path.name,
        "sensors": {},
        "anomalies": [],
        "spikes": [],
        "summary": {},
    }

    affected: list[dict] = []
    max_shift = 0.0
    persistent_total = 0
    spike_total = 0

    for name, values in series.items():
        base = external_baseline.get(name) if external_baseline else None
        if not base:
            base = values[:baseline_count]
        median, sigma = robust_stats(base)
        unit = SENSOR_UNITS.get(name, "")
        label = SENSOR_LABELS.get(name, name)
        lo = median - z_threshold * sigma
        hi = median + z_threshold * sigma

        local = rolling_median(values, window)
        shift_z = [((local[i] - median) / sigma) if sigma > 0 and local[i] == local[i] else 0.0
                   for i in range(n)]
        residual = [abs(values[i] - local[i]) / sigma if sigma > 0 and local[i] == local[i] else 0.0
                    for i in range(n)]

        persistent_idx = [i for i in range(n) if abs(shift_z[i]) > z_threshold]
        runs = [r for r in find_runs(persistent_idx) if len(r) >= min_run]
        sustained = [i for r in runs for i in r]

        spike_idx = [i for i in range(n) if residual[i] > spike_threshold]

        tail = values[int(n * 0.75):]
        tail_median = statistics.median([v for v in tail if v == v]) if tail else median
        tail_shift = (tail_median - median) / sigma if sigma > 0 else 0.0

        entry = {
            "label": label,
            "unit": unit,
            "baseline_median": round(median, 4),
            "baseline_sigma": round(sigma, 4),
            "expected_range": [round(lo, 4), round(hi, 4)],
            "persistent_anomaly_points": len(sustained),
            "transient_spike_points": len(spike_idx),
            "max_abs_shift_z": 0.0,
            "tail_shift_sigma": round(tail_shift, 2),
            "direction": "steady",
        }

        if sustained:
            worst = max(sustained, key=lambda i: abs(shift_z[i]))
            max_z = abs(shift_z[worst])
            direction = "high" if shift_z[worst] > 0 else "low"
            entry.update({"max_abs_shift_z": round(max_z, 2), "direction": direction,
                          "first_anomaly_ts": timestamps[sustained[0]],
                          "last_anomaly_ts": timestamps[sustained[-1]]})
            persistent_total += len(sustained)
            max_shift = max(max_shift, max_z)
            affected.append({"sensor": name, "label": label, "direction": direction,
                             "max_abs_shift_z": round(max_z, 2),
                             "tail_shift_sigma": round(tail_shift, 2),
                             "persistent_points": len(sustained)})
            for i in sustained[:200]:
                report["anomalies"].append({
                    "timestamp": timestamps[i],
                    "sensor": name,
                    "label": label,
                    "value": round(values[i], 4),
                    "local_median": round(local[i], 4),
                    "expected_range": [round(lo, 4), round(hi, 4)],
                    "unit": unit,
                    "shift_z": round(shift_z[i], 2),
                    "direction": "high" if shift_z[i] > 0 else "low",
                })

        if spike_idx:
            spike_total += len(spike_idx)
            for i in spike_idx[:20]:
                report["spikes"].append({
                    "timestamp": timestamps[i],
                    "sensor": name,
                    "label": label,
                    "value": round(values[i], 4),
                    "local_median": round(local[i], 4),
                    "residual_sigma": round(residual[i], 2),
                    "unit": unit,
                })

        report["sensors"][name] = entry

    if max_shift >= 2 * z_threshold:
        severity = "critical"
    elif max_shift >= z_threshold:
        severity = "warning"
    else:
        severity = "normal"

    labels = [a["label"] for a in affected]
    report["summary"] = {
        "status": "anomaly" if sustained_any(report) else "normal",
        "severity": severity,
        "persistent_anomaly_points": persistent_total,
        "transient_spike_points": spike_total,
        "affected_sensors": [a["sensor"] for a in affected],
        "affected_detail": affected,
        "max_abs_shift_z": round(max_shift, 2),
        "conclusion": (
            f"检测到 {len(affected)} 个传感器出现持续偏移：{'、'.join(labels)}"
            if affected else "未检测到持续性异常，设备处于正常工况"
        ),
    }
    return report


def sustained_any(report) -> bool:
    return any(s.get("persistent_anomaly_points", 0) > 0 for s in report["sensors"].values())


def main() -> int:
    parser = argparse.ArgumentParser(description="工业传感器异常检测（滚动基线 + 鲁棒 z 分数）")
    parser.add_argument("csv", help="传感器 CSV 路径")
    parser.add_argument("--baseline-s", type=float, default=120.0, help="基线窗口（默认 120）")
    parser.add_argument("--window-s", type=int, default=61, help="滚动中位数窗口（默认 61）")
    parser.add_argument("--z-threshold", type=float, default=4.0, help="持续偏移 z 阈值（默认 4.0）")
    parser.add_argument("--spike-threshold", type=float, default=6.0, help="瞬时尖峰阈值（默认 6.0）")
    parser.add_argument("--min-run", type=int, default=5, help="持续异常最少连续点数（默认 5）")
    parser.add_argument("--baseline-csv", dest="baseline_csv", default=None, help="用另一个文件的基线做对比（如维修前数据）")
    parser.add_argument("--json", dest="json_out", help="把结果写入该文件")
    parser.add_argument("--compact", action="store_true", help="只输出摘要")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    report = detect(path, args.baseline_s, args.window_s, args.z_threshold, args.min_run,
                    args.spike_threshold,
                    Path(args.baseline_csv) if args.baseline_csv else None)
    if args.compact:
        report.pop("anomalies", None)
        report.pop("spikes", None)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())