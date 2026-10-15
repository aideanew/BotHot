import pathlib
import re

ROOT = pathlib.Path("docs/任务规划V0.11.0")
lines = (ROOT / "04-剩余可执行大纲体系.md").read_text(encoding="utf-8").splitlines()
hdr = next(i for i, l in enumerate(lines) if l.startswith("| STEP"))

days = {}
tasks = {}
for l in lines[hdr + 2:]:
    if not l.startswith("| "):
        break
    c = [x.strip() for x in l.strip("|").split("|")]
    if c[0].startswith("**合计"):
        continue
    key = c[0].replace("*", "")
    m = re.match(r"(\d+(?:\.\d+)?)", c[5].replace("*", ""))
    t = re.match(r"(\d+)", c[4].replace("*", ""))
    days[key] = float(m.group(1)) if m else 0.0
    tasks[key] = int(t.group(1)) if t else 0

TIER = {
    "haiku/T1": ["00G", "00R", "00P", "11", "12", "17"],
    "sonnet/T2": ["00E", "00S", "RV", "R0", "16", "00T", "02", "03", "04", "05", "06",
                  "07", "08", "09", "10", "18", "19"],
    "opus/T3": ["00X", "01", "13", "14a", "14b", "15"],
}

acc = set()
for tier, cards in TIER.items():
    for k in cards:
        acc.add(k)
    print(tier, "cards=", len(cards), "sum=", round(sum(days[k] for k in cards), 2))

missing = sorted(set(days) - acc)
ghost = sorted(acc - set(days))
print("§2 未被任何档位覆盖:", missing, "| 档位表里 §2 没有的:", ghost)
print("§2 合计 人日=", round(sum(days.values()), 2), "任务=", sum(tasks.values()), "卡=", len(days))

for tier, cards in TIER.items():
    print(tier, "→", "、".join(f"{k} {days[k]:g}" for k in cards))
