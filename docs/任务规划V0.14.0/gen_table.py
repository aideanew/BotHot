"""V0.14.0 剩余量复算脚本（规划产物，纯 stdlib）。
口径：total 继承 V0.13.0 `04-…§2` 第 5 列；remain 为本版逐卡复算，依据写在 basis 列。
运行：python docs/任务规划V0.14.0/gen_table.py  → 打印 Markdown 表与合计、DAG 环检测。
"""
from __future__ import annotations

# (id, 卡路径根, 里程碑, total, remain, 人日/项, owner, 档位, 状态, 依赖, 依据)
V13 = "V0.13.0"
V14 = "V0.14.0"
CARDS = [
    # ── M0 前提与 P0 ──────────────────────────────────────────────
    ("24", V14, "M0-P0", 6, 6, 0.25, "规划方(Hark)", "opus", "⚪ 新增 P0", [], "本版探针：POST /bots/tasks 对任何人 500（evidence/fdad6dd/probe_push_write_roles_and_created_by.txt ②）"),
    ("25", V14, "M0-P0", 6, 6, 0.2, "规划方(Hark)", "opus", "⚪ 新增 P0", ["24"], "本版探针：operator 写推送域 403/10004；has_min_rank(operator,admin,operator)=False"),
    ("00H", V13, "M0", 7, 1, 0.1, "执行 Agent-Guard", "haiku", "🟢 仅余 S00H.2.3", [], "CI-Windows success：fad54a9(39041663333)、72a7a0e(39041589812)、fdad6dd(39184824751) 三个不同 head_sha ⇒ S00H.2.3 前置已满足"),
    ("22", V13, "M0", 6, 0, 0.0, "—", "—", "✅", [], "1236d50/31a6667/15470ee；CI fdad6dd success"),
    ("00G", V13, "M0", 9, 0, 0.0, "—", "—", "✅（S0G.2.1 由 D-V11-04 关闭并转 00T）", [], "V0.13.0/09 §5-§6 对账：3 已交付、3 卡面过期、1 转 00T、1 本版裁决关闭"),
    ("00T", V13, "M0", 9, 12, 0.15, "执行 Agent-Guard", "sonnet", "⚪ +3 增量（V0.14.0/steps/STEP-00T-增量）", ["00G"], "原 9 + D-14 轮次门 + D-V4-03 耦合门 + F-14 证据脚本（evidence_check.txt 仍红）"),
    ("00R", V13, "M0", 9, 10, 0.1, "执行 Agent-Guard", "sonnet", "⚪ +1 增量（V0.14.0/steps/STEP-00R-增量）", [], "原 9 + F-V14-03 用例读宿主环境（production_guard_env_leak.txt）"),
    ("00E", V13, "M0", 4, 4, 0.15, "执行 Agent-Guard", "sonnet", "🟡 待依赖机", [], "V0.13.0/09 §2：S00E.1.2/1.3/2.1/3.2 均缺 docker 或需同环境连跑"),
    ("00X", V13, "M0", 9, 2, 0.1, "执行 Agent-Guard", "sonnet", "🟡", ["00H"], "V0.13.0 表剩 2，本版未见新交付"),
    ("00P", V13, "M0", 5, 5, 0.1, "执行 Agent-Guard", "sonnet", "⚪", [], "V0.13.0 表剩 5，未见新交付"),
    ("RV", V13, "M0", 4, 4, 0.1, "执行 Agent-API", "sonnet", "🟢 已解锁（@ci junit 即真库证据）", ["00H"], "V0.13.0/09 E-03/E-04"),
    ("R0", V13, "M0", 0, 0, 0.0, "—", "—", "🟡 待 RV", ["RV"], "无独立项"),
    ("16", V13, "M0", 0, 0, 0.0, "—", "—", "🟡 待 RV", ["RV"], "无独立项"),
    ("00W", V13, "M0", 8, 0, 0.0, "—", "—", "✅", [], "残余并入 00H"),
    ("00S", V13, "M0", 10, 0, 0.0, "—", "—", "✅", [], "Security fdad6dd success(39184824740)"),
    ("00C", V13, "M0", 0, 0, 0.0, "—", "—", "✅", [], "—"),
    # ── M1 采集主线 ─────────────────────────────────────────────
    ("01", V13, "M1", 10, 2, 0.25, "规划方(Hark)", "opus", "🟡 解除阻塞", [], "D-V8-05/08 已签 A，jsonschema 化 + 收编 api 域"),
    ("02", V13, "M1", 9, 0, 0.0, "—", "—", "✅", [], "a6f54e1 S2.4"),
    ("03", V13, "M1", 10, 0, 0.0, "—", "—", "✅", [], "—"),
    ("04", V13, "M1", 10, 1, 0.1, "执行 Agent-API", "sonnet", "🟡 S4.5.1 复跑", [], "V0.13.0/09 E-11"),
    ("20", V13, "M1", 4, 0, 0.0, "—", "—", "✅（P-27 由 D-V11-05 追认）", [], "2a7195d + f7a3a6b 返工"),
    ("10", V13, "M1", 3, 4, 0.15, "执行 Agent-API", "sonnet", "⚪ +1（P-20 两条反证）", ["20"], "TikHub 降级语义已修 ⇒ 阻塞解除"),
    ("05", V13, "M1", 6, 7, 0.15, "执行 Agent-API", "sonnet", "⚪ +1（P-30 计数器）", [], "P-9 与 P-30 同卡"),
    ("06", V13, "M1", 7, 7, 0.2, "执行 Agent-Guard", "sonnet", "⚪", ["05", "10"], "CI --cov-fail-under=75 vs 卡面 85%（本机现读 86%）"),
    ("07", V13, "M1", 5, 5, 0.25, "执行 Agent-Data", "sonnet", "⚪ U-29", ["02", "04"], "D-V2-06 探测先行"),
    ("08", V13, "M1", 6, 7, 0.2, "执行 Agent-Data", "sonnet", "⚪ +1（P-28 第二套时间规范）", ["07"], "持迁移号 ab1006c2a"),
    ("09", V13, "M1", 4, 4, 0.2, "执行 Agent-Data", "sonnet", "⚪", ["08"], "条件迁移 ab1006c3a"),
    ("11", V13, "M1", 4, 4, 0.15, "执行 Agent-API", "sonnet", "⚪", ["06"], "D-V3-08：先基线后优化"),
    # ── M2 安全与身份 ───────────────────────────────────────────
    ("23", V13, "M2", 3, 0, 0.0, "—", "—", "✅", [], "831d6e9 + 三轮 @ci 复跑 + db7e63b"),
    ("26", V14, "M2", 5, 5, 0.15, "执行 Agent-API", "sonnet", "⚪ 新增", ["23", "25"], "P-29（/admin/push 第三条直投路径）+ P-24/P-25 文本为假 + P-30 顺序"),
    ("21", V13, "M2", 7, 7, 0.3, "规划方(Hark)", "opus", "⚪", ["22", "25"], "IDOR 连库矩阵；须在 25 之后，矩阵按单参数秩写"),
    ("19", V13, "M2", 6, 6, 0.2, "规划方(Hark)", "opus", "⚪", ["21"], "—"),
    ("17", V13, "M2", 7, 8, 0.1, "执行 Agent-Doc", "haiku", "⚪ +1（P-22 discoveredCount 口径）", [], "读 01 X-6/X-7"),
    # ── M3 引擎 / 管理端 / 前端 ────────────────────────────────
    ("13", V13, "M3", 6, 6, 0.3, "规划方(Hark)", "opus", "⚪", ["01"], "D-V3-03"),
    ("14a", V13, "M3", 9, 10, 0.25, "执行 Agent-API", "sonnet", "⚪ +1（P-18 retry 接四态）", ["01"], "D-V3-06"),
    ("15", V13, "M3", 9, 5, 0.2, "规划方(Hark)", "opus", "🟡", ["01"], "—"),
    ("15b", V13, "M3", 6, 8, 0.25, "规划方(Hark)", "opus", "⚪ +2（P-21 按秩导航 + 无权页）", ["24", "25"], "http.ts:18-19 MOCK 默认仍 true（本版现读）"),
    ("14b", V13, "M3", 13, 2, 0.5, "规划方(Hark)", "opus", "🟡", ["14a", "15b"], "UI 设计与实现由规划方自做"),
    ("18", V13, "M3", 5, 5, 0.2, "执行 Agent-Guard", "sonnet", "⚪", ["11"], "—"),
    ("12", V13, "M4", 6, 6, 0.15, "规划方(Hark)", "opus", "⚪ 收口", ["06", "07", "08", "09", "19", "14b", "18"], "全部清后发布"),
]

PATHS = {
    "24": "steps/STEP-24-推送任务创建恒500与创建者归属服务端化.md",
    "25": "steps/STEP-25-角色门单参数化-运营写权按意图恢复.md",
    "26": "steps/STEP-26-管理端直投第三路径补写站内历史与直投文本纠真.md",
}


def table() -> str:
    head = "| # | STEP | 卡路径 | 里程碑 | 总项 | 本版剩余 | 剩余人日 | owner | 档位 | 状态 | 依赖 | 复算依据 |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
    rows = []
    for i, (cid, ver, ms, tot, rem, pd, own, tier, st, dep, basis) in enumerate(CARDS, 1):
        path = f"`{V14}/{PATHS[cid]}`" if ver == V14 else f"`{V13}/steps/STEP-{cid}-*`"
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
