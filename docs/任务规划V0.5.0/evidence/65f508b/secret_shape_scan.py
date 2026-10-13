"""入库前的「敏感形」召回器：本机没有 gitleaks 二进制时，用 .gitleaks.toml 规则 1 的正则原样复刻跑一遍。

它**不替代** gitleaks（上游默认规则、熵判据、allowlist 的完整语义都在真正的二进制里），
它只做一件事：把 `scheme://<账号>:<口令>@<主机>` 这类邻接形、以及常见的已知 token 前缀
在待入库文件里数出来，好让「这批能不能进 main」这个问题有一个可重跑的读数，
而不是靠人眼扫一遍。命中只报 文件:行号 + 形状片段，不报整行正文。

用法：python secret_shape_scan.py <目录>   →  末行打印 HIGH/ALLOWED 计数（现算，勿抄进正文）
"""

import pathlib
import re
import sys

# 与 .gitleaks.toml 规则 connection-string-embedded-password 同一条正则（RE2 无 lookahead）
DSN = re.compile(r"(?i)[a-z][a-z0-9+.\-]*://[^:/\s\"']+:[^@/\s\"']+@")

RULES = [
    ("dsn-embedded-password", DSN),
    ("aws-akia", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("vendor-key-assign",
     re.compile(r"(?i)(?:tikhub|dajiala|wellbyte|redfox)[_-]?(?:api[_-]?key|token)"
                r"\s*[:=]\s*\S{8,}")),
]

# 与 .gitleaks.toml 的占位口令 allowlist 同源：模板/假值不是秘密
ALLOW = [
    re.compile(r"[:/](?:\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|<[^>\s]+>|%[sdv])@"),
    re.compile(r"://(?:[^:/\s\"@]+|<user>):"
               r"(?:bothot|bothot_dev|bothot_ci|aideanbot|nobody|nosuch|not_a_secret)@"),
]

# 口令赋值形（`password = "…"`）：值像占位/脱敏就不算，其余一律 HIGH 交人判
ASSIGN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|dsn)\b"
    r"\s*[:=]\s*[\"']?([^\"'\s,;)}]{4,})")
FAKE = re.compile(r"(?i)^(?:<[^>]*>|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[sdv]"
                  r"|change[_-]?me|your[_-]?\S*|REDACTED\S*|x{4,}|\*{4,})$")

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
files = sorted(p for p in root.rglob("*") if p.is_file())
high = allowed_n = 0
lines_out = [f"扫描根：{root}", f"文件数：{len(files)}（由 rglob 现算）", "----"]
for p in files:
    rel = p.relative_to(root)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        lines_out.append(f"READFAIL {rel} {exc}")
        continue
    for ln, line in enumerate(text.splitlines(), 1):
        for name, rx in RULES:
            for m in rx.finditer(line):
                if any(a.search(line) for a in ALLOW):
                    allowed_n += 1
                    lines_out.append(f"ALLOWED {name} {rel}:{ln} {m.group(0)[:70]!r}")
                    continue
                high += 1
                lines_out.append(f"HIGH {name} {rel}:{ln} {m.group(0)[:90]!r}")
        for m in ASSIGN.finditer(line):
            val = m.group(2)
            # 规则定义行本身（`DSN = re.compile(r"(?i)…")`）不是凭据，否则召回器会举报自己
            if "re.compile" in line or FAKE.match(val) or \
                    re.search(r"(?i)redact|\*{3,}|x{4,}|<[^>]+>|\$\{", val):
                continue
            high += 1
            lines_out.append(f"HIGH assign {rel}:{ln} {m.group(1)}={val[:40]!r}")

lines_out += ["----",
              f"HIGH 命中：{high}（ALLOWED {allowed_n}）——命中逐条见上，形状而非正文"]
print("\n".join(lines_out))
sys.exit(1 if high else 0)
