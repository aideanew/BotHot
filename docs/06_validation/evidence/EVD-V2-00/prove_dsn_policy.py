"""S0.1.2 的本机机器证明（纯 stdlib，不启动任何服务）。

为什么不能 `import conftest`：按「本项目无需安装开发环境和依赖」约束，本机没有
sqlalchemy / dotenv / pytest，而 `apps/api/tests/conftest.py` 在模块级 import 它们。
做法：用 `ast` 取 conftest 的**模块前缀**（第一个带装饰器的函数之前的全部语句），
只剔除三方 import，其余原样 `exec`——被执行的是文件当前的真实代码，不是抄本。

复算：`python docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py`（cwd 任意）

复算：`python docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py`（cwd 任意）

判定：全部断言通过打印 `ALL PASS`，否则退出码 1 并打印首个失败项。
反证：`… prove_dsn_policy.py --self-test` 构造变异体（广播语句改回旧实现 `setdefault`），
必须让新断言变红——证明它「能失败」而非永真（G-23）。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # 缺省 UTF-8：Windows 控制台按 GBK 编码打印 ⇒ 会抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8")  # ty: ignore[unresolved-attribute]

ROOT = Path(__file__).resolve().parents[4]
CONF = ROOT / "apps" / "api" / "tests" / "conftest.py"
VAR = "AIDEANBOT_TEST_PG_DSN"
THIRD_PARTY = {"pytest", "dotenv", "sqlalchemy"}

FAILURES: list[str] = []
CHECKS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (CHECKS if ok else FAILURES).append(f"{'PASS' if ok else 'FAIL'} {label}{f' :: {detail}' if detail else ''}")


def exec_prefix(fake_file: Path, environ: dict[str, str], dotenv_stub=None, src_text: str | None = None) -> dict:
    """把 conftest 的模块前缀 exec 成独立命名空间；fake_file 只用于定位 `.env`。

    `src_text` 用于注入**变异体**源码（见 --self-test），默认注入文件当前内容。
    """
    tree = ast.parse(src_text if src_text is not None else CONF.read_text(encoding="utf-8"))
    body = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
            break  # 第一个夹具起，后续都依赖 pytest/sqlalchemy
        if isinstance(node, ast.Import):
            mods = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [(node.module or "").split(".")[0]]
        else:
            mods = []
        if any(m in THIRD_PARTY for m in mods):
            continue
        body.append(node)
    ns: dict = {"__file__": str(fake_file), "__name__": "conftest_prefix", "os": os}
    ns["dotenv_values"] = dotenv_stub or (lambda _p: {})
    code = compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(CONF), "exec")
    # 只临时改这一个变量：清空整个环境会让 Windows 的 _overlapped/Winsock 初始化失败
    # （实测 OSError [WinError 10106]），那会让证明跑不出真实分支。
    saved = os.environ.pop(VAR, None)
    os.environ.update(environ)
    try:
        exec(code, ns)
        ns["_broadcast"] = os.environ.get(VAR)  # exec 结束前的实际广播值
    finally:
        os.environ.pop(VAR, None)
        if saved is not None:
            os.environ[VAR] = saved
    return ns


def self_test(fake_conftest: Path) -> int:
    """G-23 反证：断言必须「能红」。把广播语句改回 setdefault（旧实现），
    S0.1.2-p（空串入口）与 S0.1.2-s（带空白入口）都应变红——否则新断言是空洞的。
    """
    src = CONF.read_text(encoding="utf-8")
    live = "os.environ[_TEST_PG_ENV_VAR] = PG_URL"
    if live not in src:
        print("FAIL 反证前提：conftest 里找不到赋值语句，无法构造变异体")
        return 1
    mutant = src.replace(live, "os.environ.setdefault(_TEST_PG_ENV_VAR, PG_URL)", 1)
    test_dsn = "postgresql+psycopg://bothot:bothot_ci@localhost:5547/bothot_test"
    cases = [
        ("S0.1.2-p 空串 env 广播拒连地址", {VAR: ""}, "refused"),
        ("S0.1.2-s 带空白 env 广播剥离值", {VAR: f"  {test_dsn}  "}, test_dsn),
    ]
    rc = 0
    for label, environ, expected in cases:
        real_ns = exec_prefix(fake_conftest, environ, src_text=src)
        real = real_ns["_broadcast"]
        got = exec_prefix(fake_conftest, environ, src_text=mutant)["_broadcast"]
        want = real_ns["_REFUSED_PG_URL"] if expected == "refused" else expected
        ok_real, ok_mutant = real == want, got == want
        print(f"{'OK ' if ok_real and not ok_mutant else 'BAD'} {label}"
              f"：现行={real!r}（断言成立）｜setdefault 变异体={got!r}（断言{'未变红 ⇒ 空洞！' if ok_mutant else '变红'}）")
        if not (ok_real and not ok_mutant):
            rc = 1
    print("SELF-TEST " + ("PASS：两条新断言对旧实现敏感" if rc == 0 else "FAIL"))
    return rc


def iso_unsets() -> int:
    """在「两个 DSN 均已清除」的进程里跑 f/l/m/n 四条。

    `_resolve_test_pg_url()` 在 `exec_prefix` 返回**之后**才被调用，那一刻 ambient env
    已经恢复；带 DSN 的开发机/CI 会读到真实值，这四条必 FAIL（P-43 的 4 FAIL 复现）。
    子进程把隔离边界放在进程级：父进程即使带着 DSN，也传不进这里。
    """
    for name in (VAR, "DATABASE_URL"):
        os.environ.pop(name, None)
    tmp = Path(tempfile.mkdtemp(prefix="evdv200-iso-"))
    fake_tests = tmp / "apps" / "api" / "tests" / "conftest.py"
    fake_tests.parent.mkdir(parents=True)

    ns_unset = exec_prefix(fake_tests, {})
    dsn, source = ns_unset["_resolve_test_pg_url"]()
    check("S0.1.2-f 未配置返回空串", (dsn, source) == ("", "unset"), f"{dsn!r},{source}")

    ns_blank = exec_prefix(fake_tests, {VAR: "   "})
    blank_dsn, blank_src = ns_blank["_resolve_test_pg_url"]()
    check("S0.1.2-l 纯空白 env 视为未配置", (blank_dsn, blank_src) == ("", "unset"),
          f"{blank_dsn!r},{blank_src}")

    env_file = tmp / "apps" / "api" / ".env"
    env_file.write_text("AIDEANBOT_TEST_PG_DSN=x\n", encoding="utf-8")
    file_dsn = "postgresql+psycopg://bothot:bothot_ci@localhost:5547/bothot_from_env_file"
    ns_file = exec_prefix(tmp / "apps" / "api" / "tests" / "conftest.py",
                          {}, dotenv_stub=lambda _p: {VAR: file_dsn})
    got, src2 = ns_file["_resolve_test_pg_url"]()
    check("S0.1.2-m .env 层解析并广播该值",
          (got, src2) == (file_dsn, "file:.env") and ns_file["_broadcast"] == file_dsn,
          f"{got},{src2},broadcast={ns_file['_broadcast']!r}")
    ns_file_blank = exec_prefix(tmp / "apps" / "api" / "tests" / "conftest.py",
                                {}, dotenv_stub=lambda _p: {VAR: ""})
    check("S0.1.2-n .env 空值视为未配置", ns_file_blank["_resolve_test_pg_url"]() == ("", "unset"))

    for line in CHECKS:
        print(line)
    if FAILURES:
        print("\n".join(FAILURES))
        return 1
    return 0


def run_iso_unsets() -> None:
    env = {k: v for k, v in os.environ.items() if k not in (VAR, "DATABASE_URL")}
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--iso-unsets"],
                          env=env, capture_output=True, text=True, encoding="utf-8")
    parsed = 0
    for line in proc.stdout.splitlines():
        if line.startswith(("PASS ", "FAIL ")):
            (CHECKS if line.startswith("PASS ") else FAILURES).append(line)
            parsed += 1
        elif line.strip():
            CHECKS.append(f"  INFO iso-unsets 子进程输出：{line}")
    if proc.returncode != 0 and parsed == 0:
        FAILURES.append(f"FAIL S0.1.2 f/l/m/n 子进程隔离检查异常 rc={proc.returncode} "
                        f":: {(proc.stderr or proc.stdout).strip()[-300:]}")


def main() -> int:
    src = CONF.read_text(encoding="utf-8")

    if "--iso-unsets" in sys.argv[1:]:
        return iso_unsets()

    if "--self-test" in sys.argv[1:]:
        st_tmp = Path(tempfile.mkdtemp(prefix="evdv200-st-")) / "apps" / "api" / "tests"
        st_tmp.mkdir(parents=True)
        return self_test(st_tmp / "conftest.py")

    # 卡片反证 ①：默认生产 DSN 常量必须彻底消失
    check("S0.1.2-a `_DEFAULT_PG_URL` 已删除", "_DEFAULT_PG_URL" not in src,
          f"grep -c 命中 {src.count('_DEFAULT_PG_URL')}")
    check("S0.1.2-b 生产形态字面量不再出现在 conftest", "bothot:bothot@localhost:5433" not in src,
          f"字面量命中 {src.count('bothot:bothot@localhost:5433')} 处（期望 0）")

    tmp = Path(tempfile.mkdtemp(prefix="evdv200-"))
    fake_tests = tmp / "apps" / "api" / "tests" / "conftest.py"
    fake_tests.parent.mkdir(parents=True)

    # f/l/m/n 在子进程里跑：本进程此时可能带着 ambient DSN，且 `_resolve_test_pg_url()`
    # 是在 exec_prefix 隔离窗口关闭后才调用的（P-43）。
    run_iso_unsets()

    # ② 环境变量显式配置 ⇒ env 层胜出，且向下游广播同一值（不覆盖显式值）
    test_dsn = "postgresql+psycopg://bothot:bothot_ci@localhost:5547/bothot_test"
    ns = exec_prefix(fake_tests, {VAR: test_dsn})
    check("S0.1.2-c env 层解析", ns["PG_URL"] == test_dsn, f"PG_URL={ns['PG_URL']}")
    check("S0.1.2-d env 层来源标注", ns["_PG_URL_SOURCE"] == f"env:{VAR}", ns["_PG_URL_SOURCE"])
    check("S0.1.2-e 广播值=配置值（下游 9 处回退点被该环境变量屏蔽）",
          ns["_broadcast"] == test_dsn, f"_broadcast={ns['_broadcast']!r}")

    # ③ 完全未配置 ⇒ 空串 + unset + PG_URL 落到必然拒连地址，且绝不含 5433；
    #    广播值必须是拒连地址（这是「下游 9 处自带生产字面量」被屏蔽的唯一机制）
    ns_unset = exec_prefix(fake_tests, {})
    check("S0.1.2-g 未配置时 PG_URL=拒连地址", ns_unset["PG_URL"] == ns_unset["_REFUSED_PG_URL"],
          ns_unset["PG_URL"])
    check("S0.1.2-h 未配置时广播值=拒连地址（非生产形态）",
          ns_unset["_broadcast"] == ns_unset["_REFUSED_PG_URL"]
          and "5433" not in ns_unset["_broadcast"], f"_broadcast={ns_unset['_broadcast']!r}")
    check("S0.1.2-i 拒连地址不含部署端口", "5433" not in ns_unset["PG_URL"] and ":1/" in ns_unset["PG_URL"],
          ns_unset["PG_URL"])
    check("S0.1.2-j skip 原因含「未设置」", "未设置" in ns_unset["SKIP_UNSET_REASON"],
          ns_unset["SKIP_UNSET_REASON"])
    check("S0.1.2-k skip 原因不含「不可达」（避免触中 ci.yml:148 的 PG-不可达门禁）",
          "不可达" not in ns_unset["SKIP_UNSET_REASON"])

    # ④ 空白值等价于未配置（`AIDEANBOT_TEST_PG_DSN=" "` 不得泄漏成连接目标）
    ns_blank = exec_prefix(fake_tests, {VAR: "   "})

    # ④b 广播必须无条件覆盖：`setdefault` 在「键存在但为空串」时是空操作，下游 9 处
    #     会拿到空串（SQLAlchemy 报 URL 解析错，而不是设计中的连接被拒），且本模块
    #     解析出的规范化值丢失。此组断言对 setdefault 实现必然失败（可反证非空洞）。
    ns_empty = exec_prefix(fake_tests, {VAR: ""})
    check("S0.1.2-p 空串 env 也广播为拒连地址（赋值而非 setdefault）",
          ns_empty["_broadcast"] == ns_empty["_REFUSED_PG_URL"],
          f"_broadcast={ns_empty['_broadcast']!r}")
    check("S0.1.2-q 纯空白 env 广播拒连地址",
          ns_blank["_broadcast"] == ns_blank["_REFUSED_PG_URL"],
          f"_broadcast={ns_blank['_broadcast']!r}")
    check("S0.1.2-r 三种入口的广播值均非空串（下游永远不会读到 \"\"）",
          all(n["_broadcast"] for n in (ns_unset, ns_empty, ns_blank)),
          "｜".join(f"{n['_broadcast']!r}" for n in (ns_unset, ns_empty, ns_blank)))
    ns_padded = exec_prefix(fake_tests, {VAR: f"  {test_dsn}  "})
    check("S0.1.2-s 带空白的配置广播为剥离后的值",
          ns_padded["_broadcast"] == test_dsn, f"_broadcast={ns_padded['_broadcast']!r}")

    # ⑤ .env 命中与 .env 空值（S0.1.2-m / -n）已在 iso 子进程里跑完：
    #    `_resolve_test_pg_url()` 必须在「两个 DSN 都清掉」的进程里调用。

    # ⑥ 下游自带生产字面量回退的模块清单（旧注释写「7 个」，需机器复核）
    tests_dir = ROOT / "apps" / "api" / "tests"
    sites = []
    for py in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and len(node.args) == 2
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value == VAR):
                dflt = node.args[1]
                text = ast.unparse(dflt)
                sites.append((py.name, node.lineno, "5433" in text))
    prod = [s for s in sites if s[2]]
    check(f"S0.1.2-o 下游自带默认回退点={len(sites)}（其中生产形态 {len(prod)}）；旧注释称 7 ⇒ 钉死为 9",
          len(sites) == len(prod) == 9,
          f"实测 {len(sites)} 处、生产形态 {len(prod)} 处；期望恰 9（数量变动须同步 §3.2 表）")
    for name, lineno, is_prod in sites:
        CHECKS.append(f"  INFO 回退点 {name}:{lineno} 生产形态={is_prod}")

    # ⑦ 第 10 类消费者：不经环境变量、直接 `from conftest import PG_URL`。
    #     扫描口径必须覆盖它，否则「已列全」是假的（本轮复审指出的盲区）。
    direct = []
    for py in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.ImportFrom) and node.module == "conftest"
                    and any(a.name == "PG_URL" for a in node.names)):
                direct.append((py.name, node.lineno))
    check("S0.1.2-t 直接 import conftest.PG_URL 的模块已被清点（现恰 1 处）",
          [n for n, _ in direct] == ["test_chat_sse.py"],
          f"实测 {direct}；数量或归属变动须同步 §3.2 表")
    for name, lineno in direct:
        CHECKS.append(f"  INFO 直接消费者 {name}:{lineno}（值=conftest 解析结果，未配置时=拒连地址）")

    for line in CHECKS:
        print(line)
    if FAILURES:
        print("\n".join(FAILURES))
        print(f"RESULT FAIL ({len(FAILURES)})")
        return 1
    print(f"ALL PASS ({len([c for c in CHECKS if c.startswith('PASS')])} 断言，"
          f"回退点 {len(sites)} 个已列举)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
