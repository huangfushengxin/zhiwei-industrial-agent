#!/usr/bin/env python3
"""智维 (ZhiWei) 工业设备智能运维 MCP 工具服务.

通过 MCP (Model Context Protocol) 把工业设备运维能力暴露给
Agnes Harness (AGH) 智能体，使 Agent 能够真正"调用工具"而不是只做文本回答。

暴露的工具：
  - list_scenarios        列出可用的设备工况数据集
  - read_sensor_summary   读取并汇总某个数据集的传感器统计
  - detect_anomalies      异常检测（滚动基线 + 鲁棒 z 分数）
  - diagnose_fault        故障诊断（特征匹配 + 维修建议）
  - analyze_equipment     一次性完成异常检测 + 故障诊断

启动方式（stdio）:
    python zhiwei_mcp_server.py
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

def _find_project_root(start: Path) -> Path:
    """向上查找包含 data/scenarios.json 的项目根目录，使服务移动到别处也能工作。"""
    for candidate in (start, *start.parents):
        if (candidate / "data" / "scenarios.json").is_file():
            return candidate
    return start.parents[1] if len(start.parents) > 1 else start


ROOT = _find_project_root(Path(__file__).resolve().parent)
TOOLS_DIR = ROOT / "tools"
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(TOOLS_DIR))

from anomaly_detect import SENSOR_LABELS, detect as detect_anomalies_impl  # noqa: E402
from fault_diagnose import diagnose as diagnose_impl  # noqa: E402
from repair_plan import build_plan as build_repair_plan  # noqa: E402
from simulate_repair import DEFAULT_OUT_DIR as REPAIR_OUT_DIR  # noqa: E402
from simulate_repair import simulate as simulate_repair_impl  # noqa: E402
from verify_repair import verify as verify_repair_impl  # noqa: E402
from closed_loop import run as closed_loop_run  # noqa: E402

# 这些工具只读取/分析数据，不修改文件、不访问外部网络 -> 声明为只读，避免触发写入类审批
READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# 会写盘的工具：只新增文件（维修后数据与闭环记录），不删除或覆盖既有数据 -> 写但非破坏性
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

server = MCPServer(
    name="zhiwei-industrial-ops",
    title="智维 · 工业设备智能运维工具",
    instructions=(
        "面向工业旋转设备（离心泵机组）的运维工具集。"
        "典型闭环：detect_anomalies 判异常 -> diagnose_fault 定故障 -> plan_repair 出维修方案 -> "
        "simulate_repair 模拟维修 -> verify_repair 用数据验证；失败则重规划。"
        "run_closed_loop 可一键跑完整闭环。"
    ),
    version="0.3.0",
)


def _resolve(csv_path: str) -> Path:
    """允许传绝对路径、相对项目根路径，或只传数据文件名。"""
    candidate = Path(csv_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    for base in (ROOT, DATA_DIR, DATA_DIR / "repairs", TOOLS_DIR, Path.cwd()):
        probe = base / csv_path
        if probe.exists():
            return probe.resolve()
    raise FileNotFoundError(f"找不到数据文件: {csv_path}")


def _json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


@server.tool(
    name="list_scenarios",
    annotations=READONLY,
    description="列出当前可用的工业设备工况数据集（正常 + 各类故障场景）及其故障说明。",
)
def list_scenarios() -> str:
    manifest_path = DATA_DIR / "scenarios.json"
    if not manifest_path.exists():
        return _json({"error": "scenarios.json 不存在，请先运行 tools/generate_sensor_data.py"})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = [
        {
            "scenario": key,
            "file": value["file"],
            "description": value["description"],
            "expected_fault": value.get("expected_fault"),
            "rows": value.get("rows"),
        }
        for key, value in manifest["scenarios"].items()
    ]
    return _json({"asset": manifest["asset"], "count": len(scenarios), "scenarios": scenarios})


@server.tool(
    name="read_sensor_summary",
    annotations=READONLY,
    description="读取指定传感器数据集，返回每个测点的统计摘要（均值/最小/最大/末值），用于快速了解设备当前状态。",
)
def read_sensor_summary(csv_path: str) -> str:
    path = _resolve(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = [c for c in (reader.fieldnames or []) if c and c != "timestamp"]
        buckets: dict[str, list[float]] = {c: [] for c in columns}
        first_ts = last_ts = ""
        for row in reader:
            first_ts = first_ts or str(row.get("timestamp", ""))
            last_ts = str(row.get("timestamp", ""))
            for c in columns:
                try:
                    buckets[c].append(float(row.get(c)))
                except (TypeError, ValueError):
                    pass

    summary = []
    for name, values in buckets.items():
        if not values:
            continue
        summary.append({
            "sensor": name,
            "label": SENSOR_LABELS.get(name, name),
            "mean": round(statistics.fmean(values), 3),
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "first": round(values[0], 3),
            "last": round(values[-1], 3),
            "samples": len(values),
        })
    return _json({"file": path.name, "window": {"from": first_ts, "to": last_ts}, "sensors": summary})


@server.tool(
    name="detect_anomalies",
    annotations=READONLY,
    description=(
        "对传感器数据进行异常检测：以数据前段为基线，用滚动中位数吸收周期性工况波动，"
        "检测『持续偏移』与『瞬时尖峰』，返回异常测点、时间区间、偏移倍率与严重等级。"
    ),
)
def detect_anomalies(csv_path: str, baseline_s: float = 120.0, z_threshold: float = 4.0) -> str:
    path = _resolve(csv_path)
    report = detect_anomalies_impl(path, baseline_s, 61, z_threshold, 5, 6.0)
    summary = report["summary"]
    compact = {
        "tool": "detect_anomalies",
        "file": report["file"],
        "status": summary["status"],
        "severity": summary["severity"],
        "conclusion": summary["conclusion"],
        "max_abs_shift_z": summary["max_abs_shift_z"],
        "affected_detail": summary["affected_detail"],
        "sensors": report["sensors"],
        "anomaly_samples": report["anomalies"][:20],
        "spike_count": summary["transient_spike_points"],
    }
    return _json(compact)


@server.tool(
    name="diagnose_fault",
    annotations=READONLY,
    description=(
        "基于异常特征做故障诊断：把各测点的持续偏移方向与强度，与故障特征库匹配，"
        "输出排序后的故障候选、置信度、判据证据与推荐维修动作。"
    ),
)
def diagnose_fault(csv_path: str, baseline_s: float = 120.0, z_threshold: float = 4.0) -> str:
    path = _resolve(csv_path)
    report = diagnose_impl(path, baseline_s, z_threshold)
    report.pop("anomaly_summary", None)
    return _json(report)


@server.tool(
    name="analyze_equipment",
    annotations=READONLY,
    description="一键完成『异常检测 + 故障诊断』，返回设备健康度、是否异常、故障结论与维修建议。适合作为运维分析的主入口。",
)
def analyze_equipment(csv_path: str) -> str:
    path = _resolve(csv_path)
    anomaly = detect_anomalies_impl(path, 120.0, 61, 4.0, 5, 6.0)
    diagnosis = diagnose_impl(path, 120.0, 4.0)
    return _json({
        "tool": "analyze_equipment",
        "file": path.name,
        "asset": diagnosis["asset"],
        "status": diagnosis["status"],
        "health_index": diagnosis["health_index"],
        "verdict": diagnosis["verdict"],
        "anomaly": {
            "status": anomaly["summary"]["status"],
            "severity": anomaly["summary"]["severity"],
            "conclusion": anomaly["summary"]["conclusion"],
            "affected_detail": anomaly["summary"]["affected_detail"],
        },
        "diagnosis": {
            "primary": diagnosis["primary_diagnosis"],
            "differential": diagnosis["differential"],
            "observed_shifts_sigma": diagnosis["observed_shifts_sigma"],
        },
        "next_step": diagnosis["next_step"],
    })


@server.tool(
    name="plan_repair",
    annotations=READONLY,
    description=(
        "生成结构化维修方案：依据诊断结果给出是否停机、预计工时、安全措施、"
        "分步工序（含工具与验收标准）、备件清单与复检验收标准。"
    ),
)
def plan_repair(csv_path: str) -> str:
    path = _resolve(csv_path)
    report = build_repair_plan(path, 120.0, 4.0)
    report.pop("plan", None)
    return _json(report)


@server.tool(
    name="simulate_repair",
    annotations=WRITE,
    description=(
        "模拟执行维修并生成【维修后复测数据】CSV，写入 data/repairs/。"
        "effectiveness 表示修复彻底度：1.0=完全修复，0.7=部分修复（会留下残留故障）。"
        "repair_target 表示本次维修实际针对的故障：默认等于诊断结论；"
        "若填成另一个故障（例如把过载误判为轴承磨损），则该故障特征覆盖不到的测点不会被修复，"
        "维修后仍会残留异常 —— 用于演示『错误诊断 -> 验证失败 -> 重新规划』。"
    ),
)
def simulate_repair(csv_path: str, effectiveness: float = 1.0,
                    fault: str | None = None, attempt: int = 1,
                    repair_target: str | None = None) -> str:
    path = _resolve(csv_path)
    if fault is None:
        diag = diagnose_impl(path, 120.0, 4.0)
        primary = diag.get("primary_diagnosis")
        fault = primary["fault"] if primary else None
    report = simulate_repair_impl(path, effectiveness, fault, attempt, 20261009,
                                   REPAIR_OUT_DIR, None, repair_target)
    # 返回给 Agent 的路径用相对形式（不带本机绝对路径/用户名）；
    # _resolve 同样支持相对路径，因此 verify_repair 可以直接用它。
    if report.get("output_csv_rel"):
        report["output_csv"] = report.pop("output_csv_rel")
    return _json(report)


@server.tool(
    name="verify_repair",
    annotations=READONLY,
    description=(
        "验证维修结果：以【维修前数据的基线】为参照对比维修后复测数据，"
        "给出维修前后各测点偏移、改善率、残留偏移与 verdict（success / partial / failed），"
        "失败时给出残留故障候选与重新规划建议。"
    ),
)
def verify_repair(before_csv: str, after_csv: str) -> str:
    report = verify_repair_impl(_resolve(before_csv), _resolve(after_csv), 120.0, 4.0)
    return _json(report)


@server.tool(
    name="run_closed_loop",
    annotations=WRITE,
    description=(
        "一键跑完整闭环：数据读取 -> 异常检测 -> 故障诊断 -> 维修方案 -> 模拟维修 -> 维修后验证；"
        "验证失败会按 escalation 重新规划并再修（每次 +0.5，最多 max_attempts 次）。"
        "返回逐次 attempt、完整 trace（可作执行时间线）与最终结论。"
    ),
)
def run_closed_loop(csv_path: str, repair_effectiveness: float = 1.0,
                    max_attempts: int = 3) -> str:
    record = closed_loop_run(_resolve(csv_path), repair_effectiveness, max_attempts,
                             20261009, REPAIR_OUT_DIR)
    return _json(record)

def _selftest() -> int:
    print("== list_scenarios ==")
    print(list_scenarios()[:400])
    print("\n== analyze_equipment(bearing_wear) ==")
    print(analyze_equipment("sensor_bearing_wear.csv")[:1200])
    print("\n== analyze_equipment(normal) ==")
    print(analyze_equipment("sensor_normal.csv")[:600])
    print("\n== plan_repair(cavitation) ==")
    print(plan_repair("sensor_cavitation.csv")[:500])
    print("\n== run_closed_loop(overload, e=0.5) ==")
    print(run_closed_loop("sensor_overload.csv", 0.5, 3)[:800])
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(_selftest())
    server.run(transport="stdio")