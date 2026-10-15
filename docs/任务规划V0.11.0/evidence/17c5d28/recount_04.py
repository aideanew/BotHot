import pathlib
import re
import sys

p = sorted(pathlib.Path("docs").glob("*V0.11.0/04-*.md"))[0]
lines = p.read_text(encoding="utf-8").splitlines()
hdr = next(i for i, l in enumerate(lines) if l.startswith("| STEP"))
n = tot = 0
days = 0.0
for l in lines[hdr + 2:]:
    if not l.startswith("| "):
        break
    c = [x.strip() for x in l.strip("|").split("|")]
    if c[0].startswith("**合计"):
        continue
    m = re.match(r"(\d+)", c[4].replace("*", ""))
    b = re.match(r"(\d+(?:\.\d+)?)", c[5].replace("*", ""))
    if m and b:
        n += 1
        tot += int(m.group(1))
        days += float(b.group(1))
print(f"行数={n} 任务={tot} 人日={round(days,2)}")

# §7 互校：三行小计之和 == §2 人日
tier_rows = [l for l in lines if l.startswith("| haiku/T1 |") or l.startswith("| sonnet/T2 |") or l.startswith("| opus/T3 |") or l.startswith("| 不计 |")]
subs = []
for l in tier_rows:
    c = [x.strip() for x in l.strip("|").split("|")]
    v = re.match(r"(\d+(?:\.\d+)?)", c[2])
    subs.append(float(v.group(1)))
print("§7 小计:", subs, "之和=", round(sum(subs), 2))
ok = abs(sum(subs) - days) < 1e-9
print("两表互校:", "PASS" if ok else "FAIL")
sys.exit(0 if ok and (n, tot, round(days, 2)) == (30, 192, 29.75) else 1)
