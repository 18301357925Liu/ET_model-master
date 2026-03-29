QWEN_SYSTEM_PROMPT = """你是一位认知科学与教育技术专家，专注于通过眼动追踪数据评估人在学习算法时的认知负荷，并为学习者提供个性化学习建议。

你的分析基于以下眼动认知负荷模型：
- L0 / L1（极低~低负荷）：浏览、定位等被动感知活动，不需要深度认知加工
- L2（中等负荷）：单源信息整合，简单逻辑推理
- L3（中高负荷）：多源信息整合、条件判断、步骤规划
- L4（高负荷）：持续专注解题、长时记忆检索、高度抑制干扰

请根据用户提供的任务认知负荷数据，从以下维度给出分析和建议：
1. **当前认知负荷分布特征**：整体负荷水平、波动情况
2. **学习行为诊断**：哪些算法类型/任务让学生感到吃力，原因可能是什么
3. **个性化学习建议**：
   - 针对高负荷任务的预习策略（如补充前置知识、画流程图）
   - 降低中等负荷任务认知门槛的方法（如分块学习、间隔重复）
   - 维持低负荷高效状态的学习节奏安排
4. **具体可操作步骤**：每天/每周的学习计划调整

请用清晰的中文回答，结构化输出，使用 Markdown 格式（标题、加粗、列表等），语言风格专业但不晦涩，适合有一定编程基础但算法理解有困难的学习者。"""

USER_MESSAGE_TEMPLATE = (
    "请分析以下认知负荷数据，给出详细的学习建议：\n\n"
    "{context}"
    "\n\n请给出结构化的分析报告和学习建议（使用 Markdown 格式）。"
)


def _level_num(val):
    if val is None or str(val).strip().lower() in ("", "none", "null"):
        return 0
    s = str(val).strip()
    if s.startswith("L"):
        s = s[1:]
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


def build_advice_context(records: list, session_filter: str = "") -> str:
    if not records:
        return "当前没有可用的任务记录，请先执行 Pipeline 或加载数据。"

    if session_filter:
        records = [r for r in records if session_filter.lower() in (r.get("session") or "").lower()]

    total = len(records)
    sessions = sorted(set(r.get("session", "?") for r in records))
    clusters = sorted(set(str(r.get("cluster", "?")) for r in records))
    levels = [_level_num(r.get("level")) for r in records]
    avg_level = sum(levels) / len(levels) if levels else 0
    level_dist: dict[int, int] = {}
    for lv in levels:
        level_dist[lv] = level_dist.get(lv, 0) + 1

    by_session: dict[str, list] = {}
    for r in records:
        s = r.get("session", "?")
        by_session.setdefault(s, []).append(r)

    session_blocks = []
    for sname in sessions:
        tasks = by_session.get(sname, [])
        task_lines = []
        for t in tasks:
            lvl = t.get("level", "?")
            label = t.get("label", "")
            cluster = t.get("cluster", "?")
            task_lines.append(
                f"    - Task {t.get('task_id', '?')}: "
                f"Cluster={cluster}, 负荷等级={lvl} ({label})"
            )
        session_levels = [_level_num(t.get("level", 0)) for t in tasks]
        avg_s = sum(session_levels) / len(session_levels) if session_levels else 0
        session_blocks.append(
            f"  Session {sname}（共 {len(tasks)} 个任务，平均负荷 {avg_s:.2f}）：\n"
            + "\n".join(task_lines)
        )

    dist_lines = [f"    L{lv}: {cnt} 个任务" for lv, cnt in sorted(level_dist.items())]

    return f"""## 当前认知负荷数据概览

**数据范围**：{len(sessions)} 个 Session，共 {total} 个任务记录
**覆盖 Cluster**：{', '.join(clusters)}
**平均负荷等级**：{avg_level:.2f}（范围 L0–L4）

### 负荷等级分布
{chr(10).join(dist_lines)}

### 各 Session 详细数据
{chr(10).join(session_blocks)}

请基于以上数据，给出针对该学习者（可能正在学习算法）的认知负荷分析与个性化学习建议。"""
