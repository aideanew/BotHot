"""STEP-16：告警启用姿态的默认值与启动宽限（V0.7.0 新增）。

三条用例都**不连库**，因此本机与无 PG 的 CI 都能真跑（不是 skip）——
这是刻意的：STEP-16 判的是"默认配置下探测器会不会被跑到"，与数据库无关；
把它写成连库用例就等于在无边跑的环境里永远绿（规划 V0.7.0 01 F-88 那类假绿）。

被保护的两条既有约束（改动本模块前务必先读）：
- `test_alerting_drill.py:139` 明确断言「`ALERTING_ENABLED` 未置真 ⇒ 零探测零投递」
  ⇒ **代码层默认必须是 False**，部署层的开启走 compose/env。
- `test_alerting_drill.py:123` 断言进程刚启动就能三探针全命中
  ⇒ **宽限的代码默认必须是 0**，非零默认会让那条既有用例在"刚起即在宽限内"时变红。
本文件把这两条约束钉成用例，防止后来人"顺手把默认改成 true/600"。
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core import alerting


class _FakeSession:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeFactory:
    """run_alert_checks 只把 factory 传给被 monkeypatch 掉的探测函数，不真的触库。"""

    def __call__(self) -> _FakeSession:
        return _FakeSession()


@pytest.fixture(autouse=True)
def _isolate_alert_state(monkeypatch: pytest.MonkeyPatch):
    """冷却状态是进程内 dict：不清就会让相邻用例互相污染（第二条莫名被抑制）。

    同时把 ALERT_COOLDOWN_SECONDS 显式设 0——本文件除冷却用例外都只关心宽限与默认值，
    宿主机若已导出该变量会让结果随环境漂（"同一命令换台机器结论不同"）。
    """
    alerting.reset_alert_cooldown_state()
    monkeypatch.setenv("ALERT_COOLDOWN_SECONDS", "0")
    yield
    alerting.reset_alert_cooldown_state()


def _repo_file(rel: str) -> str:
    # 从本文件向上定位仓库根，避免依赖 cwd（本机 win32 / CI linux 皆可跑）
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / rel
        if cand.is_file():
            return cand.read_text(encoding="utf-8")
    pytest.fail(f"未找到 {rel}（仓库根定位失败）")


def test_compose_and_env_example_default_alerting_on() -> None:
    """部署层默认必须开启：compose 的 `${ALERTING_ENABLED:-true}` 与 .env.example 的 =true。

    判据写成"读磁盘上的配置"而不是"读 os.environ"，因为本卡要防的正是配置默认值；
    也刻意不做 YAML 解析（pyyaml 不是必装依赖，用文本正则即可钉住这一行）。
    """
    compose = _repo_file("docker/compose.yml")
    assert re.search(r"ALERTING_ENABLED=\$\{ALERTING_ENABLED:-true\}", compose), (
        "docker/compose.yml 里 ALERTING_ENABLED 的默认值不再是 true ⇒ 探测器在默认部署里不跑，"
        "STEP-05 的『静默缺陷一天内被发现』前提再次失效（见规划 V0.7.0 01 F-83）"
    )
    env = _repo_file("docker/.env.example")
    assert re.search(r"^ALERTING_ENABLED=true\s*$", env, re.M), (
        "docker/.env.example 的 ALERTING_ENABLED 应为 true——样例文件写 false 会让使用者照抄成关"
    )


def test_compose_sets_startup_grace_and_cooldown() -> None:
    """翻默认值必须同时配降噪参数：宽限管发版首拍，冷却管"每 60s 重投同一条"。

    这条存在的全部理由：`run_alert_checks` 由推送调度循环每 60 秒调一次
    （`services/push_scheduler.py:88-92`）。只开 `ALERTING_ENABLED=true` 而不配冷却，
    等于让一条持续积压每分钟投一条站内通知——告警系统自己变成故障源。
    """
    compose = _repo_file("docker/compose.yml")
    assert re.search(r"ALERT_STARTUP_GRACE_SECONDS=\$\{ALERT_STARTUP_GRACE_SECONDS:-[1-9]\d*\}", compose), (
        "compose 没给 ALERT_STARTUP_GRACE_SECONDS 一个非零默认 ⇒ 每次滚动发布都会误报心跳缺失"
    )
    assert re.search(r"ALERT_COOLDOWN_SECONDS=\$\{ALERT_COOLDOWN_SECONDS:-[1-9]\d*\}", compose), (
        "compose 没给 ALERT_COOLDOWN_SECONDS 非零默认 ⇒ 告警按 60s 调度周期重投，刷屏到被关掉为止"
    )
    env = _repo_file("docker/.env.example")
    assert re.search(r"^ALERT_COOLDOWN_SECONDS=[1-9]\d*\s*$", env, re.M), ".env.example 应同步给冷却默认"


def test_startup_grace_defaults_to_zero_in_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """代码层宽限默认 0：非零默认会吃掉 test_alerting_drill 的「刚启动即三探针全命中」。"""
    monkeypatch.delenv("ALERT_STARTUP_GRACE_SECONDS", raising=False)
    assert alerting.in_startup_grace() is False, (
        "宽限的代码默认被改成非零 ⇒ 任何进程启动头 N 秒内心跳告警全被抑制，"
        "既有的三探针用例会在刚起时变红；部署侧的 600 应只写在 compose/env"
    )
    monkeypatch.setenv("ALERT_STARTUP_GRACE_SECONDS", "600")
    assert alerting.in_startup_grace() is True, "配了宽限却没生效，compose 里那行等于没写"


async def test_grace_suppresses_heartbeat_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """宽限内：心跳告警被抑制，但积压/连败照报（它们是数据事实，与进程新旧无关）。

    变异反证（卡面 S16.1.2.1 的判据本体）：
    - 把 `elif stale:` 改回 `if stale:`（不判宽限）⇒ 本用例红（多了一条心跳告警）。
    - 把宽限误施到全部三类（在函数开头直接 return []）⇒ 本用例红（少了「Job 积压」）。
    """
    monkeypatch.setenv("ALERTING_ENABLED", "1")
    monkeypatch.setenv("ALERT_STARTUP_GRACE_SECONDS", "600")
    monkeypatch.setattr(alerting, "check_heartbeat_missing", lambda session: _stub(["scheduler"]))
    monkeypatch.setattr(alerting, "check_job_backlog", lambda session: _stub(999))
    monkeypatch.setattr(alerting, "check_push_consecutive_failures", lambda session, window: _stub(False))

    delivered: list[str] = []

    async def _capture(title: str, message: str) -> bool:
        delivered.append(title)
        return True

    monkeypatch.setattr(alerting, "_deliver", _capture)

    fired = await alerting.run_alert_checks(_FakeFactory())

    assert fired == ["Job 积压"], f"宽限应只压掉心跳告警，实得 {fired!r}"
    assert delivered == ["BotHot 告警：Job 积压"], f"投递应与 fired 一致，实得 {delivered!r}"


async def _stub(value: object) -> object:
    """把三个探测函数换成同步可 monkeypatch 的协程工厂（探测本身不在本卡射程）。"""
    return value


async def test_cooldown_delivers_once_then_suppresses_same_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """冷却期内同一条告警只投一次；第二次被抑制，但探测本身继续跑（不是整条链路关掉）。

    变异反证：
    - 把 `allow_alert` 写成恒 True ⇒ 第二次仍投递 ⇒ 本用例红（刷屏风险回来了）。
    - 把冷却实现成"冷却期内 run_alert_checks 直接 return []" ⇒ 第一次的 fired 也会被吃掉
      或第二次连积压探测都不跑，本用例同样红。
    """
    monkeypatch.setenv("ALERTING_ENABLED", "1")
    monkeypatch.setenv("ALERT_COOLDOWN_SECONDS", "1800")
    monkeypatch.setattr(alerting, "check_heartbeat_missing", lambda session: _stub([]))
    monkeypatch.setattr(alerting, "check_job_backlog", lambda session: _stub(999))
    monkeypatch.setattr(alerting, "check_push_consecutive_failures", lambda session, window: _stub(False))

    delivered: list[str] = []

    async def _capture(title: str, message: str) -> bool:
        delivered.append(title)
        return True

    monkeypatch.setattr(alerting, "_deliver", _capture)

    first = await alerting.run_alert_checks(_FakeFactory())
    second = await alerting.run_alert_checks(_FakeFactory())

    assert first == ["Job 积压"], f"首轮应投一条积压告警，实得 {first!r}"
    assert second == [], f"冷却期内同一条告警不该重投，实得 {second!r}"
    assert delivered == ["BotHot 告警：Job 积压"], f"投递应恰好一条，实得 {delivered!r}"
