"""S3.4.1 反证电池：每一发生产代码变异都必须让**指定的那条用例**变红。

判据不是「rc≠0 就算打中」——先跑一次未变异的基线（不绿则整批判 INCONCLUSIVE），
再逐发变异跑同一批 node id，只有「红在我点名的那条上」才算 RED 命中；
红在别处、一条都没红、跑崩了（rc 既不是 0 也不是 1）都单独记账。

变异方式：**不碰工作树里的生产文件**（这是共享工作区）。
做法是读源码文本 → 替换 → 把替换后的源 exec 进一个 ModuleType →
先 `import` 真包再把 `sys.modules[模块名]` 与父包属性一起换成变异体 →
在同一个进程里 `pytest.main(node ids)`。这样 `from app.providers.article_sources.dajiala import …`
拿到的是变异体，其余模块照常。

跑法（仓库根）：
    cd apps/api && .venv/Scripts/python.exe -X utf8 ../../docs/06_validation/evidence/EVD-V2-02/mutate_s341.py
每个变异自己一个子进程（模块状态互不污染）。
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import subprocess
import sys
import types
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"  # 本件住在 docs/06_validation/evidence/EVD-V2-02/
MODULE_DIR = "app/providers/article_sources"

T = "tests/test_provider_contract.py::"
R = "tests/test_rss_provider.py::"

MUTATIONS: list[dict[str, str | list[str]]] = [
    {
        "name": "M1 dajiala 5xx 的异常类换成 DiscoveryFailedError",
        "module": "dajiala",
        "old": 'raise DependencyUnavailableError(f"Dajiala 5xx: {resp.status_code}")',
        "new": 'raise DiscoveryFailedError(f"Dajiala 5xx: {resp.status_code}")',
        "targets": [T + "test_dajiala_status_code_error_class_split"],
    },
    {
        "name": "M2 dajiala 删掉「余额不足」业务码分支",
        "module": "dajiala",
        "old": '    if "余额" in msg or "money" in msg.lower():\n'
               '        return DependencyUnavailableError(f"Dajiala 余额不足: {msg}")\n',
        "new": "",
        "targets": [T + "test_dajiala_business_code_routing"],
    },
    {
        "name": "M3 dajiala 详情正文改读 content（载荷里是 html）",
        "module": "dajiala",
        "old": '        html = data.get("html", "")',
        "new": '        html = data.get("content", "")',
        "targets": [
            T + "test_dajiala_detail_maps_every_field_from_payload",
            T + "test_dajiala_detail_content_text_is_stripped_and_capped",
        ],
    },
    {
        "name": "M4 dajiala 纯文本丢掉 200 字上限",
        "module": "dajiala",
        "old": "        content_text = _strip_html(html)[:200]",
        "new": "        content_text = _strip_html(html)",
        "targets": [T + "test_dajiala_detail_content_text_is_stripped_and_capped"],
    },
    {
        "name": "M5 dajiala 搜索把 keyword 改名成 q",
        "module": "dajiala",
        "old": '                    "keyword": keyword,',
        "new": '                    "q": keyword,',
        "targets": [T + "test_dajiala_search_maps_rows_and_sends_only_the_keyword"],
    },
    {
        "name": "M6 dajiala 详情的时间解析摘掉 try/except",
        "module": "dajiala",
        "old": '            try:\n'
               '                publish_time = datetime.fromtimestamp(int(post_time), tz=None)\n'
               '            except (ValueError, OSError):\n'
               '                pass\n',
        "new": '            publish_time = datetime.fromtimestamp(int(post_time), tz=None)\n',
        "targets": [T + "test_dajiala_detail_keeps_the_paid_body_when_the_epoch_is_out_of_range"],
    },
    {
        "name": "M7 justoneapi 详情取末行而不是首行",
        "module": "justoneapi",
        "old": "        item = items[0]",
        "new": "        item = items[-1]",
        "targets": [T + "test_justoneapi_detail_maps_first_row_and_field_aliases"],
    },
    {
        "name": "M8 justoneapi 详情参数名 articleUrl 改成 url",
        "module": "justoneapi",
        "old": '        params = {"token": self._api_key, "articleUrl": url}',
        "new": '        params = {"token": self._api_key, "url": url}',
        "targets": [T + "test_justoneapi_detail_maps_first_row_and_field_aliases"],
    },
    {
        "name": "M9 justoneapi 删掉限频业务码分支",
        "module": "justoneapi",
        "old": '    if "限频" in msg or "rate" in msg.lower():\n'
               '        return RateLimitedUpstreamError(f"JustOneAPI 限频: {msg}")\n',
        "new": "",
        "targets": [T + "test_justoneapi_discovery_error_mapping_is_the_raising_branch"],
    },
    {
        "name": "M10 tikhub 详情不再 suppress_402",
        "module": "tikhub",
        "old": '        payload = await self._handle_response(resp, "v2/fetch_article_detail_h5", suppress_402=True)',
        "new": '        payload = await self._handle_response(resp, "v2/fetch_article_detail_h5")',
        "targets": [T + "test_tikhub_degrades_to_none_on_402_and_404"],
    },
    {
        "name": "M11 tikhub 详情丢掉 html 别名",
        "module": "tikhub",
        "old": '        content_html = data.get("content", "") or data.get("html", "")',
        "new": '        content_html = data.get("content", "")',
        "targets": [T + "test_tikhub_detail_falls_back_to_html_and_text_only_payloads"],
    },
    {
        "name": "M12 wellbyte 403 的异常类换成 DiscoveryFailedError",
        "module": "wellbyte",
        "old": '            raise DependencyUnavailableError("Wellbyte 被 Cloudflare 拦截（403）：'
               '需检查 httpx TLS 指纹配置")',
        "new": '            raise DiscoveryFailedError("Wellbyte 403")',
        "targets": [T + "test_wellbyte_discovery_error_mapping_is_the_raising_branch"],
    },
    {
        "name": "M13 wellbyte 搜索丢掉 sortType 兜底",
        "module": "wellbyte",
        "old": '            "sortType": _SORT_MAP.get(sort, "LATEST"),',
        "new": '            "sortType": _SORT_MAP.get(sort, ""),',
        "targets": [T + "test_wellbyte_search_translates_sort_and_time_range"],
    },
    {
        "name": "M14 wellbyte 把 null source 兜住（= 修掉那条缺陷见证）",
        "module": "wellbyte",
        "old": '            source_info = item.get("source", {})',
        "new": '            source_info = item.get("source") or {}',
        "targets": [T + "test_wellbyte_search_crashes_on_null_source_defect_witness"],
    },
    {
        "name": "M15 详情时间改成 tz=UTC（= 修掉时区缺陷，绊线必须红）",
        "module": "dajiala",
        "old": "                publish_time = datetime.fromtimestamp(int(post_time), tz=None)",
        "new": "                publish_time = datetime.fromtimestamp(int(post_time), tz=timezone.utc)",
        "prelude": "from datetime import timezone\n",
        "targets": [T + "test_provider_timestamps_are_naive_local_while_the_frozen_contract_demands_aware"],
    },
    {
        "name": "M16 wellbyte 时间改成 tz=UTC（同一族绊线）",
        "module": "wellbyte",
        "old": "                    publish_time = datetime.fromtimestamp(int(dt), tz=None)",
        "new": "                    publish_time = datetime.fromtimestamp(int(dt), tz=timezone.utc)",
        "prelude": "from datetime import timezone\n",
        "targets": [T + "test_provider_timestamps_are_naive_local_while_the_frozen_contract_demands_aware"],
    },
    {
        "name": "M17 aclose 不再判归属（把注入的客户端也关掉）",
        "module": "dajiala",
        "old": "    async def aclose(self) -> None:\n        if self._owns_http:\n            await self._http.aclose()",
        "new": "    async def aclose(self) -> None:\n        await self._http.aclose()",
        "targets": [T + "test_owned_http_client_is_closed_and_injected_one_is_not"],
    },
    {
        "name": "M18 rss 丢掉单 feed 条数封顶",
        "module": "rss",
        "old": "        items = items[:_MAX_ITEMS_PER_FEED]",
        "new": "        items = list(items)",
        "targets": [R + "TestFetchPath::test_item_cap_bounds_one_feed"],
    },
]

ALL_TARGETS = sorted({target for m in MUTATIONS for target in m["targets"]})  # type: ignore[type-arg]


# ── worker：单个变异 + 指定 node id ────────────────────────────────────────


def _load_mutant(module_key: str, old: str, new: str, prelude: str = "") -> types.ModuleType:
    path = API / MODULE_DIR / f"{module_key}.py"
    source = path.read_text(encoding="utf-8")
    hits = source.count(old)
    if hits != 1:
        raise SystemExit(f"INCONCLUSIVE 变异锚点在 {module_key}.py 出现 {hits} 次（要求恰好 1 次）：{old!r}")
    mutated = source.replace(old, new)
    if prelude:
        mutated = mutated.replace("from __future__ import annotations\n",
                                  "from __future__ import annotations\n" + prelude, 1)
    ast.parse(mutated)  # 语法不过就不是「等价变异」，直接判作废
    name = f"app.providers.article_sources.{module_key}"
    import importlib

    importlib.import_module(name)  # 先让真包与父包就位，再原地替换
    mutant = types.ModuleType(name)
    mutant.__file__ = str(path)
    mutant.__package__ = "app.providers.article_sources"
    sys.modules[name] = mutant
    exec(compile(mutated, str(path), "exec"), mutant.__dict__)  # noqa: S102  变异体本就是要执行的
    setattr(sys.modules["app.providers.article_sources"], module_key, mutant)
    return mutant


def run_worker(spec: dict[str, object]) -> int:
    import pytest

    _load_mutant(
        str(spec["module"]), str(spec["old"]), str(spec["new"]), str(spec.get("prelude", ""))
    )
    args = [str(t) for t in spec["targets"]] + ["-q", "-p", "no:cacheprovider", "--no-cov", "--tb=no", "-rf"]
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        rc = pytest.main(args)
    print("OUTPUT>>>" + json.dumps(buffer.getvalue(), ensure_ascii=False))
    return int(rc)


# ── orchestrator ───────────────────────────────────────────────────────────


def run_baseline() -> tuple[int, str]:
    import pytest

    args = ALL_TARGETS + ["-q", "-p", "no:cacheprovider", "--no-cov", "--tb=no", "-rf"]
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        rc = pytest.main(args)
    return int(rc), buffer.getvalue()


def main() -> int:
    if len(sys.argv) > 1:  # worker 模式
        spec = MUTATIONS[int(sys.argv[1])]
        return run_worker(spec)

    base_rc, base_out = run_baseline()
    print(f"基线（{len(ALL_TARGETS)} 条被点名用例，未变异）：rc={base_rc}")
    if base_rc != 0:
        print("❌ 基线不绿 ⇒ 下面每一发的 RED 都无从解释，整批判 INCONCLUSIVE")
        print(base_out[-1500:])
        return 2

    red = green_but_expected_red = crashed = 0
    for index, spec in enumerate(MUTATIONS):
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), str(index)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(API),
        )
        payload = proc.stdout or ""
        blob = payload.partition("OUTPUT>>>")[2] or "{}"
        try:
            out = json.loads(blob)
        except json.JSONDecodeError:
            out = payload + proc.stderr
        rc = proc.returncode
        failed = sorted({line.split(" ")[1].split(" ")[0] for line in out.splitlines() if line.startswith("FAILED ")})
        named = {t for t in spec["targets"]}  # type: ignore[union-attr]
        hit = [f for f in failed if any(f.startswith(t) or t in f for t in named)]
        if rc == 0:
            verdict = "GREEN ❌ 这发没被任何点名用例抓到"
            green_but_expected_red += 1
        elif rc == 1:
            if hit:
                verdict = f"RED ✅ 红在点名用例（{len(hit)} 条）"
                red += 1
            else:
                verdict = "RED ⚠️ 有用例红但不在点名的那条上"
                crashed += 1
        else:
            verdict = f"rc={rc} INCONCLUSIVE（跑崩/收集失败）"
            crashed += 1
        print(f"── {spec['name']}\n   {verdict}")
        for line in failed[:6]:
            print(f"     · {line}")

    print(f"\n合计：RED 命中 {red} / 未抓到 {green_but_expected_red} / 可疑 {crashed}"
          f"，共 {len(MUTATIONS)} 发")
    return 0 if green_but_expected_red == 0 and crashed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
