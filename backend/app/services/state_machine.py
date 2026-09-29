"""持久化状态机（B-T4）：流转表数据驱动，非法流转 → 30005。

域状态定义（entities.py 注释为契约）：
- job:       QUEUED → RUNNING → SUCCEEDED / PARTIAL_SUCCESS / FAILED
             QUEUED → CANCELLED（用户主动取消）；RUNNING 不设 CANCELLED 出边——已投入
             执行的作业不半途作废，由 worker 自然收敛（否则半批结果无人对账）
             终态 → QUEUED（重试/崩溃自愈的重新入队；由 retry/requeue 路径直写，
             不经本表校验——worker 只认领 QUEUED，终态 Job 若直置 RUNNING 会对 worker 隐形）
- document:  FETCHED → INDEXED → READY；任一阶段可失败（FAILED），FAILED 可重入 FETCHED
"""

from __future__ import annotations

from app.core.errors import JobStateInvalidError

ALLOWED_TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "job": {
        "QUEUED": {"RUNNING", "CANCELLED"},
        "RUNNING": {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"},
    },
    "document": {
        "FETCHED": {"INDEXED", "FAILED"},
        "INDEXED": {"READY", "FAILED"},
        "FAILED": {"FETCHED"},  # 失败重试
    },
}


def validate_transition(domain: str, old_status: str, new_status: str) -> None:
    """校验一次状态流转；非法 → 30005（JobStateInvalidError，409）。"""
    table = ALLOWED_TRANSITIONS.get(domain)
    if table is None:
        raise JobStateInvalidError(f"未知状态机域: {domain}")
    if new_status not in table.get(old_status, set()):
        raise JobStateInvalidError(f"{domain} 非法流转: {old_status} → {new_status}")


def can_transition(domain: str, old_status: str, new_status: str) -> bool:
    """无异常版（查询/预判场景）。"""
    try:
        validate_transition(domain, old_status, new_status)
    except JobStateInvalidError:
        return False
    return True
