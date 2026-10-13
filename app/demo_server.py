#!/usr/bin/env python3
"""智维交互式演示后端（最终版）.

网页上选择设备/上传 CSV，点击「开始智能诊断」后：
  阶段一：用智维工具链实时计算（读数、趋势、异常、诊断、维修方案、模拟维修、验证）
  阶段二：真实启动 Agnes Harness（AGH）Agent 执行同一闭环，逐条推送工具调用到时间线

只依赖 Python 标准库 + 本项目的 tools/。要求 AGH 守护进程已在运行。

启动:
    python demo_server.py --port 8801
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOLS = ROOT / "tools"
UPLOAD_DIR = ROOT / "data" / "uploads"
sys.path.insert(0, str(TOOLS))

from anomaly_detect import SENSOR_LABELS, SENSOR_UNITS, detect, read_series  # noqa: E402
from fault_diagnose import diagnose  # noqa: E402
from repair_plan import build_plan  # noqa: E402
from simulate_repair import DEFAULT_OUT_DIR, simulate  # noqa: E402
from verify_repair import verify  # noqa: E402

def _find_agh_home() -> Path:
    """定位 Agnes Harness 源码目录：环境变量优先，否则在常见位置自动探测。"""
    env = os.environ.get("ZHIWEI_AGH_HOME")
    if env:
        return Path(env)
    candidates = [ROOT.parent / "agnes-harness", ROOT / "agnes-harness",
                  Path.home() / "agnes-harness", Path.home() / "Documents" / "agnes-harness"]
    for c in candidates:
        if (c / "packages" / "cli" / "dist" / "local" / "agnes.mjs").exists():
            return c
    return candidates[0]


AGH_HOME = _find_agh_home()
AGH_ENTRY = AGH_HOME / "packages" / "cli" / "dist" / "local" / "agnes.mjs"
AGH_PROFILE = os.environ.get("ZHIWEI_AGH_PROFILE", "local-dev")
SEED = 20261010

TASK_TEXT = "检查这台电机是否存在异常。如果存在，请诊断故障、制定维修方案，并验证维修结果。"

DEVICES = [
    {"id": "M-001", "name": "M-001 · 离心泵机组（过载工况）", "sample": "sensor_overload.csv"},
    {"id": "M-002", "name": "M-002 · 离心泵机组（早期轻微磨损）", "sample": "sensor_boundary_bearing_early.csv"},
    {"id": "M-003", "name": "M-003 · 离心泵机组（正常）", "sample": "sensor_normal.csv"},
    {"id": "M-004", "name": "M-004 · 离心泵机组（轴承磨损）", "sample": "sensor_bearing_wear.csv"},
    {"id": "M-005", "name": "M-005 · 离心泵机组（气蚀）", "sample": "sensor_cavitation.csv"},
    {"id": "T-01", "name": "T-01 · 测试文件：正常设备", "sample": "test/test_01_normal.csv", "pair": ""},
    {"id": "T-02", "name": "T-02 · 测试文件：模拟轴承异常（维修前）",
     "sample": "test/test_02_bearing_fault.csv", "pair": ""},
    {"id": "T-03", "name": "T-03 · 测试文件：模拟维修失败（维修后复测）",
     "sample": "test/test_03_repair_failed.csv", "pair": "test/test_02_bearing_fault.csv"},
]

PLANNED_STEPS = [
    {"id": "plan", "name": "规划", "tool": "zhiwei-closed-loop skill"},
    {"id": "read", "name": "读取", "tool": "read_sensor_summary"},
    {"id": "detect", "name": "检测", "tool": "detect_anomalies"},
    {"id": "diagnose", "name": "诊断", "tool": "diagnose_fault"},
    {"id": "repair", "name": "执行", "tool": "simulate_repair"},
    {"id": "verify", "name": "验证", "tool": "verify_repair"},
]

TOOL_TO_STEP = {
    "read_sensor_summary": "read", "detect_anomalies": "detect", "diagnose_fault": "diagnose",
    "plan_repair": "diagnose", "simulate_repair": "repair", "verify_repair": "verify",
}
TOOL_RE = re.compile(r"mcp_[a-z_]+_[0-9a-f]{6,}_([a-z_]+)")

# 反问式结尾（模型有时会主动征求确认）——不进入结论与时间线
ASKBACK_MARKERS = (
    "如果你知道该文件实际应有异常",
    "我可以按你指定目标继续执行",
    "请告诉我",
    "需要我继续",
    "如需我继续",
    "你希望我",
)


def is_askback(text: str) -> bool:
    return any(marker in text for marker in ASKBACK_MARKERS)
OK_RE = re.compile(r"·\s*ok\b")
FAIL_RE = re.compile(r"·\s*(failed|error|denied|rejected)\b", re.IGNORECASE)

_jobs: dict[str, dict] = {}


DEFAULT_TASK = ("检查这台电机是否存在异常。如果存在，请诊断故障、制定维修方案，并验证维修结果。")


def build_prompt(file_name: str, baseline_name: str | None = None,
                 task: str | None = None) -> str:
    tail = ("请直接给出最终结论，不要向用户反问、不要征求确认、"
            "不要给出『我可以按你指定目标继续执行』之类的后续选项。")
    head = (task or "").strip() or DEFAULT_TASK
    if baseline_name:
        return (f"{head}\n"
                f"数据说明：data/uploads/{file_name} 是【维修后复测】数据，"
                f"维修前数据是 data/uploads/{baseline_name}。"
                f"请以维修前数据为基线做异常检测与故障诊断，判断这次维修是否成功；"
                f"如果未通过验证，请重新规划维修并再次模拟维修与验证。"
                f"要求使用 zhiwei-closed-loop skill 的完整闭环流程。" + tail)
    return (f"{head}\n"
            f"数据文件：data/uploads/{file_name}。"
            f"要求使用 zhiwei-closed-loop skill 的完整闭环流程。" + tail)


def resolve_node() -> str:
    found = shutil.which("node")
    if found:
        return found
    fallback = r"C:\Program Files\nodejs\node.exe"
    return fallback if Path(fallback).exists() else "node"


def _trend(timestamps: list[str], series: dict, limit: int = 120) -> dict:
    keys = [k for k in ("temperature_c", "vibration_mm_s") if k in series]
    n = len(timestamps)
    step = max(1, n // limit)
    idx = list(range(0, n, step))
    return {
        "labels": [timestamps[i][11:19] if len(timestamps[i]) > 11 else str(i) for i in idx],
        "series": [
            {"key": k, "label": SENSOR_LABELS.get(k, k), "unit": SENSOR_UNITS.get(k, ""),
             "values": [round(float(series[k][i]), 3) for i in idx]}
            for k in keys
        ],
    }


def run_job(job_id: str, csv_path: Path, baseline_path: Path | None = None,
            task: str | None = None) -> None:
    job = _jobs[job_id]
    lock = job["lock"]

    def emit(kind: str, **payload) -> None:
        with lock:
            job["events"].append({"type": kind, "at": time.time(), **payload})

    emit("status", text="Agent 已接收任务，正在规划执行步骤…")
    emit("plan_steps", steps=PLANNED_STEPS)
    time.sleep(0.5)
    emit("phase", text="工具链实时计算", phase=1)

    # ---------- 阶段一：智维工具链实时计算 ----------
    try:
        timestamps, series = read_series(csv_path)
        latest = {}
        for key, values in series.items():
            clean = [v for v in values if v == v]
            if clean:
                latest[key] = {"label": SENSOR_LABELS.get(key, key), "unit": SENSOR_UNITS.get(key, ""),
                               "value": round(clean[-1], 3), "samples": len(clean),
                               "min": round(min(clean), 3), "max": round(max(clean), 3),
                               "avg": round(statistics.fmean(clean), 3)}
        emit("sensors", latest=latest, samples=len(timestamps),
             window={"from": timestamps[0], "to": timestamps[-1]} if timestamps else {})
        emit("trend", **_trend(timestamps, series))
        time.sleep(0.35)

        anomaly = detect(csv_path, 120.0, 61, 4.0, 5, 6.0, baseline_path)
        emit("detect", status=anomaly["summary"]["status"], severity=anomaly["summary"]["severity"],
             conclusion=anomaly["summary"]["conclusion"],
             max_abs_shift_z=anomaly["summary"]["max_abs_shift_z"],
             affected=anomaly["summary"]["affected_detail"])
        time.sleep(0.35)

        diag = diagnose(csv_path, 120.0, 4.0, baseline_path)
        emit("diagnosis", status=diag["status"], verdict=diag["verdict"],
             health_index=diag["health_index"],
             primary=diag.get("primary_diagnosis"), candidates=diag.get("candidates", [])[:4],
             differential=diag.get("differential"))
        time.sleep(0.35)

        if diag["status"] == "normal" or not diag.get("primary_diagnosis"):
            emit("repair_plan", skipped=True, verdict="设备健康，无需维修")
            emit("repair", skipped=True)
            emit("verify", status="success", verdict="设备健康，未触发维修",
                 health={"before": diag["health_index"], "after": diag["health_index"]},
                 before_shifts={}, after_shifts={}, comparison=[])
        else:
            plan = build_plan(csv_path, 120.0, 4.0, baseline_path)
            emit("repair_plan", skipped=False, fault=plan["fault"], verdict=plan["verdict"],
                 downtime=plan["downtime"], downtime_label=plan["downtime_label"],
                 estimated_hours=plan["estimated_hours"], steps=plan["steps"],
                 parts=plan["parts"], safety=plan["safety"])
            time.sleep(0.35)

            fault = plan["fault"]
            if baseline_path is not None:
                # 上传的是"上次维修后的复测数据"，完整走一遍：
                #   ① 先判定"上次维修"结果 -> ② 诊断残留 -> ③ 再次维修方案（已在上方 emit）
                #   -> ④ 执行"再次维修" -> ⑤ 验证"再次维修"结果
                prior = verify(baseline_path, csv_path, 120.0, 4.0)
                emit("prior_verify", status=prior["status"], verdict=prior["verdict"],
                     worst_residual_sigma=prior["worst_residual_sigma"],
                     health={"before": prior["before"]["health_index"],
                             "after": prior["health_index"]},
                     before_shifts=prior["before_shifts_sigma"],
                     after_shifts=prior["residual_shifts_sigma"])
                time.sleep(0.35)
                sim = simulate(csv_path, 1.0, fault, 2, SEED + 2, DEFAULT_OUT_DIR, None,
                              fault, baseline_path)
                emit("repair", skipped=False, csv=Path(sim["output_csv"]).name,
                     effectiveness=1.0, attempt=2, residual_offset=sim["residual_offset"])
                # 再次维修后，仍以"真实健康基线"为标准比较
                ver = verify(baseline_path, Path(sim["output_csv"]), 120.0, 4.0)
            else:
                sim = simulate(csv_path, 1.0, fault, 1, SEED + 1, DEFAULT_OUT_DIR, None, fault)
                emit("repair", skipped=False, csv=Path(sim["output_csv"]).name,
                     effectiveness=1.0, residual_offset=sim["residual_offset"])
                ver = verify(csv_path, Path(sim["output_csv"]), 120.0, 4.0)
            emit("verify", status=ver["status"], verdict=ver["verdict"],
                 health={"before": ver["before"]["health_index"], "after": ver["health_index"]},
                 worst_residual_sigma=ver["worst_residual_sigma"],
                 before_shifts=ver["before_shifts_sigma"],
                 after_shifts=ver["residual_shifts_sigma"],
                 comparison=ver["comparison"], residual_fault=ver["residual_fault"],
                 next_step=ver["next_step"])
    except Exception as exc:  # noqa: BLE001
        emit("error", text=f"工具链计算出错：{exc}")

    # ---------- 阶段二：真实 AGH Agent ----------
    emit("phase", text="Agnes Agent 在 AGH 中执行", phase=2)
    if not AGH_ENTRY.exists():
        emit("error", text=f"找不到 AGH 入口：{AGH_ENTRY}")
        emit("done", ok=False)
        return

    env = os.environ.copy()
    env["AGNES_PROFILE"] = AGH_PROFILE
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(key, None)
    env["NO_PROXY"] = "*"
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [resolve_node(), str(AGH_ENTRY), "-p", "--cwd", str(ROOT),
           build_prompt(csv_path.name, baseline_path.name if baseline_path else None, task)]
    emit("log", text=f"启动 Agent：agnes -p --cwd {ROOT}")
    try:
        proc = subprocess.Popen(cmd, cwd=str(AGH_HOME), env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", bufsize=1)
    except Exception as exc:  # noqa: BLE001
        emit("error", text=f"启动 Agent 失败：{exc}")
        emit("done", ok=False)
        return

    emit("tool", tool="zhiwei-closed-loop", status="running")
    answer_lines: list[str] = []
    for raw in proc.stdout or []:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        m = TOOL_RE.search(line)
        if m:
            tool = m.group(1)
            step = TOOL_TO_STEP.get(tool)
            if FAIL_RE.search(line):
                emit("tool", tool=tool, step=step, status="failed", text=line.strip())
            elif OK_RE.search(line):
                emit("tool", tool=tool, step=step, status="ok", text=line.strip())
            else:
                emit("tool", tool=tool, step=step, status="running", text=line.strip())
            continue
        text = line.strip()
        if is_askback(text):
            continue
        answer_lines.append(text)
        emit("log", text=text)

    proc.wait()
    emit("answer", text="\n".join(answer_lines).strip())
    emit("tool", tool="zhiwei-closed-loop", status="ok" if proc.returncode == 0 else "failed")
    emit("done", ok=proc.returncode == 0)


class Handler(BaseHTTPRequestHandler):
    server_version = "ZhiWeiDemo/2.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict):
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._json(200, {"ok": True, "aghEntry": str(AGH_ENTRY), "aghFound": AGH_ENTRY.exists(),
                             "profile": AGH_PROFILE, "root": str(ROOT), "task": TASK_TEXT})
            return

        if path == "/api/devices":
            self._json(200, {"devices": DEVICES, "task": TASK_TEXT})
            return

        if path == "/api/sample":
            qs = parse_qs(parsed.query)
            raw = (qs.get("name") or ["sensor_overload.csv"])[0]
            data_root = (ROOT / "data").resolve()
            target = (data_root / raw).resolve()
            if (not target.exists() or target.is_dir()
                    or not str(target).startswith(str(data_root))):
                self._json(404, {"error": "示例数据不存在"})
                return
            self._send(200, target.read_bytes(), "text/csv; charset=utf-8")
            return

        if path == "/api/run":
            qs = parse_qs(parsed.query)
            file_name = Path((qs.get("file") or [""])[0]).name
            csv_path = UPLOAD_DIR / file_name
            if not file_name or not csv_path.exists():
                self._json(404, {"error": "数据文件不存在"})
                return
            base_name = Path((qs.get("baseline") or [""])[0]).name
            baseline_path = (UPLOAD_DIR / base_name) if base_name else None
            if baseline_path is not None and not baseline_path.exists():
                baseline_path = None
            task = (qs.get("task") or [""])[0]
            job_id = uuid.uuid4().hex
            _jobs[job_id] = {"events": [], "lock": threading.Lock()}
            threading.Thread(target=run_job,
                             args=(job_id, csv_path, baseline_path, task),
                             daemon=True).start()
            self._serve_events(job_id)
            return

        rel = "zhiwei-live.html" if path in ("/", "") else path.lstrip("/")
        target = (HERE / rel).resolve()
        if not str(target).startswith(str(HERE)) or not target.exists():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8"}.get(target.suffix,
                                                                      "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def _serve_events(self, job_id: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        sent = 0
        while True:
            job = _jobs.get(job_id)
            if job is None:
                break
            with job["lock"]:
                pending = job["events"][sent:]
                sent += len(pending)
            for event in pending:
                try:
                    self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:  # noqa: BLE001
                    return
            if pending and pending[-1]["type"] == "done":
                break
            time.sleep(0.25)

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path != "/api/upload":
            self._json(404, {"error": "unknown endpoint"})
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._json(400, {"error": "请求体必须是 JSON"})
            return
        name = Path(str(payload.get("name") or "motor_data.csv")).name
        csv_text = str(payload.get("csv") or "")
        if not csv_text.strip():
            self._json(400, {"error": "数据为空"})
            return
        if not name.lower().endswith(".csv"):
            name += ".csv"
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        safe = f"{Path(name).stem}_{time.strftime('%Y%m%d-%H%M%S')}.csv"
        (UPLOAD_DIR / safe).write_text(csv_text, encoding="utf-8")
        self._json(200, {"file": safe, "rows": max(0, len(csv_text.strip().splitlines()) - 1)})


def main() -> int:
    parser = argparse.ArgumentParser(description="智维交互式演示服务")
    parser.add_argument("--port", type=int, default=8801)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    if not AGH_ENTRY.exists():
        print(f"[warn] 未找到 AGH 入口：{AGH_ENTRY}", file=sys.stderr)
    print(f"智维演示服务已启动： http://{args.host}:{args.port}/")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())