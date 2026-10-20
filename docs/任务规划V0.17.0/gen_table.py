"""V0.17.0 剩余量复算脚本（规划产物，纯 stdlib）。
口径：total 继承 V0.16.0；remain 为本版逐卡复算，依据写在 basis 列。
2026-10-20 建于 main@81205f1：规划方交付 21（c93a6bc/1834c4a/bec5225）、01（25088c4）、13（81205f1）；
按 D-V17-01 分工口径，原规划方的 19/15/15b/14b/12 全部转执行助手；新增 30（三卡独立复查）、31（写操作审计日志，D-V17-02）。
运行：python docs/任务规划V0.17.0/gen_table.py  → 打印 Markdown 表与合计、DAG 环检测。
"""
from __future__ import annotations

# (id, 卡路径根, 里程碑, total, remain, 人日/项, owner, 档位, 状态, 依赖, 依据)
V13 = "V0.13.0"
V14 = "V0.14.0"
V15 = "V0.15.0"
V16 = "V0.16.0"
V17 = "V0.17.0"
CARDS = [
    # ── M0 前提与 P0 ──────────────────────────────────────────────
    ("24", V14, "M0-P0", 6, 0, 0.25, "—", "—", "✅ 7504ef8（独立复查+@ci 见 07）", [], "先红 500/50001 + 归属可伪造；改后 200/0、归属=当前登录者（EVD-V14-24）；探针 ② 两行 200 0"),
    ("25", V14, "M0-P0", 6, 0, 0.2, "—", "—", "✅ 7504ef8（按 D-V12-12 收窄；独立复查+@ci 见 07）", ["24"], "守卫先红 10 处→0；矩阵 operator 8 格 10004→放行，admin-only 5 行锁定（EVD-V14-25）；顺修 P-39"),
    ("00H", V13, "M0", 7, 1, 0.1, "执行 Agent-Guard", "haiku", "🟢 仅余 S00H.2.3", [], "执行方 07 §7：前置已复算成立，缺 Windows durations；本版无新交付"),
    ("22", V13, "M0", 6, 0, 0.0, "—", "—", "✅", [], "1236d50/31a6667/15470ee；CI fdad6dd success"),
    ("00G", V13, "M0", 9, 0, 0.0, "—", "—", "✅（S0G.2.1 由 D-V11-04 关闭并转 00T）", [], "V0.13.0/09 §5-§6 对账：3 已交付、3 卡面过期、1 转 00T、1 本版裁决关闭"),
    ("00T", V13, "M0", 12, 9, 0.15, "执行 Agent-Guard", "sonnet", "🟡 V14.1-3 已交付，余原 9", ["00G"], "067ff59/e99fac1/6f5a1a9/b034cd7；@linux 非空批 evidence-check rc=0（evidence/410ac20/evidence_check_nonempty_*.txt）"),
    ("00R", V13, "M0", 10, 9, 0.1, "执行 Agent-Guard", "sonnet", "🟡 V14.1 已交付，余原 9", [], "7a525a0；本版全量 1712/5/0 含该用例"),
    ("00E", V13, "M0", 4, 4, 0.15, "执行 Agent-Guard", "sonnet", "🟡 待依赖机", [], "V0.13.0/09 §2：S00E.1.2/1.3/2.1/3.2 均缺 docker 或需同环境连跑"),
    ("00X", V13, "M0", 9, 2, 0.1, "执行 Agent-Guard", "sonnet", "🟡", ["00H"], "V0.13.0 表剩 2，本版未见新交付"),
    ("00P", V13, "M0", 5, 0, 0.0, "—", "—", "✅（验收①按 D-V12-04 在 @linux 非空批 rc=0 确认；Windows 面随 27）", [], "56a9049；@ci 三绿 39214424679/726/699"),
    ("27", V15, "M0", 8, 0, 0.15, "—", "—", "✅ 按 D-V16-01 收口（独立复查 B–E PASS；A 为存量召回缺口，转 P-44 → 29）", [], "d32edfc 七项 + 9e1532d S27.2 第2轮；CI 39271291938/Win 39271292029/Sec 39271292556 三绿；28c0d2e 三绿 39274782243/211/247"),
    ("29", V16, "M0", 6, 6, 0.2, "执行 Agent-Guard", "sonnet", "⚪ 新增（P-41/P-44 召回补缺、P-45 误报、P-42 夹具、P-43 隔离、P-46 读数口径）——**队列第一项**", ["27"], "28c0d2e 普查：11 个自有文件仍有命中（含 app/providers/reranker.py 1 条误报）；复查 A 项 6 类漏报（evidence/28c0d2e）"),
    ("RV", V13, "M0", 4, 4, 0.1, "执行 Agent-API", "sonnet", "🟢 已解锁（@ci junit 即真库证据）", ["00H"], "V0.13.0/09 E-03/E-04"),
    ("R0", V13, "M0", 0, 0, 0.0, "—", "—", "🟡 待 RV", ["RV"], "无独立项"),
    ("16", V13, "M0", 0, 0, 0.0, "—", "—", "🟡 待 RV", ["RV"], "无独立项"),
    ("00W", V13, "M0", 8, 0, 0.0, "—", "—", "✅", [], "残余并入 00H"),
    ("00S", V13, "M0", 10, 0, 0.0, "—", "—", "✅", [], "Security fdad6dd success(39184824740)"),
    ("00C", V13, "M0", 0, 0, 0.0, "—", "—", "✅", [], "—"),
    ("30", V17, "M0", 4, 4, 0.15, "执行 Agent-Guard", "sonnet", "⚪ 新增：规划方 21/01/13 三卡独立复查 + SessionClaims 登记更正", ["29"], "规划方自做的卡须由执行方独立判 PASS/FAIL"),
    # ── M1 采集主线 ─────────────────────────────────────────────
    ("01", V13, "M1", 10, 0, 0.25, "—", "—", "✅ 25088c4（jsonschema 成语义真源 + api.envelope 收编；复查归 30）", [], "EVD-V13-01/s01_close.md；本机真库 1902/5/0"),
    ("02", V13, "M1", 9, 0, 0.0, "—", "—", "✅", [], "a6f54e1 S2.4"),
    ("03", V13, "M1", 10, 0, 0.0, "—", "—", "✅", [], "—"),
    ("04", V13, "M1", 10, 1, 0.1, "执行 Agent-API", "sonnet", "🟡 S4.5.1 复跑", [], "V0.13.0/09 E-11"),
    ("20", V13, "M1", 4, 0, 0.0, "—", "—", "✅（P-27 由 D-V11-05 追认）", [], "2a7195d + f7a3a6b 返工"),
    ("10", V13, "M1", 3, 6, 0.15, "执行 Agent-API", "sonnet", "⚪ +3（P-20 反证 +1；D-V12-13 接线默认关 +1、触发/供应商可配 +1）", ["20", "29", "28"], "Coordinator 全仓 0 实例化（8cd0e68 前 AST 现读）；S10.V15.2 依赖 28 的 system_settings"),
    ("05", V13, "M1", 6, 7, 0.15, "执行 Agent-API", "sonnet", "⚪ +1（P-30 计数器）", ["29"], "P-9 与 P-30 同卡"),
    ("06", V13, "M1", 7, 7, 0.2, "执行 Agent-Guard", "sonnet", "⚪", ["05", "10"], "CI --cov-fail-under=75 vs 卡面 85%（本机现读 86%）"),
    ("07", V13, "M1", 5, 8, 0.25, "执行 Agent-Data", "sonnet", "⚪ +3（D-V12-14 测试库演练；S24.3.1 孤儿行 + P-39 明文行审计；P-39 重加密脚本）", ["02", "04"], "生产只读 DSN 未提供 ⇒ 生产读数写未测"),
    ("08", V13, "M1", 6, 7, 0.2, "执行 Agent-Data", "sonnet", "⚪ +1（P-28 第二套时间规范）", ["07"], "持迁移号 ab1006c2a"),
    ("09", V13, "M1", 4, 4, 0.2, "执行 Agent-Data", "sonnet", "⚪", ["08"], "条件迁移 ab1006c3a"),
    ("11", V13, "M1", 4, 4, 0.15, "执行 Agent-API", "sonnet", "⚪", ["06"], "D-V3-08：先基线后优化"),
    ("28", V15, "M1", 9, 9, 0.25, "执行 Agent-API", "sonnet", "⚪ 新增（D-V12-12 运营配置采集渠道/分类）", ["25", "29"], "registry/categorizer 只读 env/常量，全仓无写接口（d1db090 现读）；迁移 ab1006c4a，与 08/09 串行"),
    # ── M2 安全与身份 ───────────────────────────────────────────
    ("23", V13, "M2", 3, 0, 0.0, "—", "—", "✅", [], "831d6e9 + 三轮 @ci 复跑 + db7e63b"),
    ("26", V14, "M2", 5, 5, 0.15, "执行 Agent-API", "sonnet", "⚪ 新增", ["23", "25", "29"], "P-29（/admin/push 第三条直投路径）+ P-24/P-25 文本为假 + P-30 顺序"),
    ("21", V13, "M2", 7, 0, 0.3, "—", "—", "✅ c93a6bc/1834c4a/bec5225（@ci 三绿；复查归 30）", ["22", "25"], "47 个带参操作全部归类；先红抓到引擎 Key 写操作 operator 可达 ⇒ D-V16-06"),
    ("19", V13, "M2", 6, 6, 0.2, "执行 Agent-API", "sonnet", "⚪ 转执行助手（D-V17-01）", ["21"], "已实现未纳管域验证：按卡面逐域补测，非架构工作"),
    ("31", V17, "M2", 4, 4, 0.2, "执行 Agent-API", "sonnet", "⚪ 新增（D-V17-02：写操作结构化审计日志）", ["29"], "全仓无审计设施（grep audit 0 命中）；identity 契约要求运营写操作记录操作者 sub（R-V14-03）"),
    ("17", V13, "M2", 7, 8, 0.1, "执行 Agent-Doc", "haiku", "⚪ +1（P-22 discoveredCount 口径）", [], "读 01 X-6/X-7"),
    # ── M3 引擎 / 管理端 / 前端 ────────────────────────────────
    ("13", V13, "M3", 6, 0, 0.3, "—", "—", "✅ 81205f1（engine 契约 + reason 四值；复查归 30）", ["01"], "EVD-V3-13/s13_readings.md；本机真库 1953/5/0"),
    ("14a", V13, "M3", 9, 10, 0.25, "执行 Agent-API", "sonnet", "⚪ +1（P-18 retry 接四态）", ["01"], "D-V3-06"),
    ("15", V13, "M3", 9, 6, 0.2, "执行 Agent-Web", "sonnet", "🟡 转执行助手（D-V17-01）+1（EngineSwitcher 读 reason）", ["01", "13"], "契约已冻结，前端只按契约对齐"),
    ("15b", V13, "M3", 8, 11, 0.25, "执行 Agent-Web", "sonnet", "⚪ 转执行助手（D-V17-01）+1（/admin/ops 对 operator 隐藏引擎 Key 登记/撤销）", ["24", "25"], "http.ts MOCK 默认仍 true；D-V16-06 后 operator 点登记会得 403"),
    ("14b", V13, "M3", 13, 3, 0.5, "执行 Agent-Web", "sonnet", "🟡 转执行助手（D-V17-01）", ["14a", "15b", "28"], "四屏已在；余告警条 + 采集配置页，沿用现有组件与 LoadingErrorShell"),
    ("18", V13, "M3", 5, 5, 0.2, "执行 Agent-Guard", "sonnet", "⚪", ["11"], "—"),
    ("12", V13, "M4", 6, 6, 0.15, "执行 Agent-Doc", "sonnet", "⚪ 收口，转执行助手（D-V17-01）", ["06", "07", "08", "09", "19", "14b", "18", "30", "31"], "全部清后发布；发布结论由用户拍板"),
]

PATHS = {
    "30": "steps/STEP-30-规划方三卡独立复查.md",
    "31": "steps/STEP-31-写操作结构化审计日志.md",
    "29": "steps/STEP-29-夹具占位形与证据脚本隔离.md",
    "27": "steps/STEP-27-守卫门口径追认与CI接线.md",
    "28": "steps/STEP-28-采集渠道与分类运营可配置-后端.md",
    "24": "steps/STEP-24-推送任务创建恒500与创建者归属服务端化.md",
    "25": "steps/STEP-25-角色门单参数化-运营写权按意图恢复.md",
    "26": "steps/STEP-26-管理端直投第三路径补写站内历史与直投文本纠真.md",
}


def table() -> str:
    head = "| # | STEP | 卡路径 | 里程碑 | 总项 | 本版剩余 | 剩余人日 | owner | 档位 | 状态 | 依赖 | 复算依据 |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
    rows = []
    for i, (cid, ver, ms, tot, rem, pd, own, tier, st, dep, basis) in enumerate(CARDS, 1):
        path = f"`{ver}/{PATHS[cid]}`" if ver in (V14, V15, V16, V17) else f"`{V13}/steps/STEP-{cid}-*`"
        rows.append(f"| {i} | **{cid}** | {path} | {ms} | {tot} | {rem} | {rem*pd:.2f} | {own} | {tier} | {st} | {','.join(dep) or '—'} | {basis} |")
    tot = sum(c[3] for c in CARDS); rem = sum(c[4] for c in CARDS); pd = sum(c[4] * c[5] for c in CARDS)
    rows.append(f"| | **合计 {len(CARDS)} STEP** | | | **{tot}** | **{rem}** | **{pd:.2f}** | | | | | |")
    return head + "\n" + "\n".join(rows)


def acyclic() -> bool:
    g = {c[0]: c[9] for c in CARDS}
    seen, stack = set(), set()

    def dfs(n):
        if n in stack:
            return False
        if n in seen:
            return True
        stack.add(n)
        ok = all(dfs(m) for m in g.get(n, []))
        stack.discard(n); seen.add(n)
        return ok

    return all(dfs(n) for n in g)


def critical_path():
    g = {c[0]: c for c in CARDS}
    memo = {}

    def best(n):
        if n in memo:
            return memo[n]
        c = g[n]; w = c[4] * c[5]
        prev = max((best(d) for d in c[9]), key=lambda x: x[0], default=(0.0, []))
        memo[n] = (prev[0] + w, prev[1] + [n])
        return memo[n]

    return max((best(n) for n in g), key=lambda x: x[0])


if __name__ == "__main__":
    print(table())
    print("\nacyclic", acyclic())
    w, p = critical_path()
    print("critical", " → ".join(p), f"{w:.2f} 人日")
    by = {}
    for c in CARDS:
        by.setdefault(c[6], [0, 0.0]); by[c[6]][0] += c[4]; by[c[6]][1] += c[4] * c[5]
    for k, (n, d) in by.items():
        print(f"owner {k}: {n} 项 / {d:.2f} 人日")
    tiers = {}
    for c in CARDS:
        tiers[c[7]] = tiers.get(c[7], 0) + c[4]
    print("tiers", tiers)
