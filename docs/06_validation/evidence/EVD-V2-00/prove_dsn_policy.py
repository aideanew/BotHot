"""S0.1.2 的本机机器证明（纯 stdlib，不启动任何服务）。

为什么不能 `import conftest`：按「本项目无需安装开发环境和依赖」约束，本机没有
sqlalchemy / dotenv / pytest，而 `apps/api/tests/conftest.py` 在模块级 import 它们。
做法：用 `ast` 取 conftest 的**模块前缀**（第一个带装饰器的函数之前的全部语句），
只剔除三方 import，其余原样 `exec`——被执行的是文件当前的真实代码，不是抄本。

复算：`python docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py`（cwd 任意）

判定：全部断言通过打印 `ALL PASS`，否则退出码 1 并打印首个失败项。
"""

from __future__ import annotations

import ast
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CONF = ROOT / "apps" / "api" / "tests" / "conftest.py"
VAR = "AIDEANBOT_TEST_PG_DSN"
THIRD_PARTY = {"pytest", "dotenv", "sqlalchemy"}

FAILURES: list[str] = []
CHECKS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (CHECKS if ok else FAILURES).append(f"{'PASS' if ok else 'FAIL'} {label}{f' :: {detail}' if detail else ''}")


def exec_prefix(fake_file: Path, environ: dict[str, str], dotenv_stub=None) -> dict:
    """把 conftest 的模块前缀 exec 成独立命名空间；fake_file 只用于定位 `.env`。"""
    tree = ast.parse(CONF.read_text(encoding="utf-8"))
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


def main() -> int:
    src = CONF.read_text(encoding="utf-8")

    # 卡片反证 ①：默认生产 DSN 常量必须彻底消失
    check("S0.1.2-a `_DEFAULT_PG_URL` 已删除", "_DEFAULT_PG_URL" not in src,
          f"grep -c 命中 {src.count('_DEFAULT_PG_URL')}")
    check("S0.1.2-b 生产形态字面量不再出现在 conftest", "bothot:bothot@localhost:5433" not in src,
          "conftest 仍含口令字面量")

    tmp = Path(tempfile.mkdtemp(prefix="evdv200-"))
    fake_tests = tmp / "apps" / "api" / "tests" / "conftest.py"
    fake_tests.parent.mkdir(parents=True)

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
    dsn, source = ns_unset["_resolve_test_pg_url"]()
    check("S0.1.2-f 未配置返回空串", (dsn, source) == ("", "unset"), f"{dsn!r},{source}")
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
    blank_dsn, blank_src = ns_blank["_resolve_test_pg_url"]()
    check("S0.1.2-l 纯空白 env 视为未配置", (blank_dsn, blank_src) == ("", "unset"),
          f"{blank_dsn!r},{blank_src}")

    # ⑤ 只有 .env 命中 ⇒ file 层胜出并向下游广播该值
    #   （dotenv_values 被替换为 stub：本证明覆盖的是 conftest 的分层与广播逻辑，
    #     python-dotenv 的解析正确性属三方库，不在本机可证范围）
    env_file = tmp / "apps" / "api" / ".env"
    env_file.write_text("AIDEANBOT_TEST_PG_DSN=x\n", encoding="utf-8")
    file_dsn = "postgresql+psycopg://bothot:bothot_ci@localhost:5547/bothot_from_env_file"
    ns_file = exec_prefix(tmp / "apps" / "api" / "tests" / "conftest.py",
                          {}, dotenv_stub=lambda _p: {VAR: file_dsn})
    got, src2 = ns_file["_resolve_test_pg_url"]()
    check("S0.1.2-m .env 层解析并广播该值",
          (got, src2) == (file_dsn, "file:.env") and ns_file["_broadcast"] == file_dsn,
          f"{got},{src2},broadcast={ns_file['_broadcast']!r}")
    # .env 里是空值 ⇒ 仍算未配置（防止 `AIDEANBOT_TEST_PG_DSN=` 把生产回退还绕出来）
    ns_file_blank = exec_prefix(tmp / "apps" / "api" / "tests" / "conftest.py",
                                {}, dotenv_stub=lambda _p: {VAR: ""})
    check("S0.1.2-n .env 空值视为未配置", ns_file_blank["_resolve_test_pg_url"]() == ("", "unset"))

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
    check(f"S0.1.2-o 下游自带默认回退点={len(sites)}（其中生产形态 {len(prod)}）；旧注释称 7",
          len(sites) == len(prod) and len(sites) >= 1,
          "存在非生产形态默认值，需复核")
    for name, lineno, is_prod in sites:
        CHECKS.append(f"  INFO 回退点 {name}:{lineno} 生产形态={is_prod}")

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
