#!/usr/bin/env python3
"""智维 (ZhiWei) 流水线验证脚本.

对 data/ 下全部工况数据集运行「异常检测 -> 故障诊断」，
并把诊断结论与 scenarios.json 中的真值比对，输出可验证的准确率报告。

用法:
    python validate_pipeline.py                    # 打印报告
    python validate_pipeline.py --json ../evidence/day2/validation-report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_detect import detect as detect_anomalies  # noqa: E402
from fault_diagnose import diagnose  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="智维运维流水线验证")
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args()

    data_dir = Path(args.data)
    manifest = json.loads((data_dir / "scenarios.json").read_text(encoding="utf-8"))

    rows = []
    passed = 0
    for name, spec in manifest["scenarios"].items():
        path = data_dir / spec["file"]
        anomaly = detect_anomalies(path, 120.0, 61, 4.0, 5, 6.0)
        diag = diagnose(path, 120.0, 4.0)
        expected = spec.get("expected_fault")
        actual = diag["primary_diagnosis"]["fault"] if diag["primary_diagnosis"] else None
        if expected is None:
            ok = diag["status"] == "normal"
        else:
            ok = actual == expected
        passed += 1 if ok else 0
        rows.append({
            "scenario": name,
            "file": spec["file"],
            "expected_fault": expected,
            "detected_status": anomaly["summary"]["status"],
            "severity": anomaly["summary"]["severity"],
            "diagnosed_fault": actual,
            "confidence": diag["primary_diagnosis"]["confidence"] if diag["primary_diagnosis"] else None,
            "health_index": diag["health_index"],
            "correct": ok,
        })

    total = len(rows)
    report = {
        "tool": "validate_pipeline",
        "asset": manifest["asset"],
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 3) if total else 0.0,
        "results": rows,
    }

    header = f"{'场景':<16}{'期望':<14}{'诊断':<14}{'置信度':<8}{'健康度':<8}{'结果'}"
    print(header)
    print("-" * 78)
    for r in rows:
        print(f"{r['scenario']:<16}{str(r['expected_fault'] or 'normal'):<14}"
              f"{str(r['diagnosed_fault'] or 'normal'):<14}"
              f"{str(r['confidence'] if r['confidence'] is not None else '-'):<8}"
              f"{r['health_index']:<8}{'PASS' if r['correct'] else 'FAIL'}")
    print("-" * 78)
    print(f"准确率: {passed}/{total} = {report['accuracy'] * 100:.1f}%")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入: {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())