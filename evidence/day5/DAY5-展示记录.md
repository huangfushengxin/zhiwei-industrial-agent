# Day 5 记录 —— 展示（网页 + 三案例 + 演示材料）

日期：2026-10-10

## 一、Day 5 目标与完成情况

| # | 任务 | 状态 |
|---|---|---|
| 1 | 做简单网页 | 完成 `app/zhiwei-demo.html` |
| 2 | 展示 Agent 执行时间线 | 完成（每案例的 trace 逐步渲染） |
| 3 | 准备正常 / 边界 / 失败三个测试案例 | 完成，3/3 通过 |
| 4 | 保存 AGH 工具调用链和执行记录 | 完成（会话导出 HTML + JSON） |
| 5 | 制作 3–5 分钟演示视频 | 提供分镜脚本 `演示视频脚本.md`（录制由团队完成） |

## 二、展示网页

`app/zhiwei-demo.html` —— **自包含单文件**（数据内嵌，双击即可打开，无需服务器）。

页面包含：
- 顶部：项目名、被监测设备、执行底座（AGH）、模型（Agnes 3.0 Flash）、生成时间
- 统计卡：三个案例的状态、维修次数、健康度变化
- 每个案例一张卡片：目标说明、数据集、严重等级徽标、**健康度进度条**、
  **Agent 执行时间线**（每步带状态色：绿=通过、黄=警告、红=失败、青=信息）、结论与说明
- 底部：六步闭环流程条

生成方式：`python tools/build_demo_page.py`（数据来自 `evidence/day5/demo-cases.json`）。

## 三、三个测试案例

由 `tools/run_demo_cases.py` 一次性跑出并写入 `evidence/day5/demo-cases.json`：

| 案例 | 数据集 | 等级 | 状态 | 健康度 | 证明的能力 |
|---|---|---|---|---|---|
| A 正常 | `sensor_normal.csv` | normal | healthy（0 次维修） | 100→100 | 不误报、不触发维修 |
| B 边界 | `sensor_boundary_bearing_early.csv` | **warning** | repaired（1 次） | 60→100 | 早期弱信号（5.06σ 刚越阈值）也能检出并处置 |
| C 失败 | `sensor_overload.csv` | critical | **recovered**（2 次） | 20→50→100 | 错误诊断 → 验证失败 → 重新规划 → 维修成功 |

**边界案例**是本次新增：`tools/make_boundary_case.py` 生成"早期轻微轴承磨损"
（幅度约满强度 25%），实测 severity = warning、max shift 5.06σ、诊断置信度 0.982——
正好卡在检测阈值之上，是真正意义上的边界工况。

**失败案例**复用 Day 4 的错误诊断流程：第 1 次按错误目标维修 → verify 未通过（残留 28.52σ）
→ Agent 依残留测点纠正诊断 → 第 2 次维修通过（残留 1.28σ）。

## 四、AGH 执行记录

会话：`agnes:local:local-dev:cli:workspace:b1091fd773a74edb`（cwd = 提交包根目录）
导出：`agh-day5-three-cases.{html,json}`（本次导出共 409 条事件，seq 1→409）

三个案例**全部由 Agent 在 AGH 中真实调用 MCP 工具完成**。导出记录中的工具引用次数：

| 工具 | 引用次数 |
|---|---|
| `verify_repair` | 56 |
| `simulate_repair` | 47 |
| `run_closed_loop` | 26 |
| `diagnose_fault` | 23 |
| `detect_anomalies` | 19 |
| `plan_repair` | 9 |
| `read_sensor_summary` | 2 |
| `list_scenarios` | 2 |

Agent 给出的三个案例结论（与 `evidence/day5/demo-cases.json`、展示页完全一致）：

| 案例 | Agent 报告的关键结果 |
|---|---|
| ① 正常设备 | `detect_anomalies → normal` 后直接短路，`attempts = []`，不写盘，健康度 100 |
| ② 边界工况 | severity `warning`、`max_abs_shift_z = 5.06`；诊断 `bearing_wear` 置信度 **0.982**；1 次维修 + 验证通过，最大残留 1.64σ；健康度 60 → 100 |
| ③ 失败→纠错 | 主判 `overload` 置信度 **0.936**；第 1 次按误用的次选 `bearing_wear` 维修 → `verify_repair = failed`（最大残留 **28.52σ**，健康度 20 → 50）；重规划后按主判 `overload` 复修 → `success`（最大残留 **1.28σ**，健康度 50 → 100） |

> 说明：该会话同时包含 Day 4 的"异常恢复"演示轮次与 Day 5 的三案例验收轮次，
> 两次运行的数据与结论互相印证。
## 五、演示视频

脚本见 `演示视频脚本.md`（分镜、旁白、录制检查清单），时长 3–5 分钟。
核心叙事：问题 → 架构 → 正常/边界 → **失败与恢复（重点）** → 工程亮点 → 收尾。

## 六、全部验收（Day 2–5 汇总）

| 验收项 | 结果 |
|---|---|
| 故障诊断准确率 | 5/5 = 100% |
| 闭环（含失败重规划） | 6/6 = 100% |
| 异常恢复（错误诊断→纠正） | 4/4 = 100% |
| 三测试案例（正常/边界/失败） | 3/3 = 100% |
| MCP 工具 | 9 个全部可调用 |

## 七、已知边界与后续

- 传感器数据为机理化仿真，尚未接入真实设备/PLC；
- `typical_delta` 需要用真实维修案例标定；
- 展示页为静态生成（每次运行案例后重新构建即可）；
- 可选增强：趋势监测（把早期 confidence 作为检修阈值输入）、电流-转速联动告警。
---

## 八、交互式在线诊断演示（新增）

### 8.1 是什么

`app/zhiwei-live.html` + `app/demo_server.py`：在网页上**粘贴/上传一份电机运行数据**，
点「开始」，页面会实时显示：

1. **Agent 已接收任务，正在规划执行步骤…**
2. 六步执行计划（读取数据 / 异常检测 / 故障诊断 / 制定维修方案 / 模拟维修 / 验证维修结果），
   每一步随真实工具调用依次点亮：灰=待执行、青=进行中、绿=完成、红=失败
3. 实时工具调用日志（含每次调用耗时）
4. 最终结论（健康度、故障、维修动作、验证结果）

任务文案固定为：**「检查这台电机是否存在异常。如果存在，请诊断故障、制定维修方案，并验证维修结果。」**

### 8.2 关键：这是"真跑"不是动画

页面点「开始」后，后端会：

1. 把数据写入 `data/uploads/<name>_<时间戳>.csv`
2. 用 `node agnes.mjs -p --cwd zhiwei "<任务>"` **真实启动 Agnes Harness Agent**
3. 实时解析 Agent 输出的 `- tool mcp_zhiwei_ops_*_<工具> · ok · <耗时>` 行，按 SSE 推给网页
4. Agent 完成后推送完整结论

也就是说：**真实模型 + 真实 MCP 工具调用 + 真实数据验证**，页面只是把过程可视化。

### 8.3 实测（真实上传 600 行数据跑通）

    upload   -> demo_motor_20261009-144625.csv（600 行）
    status   -> Agent 已接收任务，正在规划执行步骤…
    plan     -> 读取数据、异常检测、故障诊断、制定维修方案、模拟维修、验证维修结果
    tool     -> read_sensor_summary   ok  96ms
    tool     -> detect_anomalies      ok 140ms
    tool     -> diagnose_fault        ok 154ms
    tool     -> plan_repair           ok 150ms
    tool     -> simulate_repair       ok 100ms
    tool     -> verify_repair         ok 556ms
    answer   -> 健康度 20 → 100，overload（0.933），验证 success

### 8.4 启动方式

    # 前提：AGH 服务已在运行（另一个窗口）
    cd app
    .\start_demo.ps1          # 或 python demo_server.py --port 8801
    # 浏览器打开 http://127.0.0.1:8801/

页面内置三个快捷载入按钮：过载电机 / 边界数据（早期轻微故障）/ 正常数据，也支持选择本地 CSV 或直接粘贴。

### 8.5 文件

| 文件 | 说明 |
|---|---|
| `app/zhiwei-live.html` | 交互式在线诊断页面 |
| `app/demo_server.py` | 本地演示服务（Python 标准库，无第三方依赖） |
| `app/start_demo.ps1` | 一键启动脚本 |
| `app/zhiwei-demo.html` | 三案例结果展示页（静态、自包含，用于视频与答辩） |
---

## 九、最终页面版式（按需求定稿）

页面按指定的最终版式重做，采用「顶部状态栏 + 设备选择栏 + 左右双栏 + 时间线 + 验证结果」结构：

    智维 AI Industrial Operations Agent        [Agnes Status ● ] [AGH Runtime ● ] [MCP Tools]
    ────────────────────────────────────────────────────────────────────────────────
    设备选择与数据上传     [M-001 ▼] [上传 CSV] [开始智能诊断]
    ────────────────────────────────────────────────────────────────────────────────
    设备实时数据                     │ AI 故障诊断
      温度 74.97℃ / 振动 4.58        │   可能故障：负载过大 / 转动部件卡涩（0.933）
      转速 2901rpm / 电流 58.25A     │   判断依据：电流 +36.72σ ↑、温度 +32.99σ ↑ …
      温度/振动趋势图（SVG 双曲线）    │   维修建议 + 维修方案（6 道工序 / 备件）
    ────────────────────────────────────────────────────────────────────────────────
    Agent 执行时间线   规划 → 读取 → 检测 → 诊断 → 执行 → 验证
    ────────────────────────────────────────────────────────────────────────────────
    维修验证结果       维修前数据 | 维修后数据 | 验证状态

### 数据来源（重要，避免误解）

- **左侧读数/趋势**、**右侧诊断与方案**、**维修验证结果**：由演示服务调用**智维工具链**
  （`anomaly_detect` / `fault_diagnose` / `repair_plan` / `simulate_repair` / `verify_repair`）
  实时计算得出——与 Agent 调用的是**同一套工具**，数据同源。
- **执行时间线上的每一步**：来自**真实 Agnes Agent** 在 AGH 中的运行日志
  （页面通过 SSE 实时解析 `- tool mcp_zhiwei_ops_* · ok · <耗时>`）。

### 设备下拉

| 设备 | 数据集 | 工况 |
|---|---|---|
| M-001 | `sensor_overload.csv` | 过载（critical） |
| M-002 | `sensor_boundary_bearing_early.csv` | 早期轻微磨损（warning 边界） |
| M-003 | `sensor_normal.csv` | 正常 |
| M-004 | `sensor_bearing_wear.csv` | 轴承磨损 |
| M-005 | `sensor_cavitation.csv` | 气蚀 |

### 实测（最终版页面）

    UPLOAD  M-001_20261009-150147.csv（600 行）
    SENSORS 温度 74.97℃ / 振动 4.58 / 转速 2901 / 电流 58.25A
    TREND   温度+振动 双曲线，120 个采样点
    DETECT  critical · 4 个测点持续偏移
    DIAG    负载过大 / 转动部件卡涩 · 置信度 0.933
    PLAN    先在线降载排查，必要时停机 · 3.0 小时 · 6 道工序
    REPAIR  M-001_20261009-150147_repair_e1.00_a1.csv
    VERIFY  success · 最大残留 1.4σ
    DONE    ok = True