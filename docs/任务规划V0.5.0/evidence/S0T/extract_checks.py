"""S0T.1.1.1：从在库证明件里**提取判据清单**，生成迁移初表（不手抄标签）。

为什么要有这个脚本而不是手写一张表：手写的那张表每次 harness 加一条判据就旧一次，
而本仓已经为「抄来的数当场被现读打回」付过三次学费（`06-执行记录.md` 条 17/20/21）。
提取走 AST，不用 grep：标签出现在注释里不算判据。

用法（仓库根）：
    PYTHONIOENCODING=utf-8 python docs/任务规划V0.5.0/evidence/S0T/extract_checks.py [--write]
不带 `--write` 只打合计与各来源条数；带 `--write` 把 markdown 表写进
`docs/任务规划V0.5.0/evidence/S0T/判据迁移清单.md`（表尾自动带生成命令与合计）。

分类是**启发式**：它只回答「这条判据在问哪一类问题」，
『现有 pytest 等价』与『目标用例名』两列一律留 `⏳ 待补`——那两列是 S0T.1.1.2 的人工活，
机器替人填就等于把「已迁」写成愿望。
"""

from __future__ import annotations

import argparse
import ast
import datetime
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]

#: 取材面：文件 → 被证对象（一句话）。新增 harness 时要在这里登记，
#: 否则它不会被迁移清单看见——这条判据的「在册才可见」与 EVD-V2-02 的 EV_PY 同口径。
SOURCES: dict[str, str] = {
    "docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py": "conftest 的 DSN 两级解析与拒连广播",
    "docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py": "Provider 样本形状 ↔ 真实读取路径",
    "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py": "本机 ruff 子集近似表自身（含两端自证）",
    "docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py": "测试出站代理隔离夹具（NR-*）",
    "docs/06_validation/evidence/EVD-V2-02/prove_article_identity.py": "parse_wechat_url 的解析层（PI-*）",
    "docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py": "kb._biz_from_url 委托解析层（BD-*）",
    "docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py": "S2.1.4 锚定与 S2.1.5 片段守卫（AF-*）",
    "docs/06_validation/evidence/EVD-V2-02/replay_s213.py": "留档重放器与仓库静态门（M/N 段）",
    "docs/06_validation/evidence/EVD-V2-02/mutate_replay_r9.py": "反证电池自身（N-* 发与编码三发）",
    "docs/06_validation/evidence/EVD-V2-02/j_attack_r7.py": "第七轮「def 还在但活绑定已换」攻击面",
}

#: 标签形状：显式 id（BD-/AF-/PI-/NR-/G-/N-）或一句中文陈述（含 CJK 且长度 ≥12）。
ID_LABEL = re.compile(r"^(BD|AF|PI|NR|MI|NI|G|N|S|K|L|M|O|J)[-\d]", re.I)
CJK = re.compile(r"[一-鿿]")

KINDS = [
    ("反证/变异", ("变异", "应红", "致红", "MUTANT", "抽不得", "改坏")),
    ("等价写法", ("等价", "不许假红", "不假红", "同权", "EQUIV")),
    ("自证/档位", ("自证", "档位", "退出码", "编码", "三档", "末行", "崩溃", "崩栈", "traceback")),
    ("探针", ("探针", "注入", "故意", "必须点名", "不许沉默", "静默")),
    ("结构面", ("AST", "ast", "扫描", "def ", "绑定", "重绑", "全文", "名单", "白名单", "形状")),
    ("行为面", ("返回", "下发", "exec", "调用", "条件", "锚", "阈值", "片段", "字节", "字符")),
]


def classify(label: str) -> str:
    for name, marks in KINDS:
        if any(m in label for m in marks):
            return name
    return "未分类（S0T.1.1.2 人工）"


def labels_from(path: pathlib.Path) -> list[tuple[int, str]]:
    """这个文件里被**当成判据在用**的字符串标签：`check(...)` 的实参，或登记表元组的首项。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, ValueError) as exc:
        print(f"WARN 读不出 {path}: {type(exc).__name__}: {exc}")
        return []
    out: list[tuple[int, str]] = []
    seen: set[str] = set()

    def keep(node: ast.AST) -> str | None:
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            return None
        s = " ".join(node.value.split())
        if len(s) < 8 or s in seen:
            return None
        if not (ID_LABEL.match(s) or (len(CJK.findall(s)) >= 4 and len(s) >= 12)):
            return None
        seen.add(s)
        return s

    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = n.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if name in {"check", "add", "fail", "reason", "ok"}:
                for a in n.args:
                    s = keep(a)
                    if s:
                        out.append((getattr(a, "lineno", 0), s))
        elif isinstance(n, ast.Tuple) and n.elts:
            s = keep(n.elts[0])
            if s:
                out.append((getattr(n, "lineno", 0), s))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="把 markdown 表写进本目录")
    args = ap.parse_args()
    rows: list[tuple[str, int, str, str, str]] = []
    for rel, target in SOURCES.items():
        p = ROOT / rel
        if not p.is_file():
            rows.append((rel, 0, "⛔ 文件不在登记表所指路径", "登记", "——"))
            continue
        for line, label in labels_from(p):
            rows.append((rel, line, label, classify(label), target))
    per: dict[str, int] = {}
    for r in rows:
        per[r[0]] = per.get(r[0], 0) + 1
    # 零标签的登记来源不是「没有判据」，而是**这份脚本认不出它的判定形态**——
    # 沉默地少一份，下一轮就会被读成「那份已经迁完了」。这里把它显式登记成待人工补。
    empty = [rel for rel in SOURCES if per.get(rel, 0) == 0]
    for rel in empty:
        rows.append((rel, 0, "⏳ 未提取到标签：这份件的判定不走 check(...) 也不走登记表元组，"
                             "形态需人工登记（见本脚本 SOURCES）", "未分类（S0T.1.1.2 人工）", SOURCES[rel]))
    if not args.write:
        for k in sorted(per):
            print(f"  {per[k]:>4}  {k}")
        print(f"合计标签 {len(rows)} 条、登记来源 {len(SOURCES)} 份（提取到标签的 {len(per)} 份）"
              "——三个数现算，勿抄进正文")
        return 0
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    out = [
        "# 判据迁移清单（S0T.1.1.1 自动初表 —— 标签由脚本提取，不手抄）",
        "",
        f"> 生成：{stamp}｜生成命令：`PYTHONIOENCODING=utf-8 python "
        "docs/任务规划V0.5.0/evidence/S0T/extract_checks.py --write`",
        f"> 合计 {len(rows)} 条标签、登记来源 {len(SOURCES)} 份（其中 {len(per)} 份提取到标签、"
        f"{len(SOURCES) - len(per)} 份提取为 0 并已显式登记为待人工补）；三个数都由脚本现算。",
        "> 『现有 pytest 等价』与『目标用例名』两列**故意留空**：那是 S0T.1.1.2 的人工判断，"
        "机器替人填就会把「已迁」写成愿望（本仓为此付过学费，见 `06-执行记录.md` 条 17）。",
        "",
        "| # | 来源 | 行 | 分类 | 判据标签（原文） | 被证对象 | 现有 pytest 等价 | 目标用例名 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, (rel, line, label, kind, target) in enumerate(sorted(rows, key=lambda x: (x[0], x[1])), 1):
        short = label if len(label) <= 90 else label[:88] + "…"
        out.append(f"| {i} | `{rel.split('/')[-1]}` | {line} | {kind} | {short} | {target} | ⏳ 待补 | ⏳ 待补 |")
    out += ["", "## 分类口径", "",
            "- **行为面**：跑一段真实/仿真代码问「返回了什么、下发了什么条件」；迁 pytest 时可等价。",
            "- **结构面**：AST/文本扫描问「这份源码长什么样」；多数**不可**等价进 pytest（CI 里没有这台机器）。",
            "- **探针 / 反证 / 等价 / 自证**：判的是门禁自身的判定力与体面性，属**取证工具**，"
            "迁移时随脚本一起归档（S0T.3.1），不冒充业务用例。",
            "- **前提/其它**：登记表在不在册、路径存不存在这类前置。"]
    dst = pathlib.Path(__file__).with_name("判据迁移清单.md")
    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"写出 {dst.relative_to(ROOT)}：{len(rows)} 行、登记来源 {len(SOURCES)} 份"
          f"（提取到标签的 {len(per)} 份）——合计由脚本现算")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
