#!/usr/bin/env python3
"""智维 (ZhiWei) 故障知识库.

集中维护每类故障的：
  - signature  特征指纹（测点权重 + 期望方向），供故障诊断做匹配
  - actions    简要维修动作
  - parts      涉及备件
  - plan       结构化维修方案（是否停机、工时、安全措施、分步工序、复检验收标准）

全项目共用此文件，避免知识分散在多处。只依赖 Python 标准库。
"""
from __future__ import annotations

# 故障特征库：signature[sensor] = (权重, 期望方向 +1 上升 / -1 下降)
FAULT_LIBRARY: dict[str, dict] = {
    "bearing_wear": {
        "typical_delta": {"temperature_c": 19.0, "vibration_mm_s": 6.4, "current_a": 3.2},
        "name": "轴承磨损（滚动体 / 滚道损伤）",
        "signature": {
            "vibration_mm_s": (1.00, +1),
            "temperature_c": (1.00, +1),
            "current_a": (0.25, +1),
        },
        "actions": [
            "停机后测量轴承径向游隙并与出厂值比对",
            "检查润滑脂状态（变色 / 乳化 / 铁屑）并按规程补脂或更换",
            "更换损伤轴承，复测安装同轴度",
        ],
        "parts": ["轴承", "润滑脂", "密封件"],
        "plan": {
            "downtime": "offline",
            "estimated_hours": 6.0,
            "safety": [
                "执行断电挂牌上锁（LOTO），确认电机不可启动",
                "关闭进出口阀门并泄压排空，确认泵体温度降至常温",
                "吊装轴承座时使用合格吊具，禁止手扶对位",
            ],
            "steps": [
                {"seq": 1, "action": "停机断电挂牌，关闭进出口阀门并泄压排空", "tool": "LOTO 锁具、阀门扳手", "acceptance": "电机断电挂牌、泵内无压无料"},
                {"seq": 2, "action": "拆除联轴器防护罩与轴承座端盖，记录垫片位置", "tool": "内六角扳手组、记号笔", "acceptance": "部件完好，垫片位置有记录"},
                {"seq": 3, "action": "测量轴承径向游隙与滚道表面状态", "tool": "塞尺 / 游隙测量仪、放大镜", "acceptance": "游隙实测值记录并与出厂值比对"},
                {"seq": 4, "action": "拆除损伤轴承，检查轴颈磨损与圆度", "tool": "拉马、千分尺", "acceptance": "轴颈尺寸在图纸公差内，超差需报修"},
                {"seq": 5, "action": "装新轴承并加注规定牌号润滑脂", "tool": "轴承加热器、注脂枪", "acceptance": "注脂量为轴承腔容积的 1/3 ~ 1/2"},
                {"seq": 6, "action": "复装端盖与防护罩，手动盘车检查", "tool": "扭矩扳手", "acceptance": "盘车顺畅无卡涩，紧固力矩达标"},
                {"seq": 7, "action": "试运行并复测振动与温度", "tool": "测振仪、红外测温仪", "acceptance": "振动与温度回到基线 +4σ 以内"},
            ],
            "verification": [
                {"sensor": "vibration_mm_s", "criterion": "尾部偏移 |z| < 4σ，回到基线水平"},
                {"sensor": "temperature_c", "criterion": "尾部偏移 |z| < 4σ，回到基线水平"},
                {"sensor": "current_a", "criterion": "电流无明显持续抬升"},
            ],
        },
    },
    "misalignment": {
        "typical_delta": {"vibration_mm_s": 9.2, "temperature_c": 7.0, "current_a": 4.0},
        "name": "联轴器不对中 / 转子不平衡",
        "signature": {
            "vibration_mm_s": (1.00, +1),
            "temperature_c": (0.30, +1),
            "current_a": (0.20, +1),
        },
        "actions": [
            "用激光对中仪复测电机与泵的同轴度",
            "检查联轴器弹性块磨损与地脚螺栓紧固力矩",
            "必要时做转子动平衡",
        ],
        "parts": ["联轴器弹性块", "地脚螺栓", "平衡块"],
        "plan": {
            "downtime": "offline",
            "estimated_hours": 4.0,
            "safety": [
                "执行断电挂牌上锁（LOTO），防止联轴器意外转动",
                "拆除防护罩前确认设备完全静止",
                "工具与垫片系防坠绳，避免落入运转腔体",
            ],
            "steps": [
                {"seq": 1, "action": "停机断电挂牌，拆除联轴器防护罩", "tool": "LOTO 锁具、内六角扳手组", "acceptance": "设备完全静止，防护罩完好拆除"},
                {"seq": 2, "action": "检查联轴器弹性块磨损与地脚螺栓紧固状态", "tool": "扭矩扳手、塞尺", "acceptance": "磨损量与力矩值有记录"},
                {"seq": 3, "action": "用激光对中仪复测径向与角向偏差", "tool": "激光对中仪", "acceptance": "偏差实测值有记录"},
                {"seq": 4, "action": "通过调整垫片与地脚螺栓完成对中", "tool": "垫片组、扭矩扳手", "acceptance": "径向偏差 ≤ 0.05 mm，角向 ≤ 0.03 mm/100 mm"},
                {"seq": 5, "action": "按规定力矩紧固地脚螺栓并复测对中", "tool": "扭矩扳手、激光对中仪", "acceptance": "力矩达标且对中复测合格"},
                {"seq": 6, "action": "必要时做转子动平衡（更换配重）", "tool": "动平衡仪、配重块", "acceptance": "残余不平衡量在允许范围内"},
                {"seq": 7, "action": "复装防护罩，试运行并复测振动", "tool": "测振仪", "acceptance": "振动回到基线 +4σ 以内"},
            ],
            "verification": [
                {"sensor": "vibration_mm_s", "criterion": "尾部偏移 |z| < 4σ，回到基线水平"},
                {"sensor": "temperature_c", "criterion": "温度不再持续上升"},
            ],
        },
    },
    "overload": {
        "typical_delta": {"current_a": 15.5, "temperature_c": 13.5, "speed_rpm": -75.0, "vibration_mm_s": 2.6},
        "name": "负载过大 / 转动部件卡涩",
        "signature": {
            "current_a": (1.00, +1),
            "temperature_c": (0.70, +1),
            "speed_rpm": (0.80, -1),
            "vibration_mm_s": (0.30, +1),
        },
        "actions": [
            "核对工艺负载与出口阀门开度，确认是否超出设计工况",
            "检查电机保护定值与实际电流曲线",
            "手动盘车排查转动部件卡涩、异物或结垢",
        ],
        "parts": ["出口阀门", "电机保护器", "叶轮"],
        "plan": {
            "downtime": "conditional",
            "estimated_hours": 3.0,
            "safety": [
                "先在线降载排查，涉及拆检时必须断电挂牌上锁（LOTO）",
                "拆检前泄压排空，确认介质温度已降至安全范围",
                "清理结垢时佩戴防护面罩与耐腐蚀手套",
            ],
            "steps": [
                {"seq": 1, "action": "核对工艺负载与出口阀门开度，确认是否超出设计工况", "tool": "DCS 参数、现场阀位、工艺参数表", "acceptance": "负载回到设计范围内"},
                {"seq": 2, "action": "检查电机保护定值与电流记录，必要时修正定值", "tool": "保护测试仪", "acceptance": "定值与铭牌/设计一致"},
                {"seq": 3, "action": "降载运行并观察电流与温度趋势", "tool": "钳形电流表、红外测温仪", "acceptance": "电流回落，温度不再上升"},
                {"seq": 4, "action": "手动盘车排查转动部件卡涩、异物或结垢", "tool": "盘车工具、工业内窥镜", "acceptance": "盘车顺畅无卡涩"},
                {"seq": 5, "action": "清理叶轮与管路的结垢、异物", "tool": "高压水枪、清洗剂", "acceptance": "流道通畅，无异物残留"},
                {"seq": 6, "action": "复装后带载试运行，复测电流、温度、转速", "tool": "钳形电流表、测振仪、转速表", "acceptance": "各测点回到基线 +4σ 以内"},
            ],
            "verification": [
                {"sensor": "current_a", "criterion": "尾部偏移 |z| < 4σ，回到基线水平"},
                {"sensor": "temperature_c", "criterion": "尾部偏移 |z| < 4σ，回到基线水平"},
                {"sensor": "speed_rpm", "criterion": "转速恢复到额定值附近"},
                {"sensor": "vibration_mm_s", "criterion": "振动无明显持续抬升"},
            ],
        },
    },
    "cavitation": {
        "typical_delta": {"pressure_mpa": -0.28, "flow_m3h": -23.0, "vibration_mm_s": 5.0, "temperature_c": 4.5},
        "name": "泵气蚀 / 入口堵塞",
        "signature": {
            "pressure_mpa": (1.00, -1),
            "flow_m3h": (0.90, -1),
            "vibration_mm_s": (0.70, +1),
            "temperature_c": (0.30, +1),
        },
        "actions": [
            "检查入口过滤器压差并对堵塞滤网进行清洗",
            "确认吸入液位与有效汽蚀余量（NPSHa）满足要求",
            "对泵体排气，检查入口管路是否漏气",
        ],
        "parts": ["入口过滤器", "入口管路密封", "叶轮"],
        "plan": {
            "downtime": "conditional",
            "estimated_hours": 3.5,
            "safety": [
                "涉及拆检入口管路时必须断电挂牌上锁（LOTO）并泄压排空",
                "确认介质温度与腐蚀性，佩戴对应防护用品",
                "排气作业时人员避开泵体正上方，防止汽水喷溅",
            ],
            "steps": [
                {"seq": 1, "action": "检查入口过滤器压差，判断是否堵塞", "tool": "差压表 / 差压变送器", "acceptance": "压差实测值有记录"},
                {"seq": 2, "action": "清洗或更换堵塞的滤网", "tool": "清洗工具、备用滤网", "acceptance": "滤网压差回到设计值"},
                {"seq": 3, "action": "确认吸入液位与有效汽蚀余量（NPSHa）满足要求", "tool": "液位计、工艺计算表", "acceptance": "NPSHa > NPSHr + 安全余量"},
                {"seq": 4, "action": "泵体排气，检查入口管路是否漏气", "tool": "排气阀、发泡剂", "acceptance": "排气彻底，管路无泄漏"},
                {"seq": 5, "action": "检查叶轮气蚀损伤，必要时修磨或更换", "tool": "工业内窥镜、角磨机", "acceptance": "叶片无严重蜂窝状损伤"},
                {"seq": 6, "action": "恢复运行并逐步开阀，复测压力、流量与振动", "tool": "压力表、流量计、测振仪", "acceptance": "压力与流量回到基线 +4σ 以内"},
            ],
            "verification": [
                {"sensor": "pressure_mpa", "criterion": "尾部偏移 |z| < 4σ，回到基线水平"},
                {"sensor": "flow_m3h", "criterion": "尾部偏移 |z| < 4σ，回到基线水平"},
                {"sensor": "vibration_mm_s", "criterion": "振动回到基线 +4σ 以内"},
            ],
        },
    },
}


def fault_names() -> dict[str, str]:
    return {key: value["name"] for key, value in FAULT_LIBRARY.items()}


def repair_plan_for(fault: str) -> dict:
    """返回某类故障的结构化维修方案（浅拷贝，避免调用方改动知识库）。"""
    entry = FAULT_LIBRARY.get(fault)
    if entry is None:
        raise KeyError(f"unknown fault: {fault}")
    plan = entry.get("plan", {})
    return {
        "fault": fault,
        "fault_name": entry["name"],
        "downtime": plan.get("downtime", "offline"),
        "estimated_hours": plan.get("estimated_hours"),
        "safety": list(plan.get("safety", [])),
        "steps": [dict(step) for step in plan.get("steps", [])],
        "parts": list(entry.get("parts", [])),
        "verification": [dict(item) for item in plan.get("verification", [])],
    }