"""运营可配置项的读写面（STEP-28 S28.1.2；形状与不变量见 ADR-0013）。

读侧刻意分成两个函数，因为它们服务的对象不同：

- `refresh(session)` / `get(session, key)` 是**异步**的，只有握着会话的调用方能动库；
- `peek(key)` 是**同步**的，被 `registry` 与 `categorizer` 那两个"签名不变"的读函数调用。
  它只读进程内快照，**绝不发起 IO**——同步函数不能 await，而"顺手同步查一次库"会把
  一次网络往返放进事件循环里，那正是 STEP-00H 刚收口的病（探针/入库被外部依赖卡住）。

代价写在 ADR-0013 §5：快照不是广播，各进程最多落后 TTL 一秒数；所以"下一轮生效"这句话
靠的是**每轮开头刷一次**（scheduler / worker 各一行接线），不是靠 `peek()` 实时。

`put()` 自己 commit——与本仓其它 Service 一致（`engine_keys.py:123` 等）。
`get_db` 在请求结束统一回滚，所以写侧不自提交的话，"接口返回 200 但库里没行"
会读遍所有测试都看不见（测试夹具里 savepoint 一释放就照样查得到）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RequestInvalidError
from app.models.bothot_entities import SystemSetting
from app.models.entities import User

logger = structlog.get_logger(__name__)

DISCOVERY_KEY = "discovery"
CATEGORIES_KEY = "categories"
# 白名单是这张表不变成垃圾抽屉的唯一防线（ADR-0013 §3 的承重墙）：
# 没登记的键读不到、写不进，只能在这里显式加。
KNOWN_KEYS: frozenset[str] = frozenset({DISCOVERY_KEY, CATEGORIES_KEY})
SNAPSHOT_TTL_SECONDS = 60.0  # 卡面上界；跨进程一致性的代价就写在这个数上

_DEFAULT_CATEGORY = "其他"  # categorizer.DEFAULT_CATEGORY 的镜像，见下方注释


class DiscoveryConfig(BaseModel):
    """`discovery` 键的值：启用哪些渠道 + 默认渠道。

    `extra="forbid"` 是 ADR-0013 不变量 2 的落点：任何多出来的字段（含凭据形状）都拒。
    渠道名的**注册性**不在这里查——那是 registry 的事实，服务层不该反向依赖 provider 层。
    """

    model_config = ConfigDict(extra="forbid")

    enabled: list[str]
    default: str


class CategorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True


_DISCOVERY_ADAPTER = TypeAdapter(DiscoveryConfig)
_CATEGORIES_ADAPTER = TypeAdapter(list[CategorySpec])


# ------------------------------------------------------------------ 快照


_snapshot: dict[str, Any] = {}
_loaded_at: float | None = None


def peek(key: str) -> Any | None:
    """同步读最后已知快照。None = 「这里没登记过库值」，调用方据此回落。"""
    return _snapshot.get(key)


def snapshot_age() -> float | None:
    """距上次 refresh 的秒数；从没刷过 ⇒ None（快照是空的，别把"没读过"读成"库里没有"）。"""
    return None if _loaded_at is None else time.monotonic() - _loaded_at


def reset_snapshot() -> None:
    """清空进程内快照。测试用它密封用例，运维用它强制下一次读重新取值。"""
    global _loaded_at, _snapshot
    _snapshot = {}
    _loaded_at = None


def prime(key: str, value: Any) -> None:
    """把一份**已 validate** 的值放进快照，不碰库。

    存在的理由是让"库值优先"这段同步逻辑能在没有数据库的环境里被测。它不写库，
    所以永远不能拿它当"配置生效了"的证据——那必须走 `put()`。
    """
    global _snapshot
    _snapshot[key] = value


def is_fresh() -> bool:
    return _loaded_at is not None and (time.monotonic() - _loaded_at) < SNAPSHOT_TTL_SECONDS


# ------------------------------------------------------------------ 校验


def _readable(exc: ValidationError) -> str:
    """把 pydantic 错误转成人能读的中文，且**不回显输入值**。

    FastAPI 的默认 422 文案会把整份 body 打出来（`main.py` 的 `exc.errors()[:1]`）；
    配置字段里夹带的正是调用方自己塞的凭据串，回显等于把它复制进响应与访问日志。
    本服务的错误面只报「字段 + 原因」。
    """
    errors = exc.errors()
    if not errors:
        return "配置形状不合法（无法定位到具体字段）"
    first = errors[0]
    loc = ".".join(str(part) for part in first["loc"]) or "值"
    return f"配置形状不合法：{loc}（{first['type']}）"


def validate(key: str, value: object) -> Any:
    """值 → 已校验的模型（`DiscoveryConfig` 或 `list[CategorySpec]`）。非法 ⇒ 10005/422。"""
    if key not in KNOWN_KEYS:
        raise RequestInvalidError(f"未登记的配置键：{key}")
    parsed: Any
    try:
        if key == DISCOVERY_KEY:
            parsed = _DISCOVERY_ADAPTER.validate_python(value)
            _validate_discovery(parsed)
        else:
            parsed = _CATEGORIES_ADAPTER.validate_python(value)
            _validate_categories(parsed)
    except ValidationError as exc:
        raise RequestInvalidError(_readable(exc)) from exc
    return parsed


def _validate_discovery(cfg: DiscoveryConfig) -> None:
    cfg.enabled = [name.strip() for name in cfg.enabled if name.strip()]
    if len(set(cfg.enabled)) != len(cfg.enabled):
        doubled = sorted({n for n in cfg.enabled if cfg.enabled.count(n) > 1})
        raise RequestInvalidError(f"渠道重复：{', '.join(doubled)}")
    if not cfg.enabled:
        # 空集在这里是"决定过：本轮不做发现"，不是"没配"——所以 default 必须也是空串，
        # 否则就是一份自相矛盾的启用表（没有渠道却指定了默认渠道）。
        if cfg.default:
            raise RequestInvalidError(f"enabled 为空时 default 也必须是空串，实得 {cfg.default!r}")
        return
    if cfg.default not in cfg.enabled:
        raise RequestInvalidError(f"默认渠道 {cfg.default!r} 不在启用集内（可用：{', '.join(cfg.enabled)}）")


def _validate_categories(items: list[CategorySpec]) -> None:
    if not items:
        raise RequestInvalidError("分类清单不能为空：至少要有一个启用项")
    names: list[str] = []
    for item in items:
        item.name = item.name.strip()
        if not item.name:
            raise RequestInvalidError("分类名不能是空串")
        if len(item.name) > 32:
            # 上界来自列宽：`content_assets.category` 是 String(32)，超宽的名字会在入库时被
            # 数据库拒掉——那时报错的位置离配置的地方已经隔了一整条入库链。
            raise RequestInvalidError(f"分类名长度不能超过 32 字：{item.name[:12]}…（{len(item.name)} 字）")
        item.keywords = [kw.strip() for kw in item.keywords]
        if any(not kw for kw in item.keywords):
            raise RequestInvalidError(f"分类「{item.name}」的关键词里有空串")
        names.append(item.name)
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        raise RequestInvalidError(f"分类名重复：{', '.join(duplicated)}")
    if not any(item.enabled for item in items):
        raise RequestInvalidError("分类清单至少要有一个启用项")
    bottom = next((item for item in items if item.name == _DEFAULT_CATEGORY), None)
    if bottom is None or not bottom.enabled:
        raise RequestInvalidError(f"分类清单必须包含且启用「{_DEFAULT_CATEGORY}」（规则零命中的兜底落点）")


# ------------------------------------------------------------------ 摘要与审计


def digest(key: str, value: Any) -> str:
    """审计用的一行摘要：可比较、不含凭据（这两条都是本表不变量的要求）。

    只打名字与计数——配置值里唯一可能出现的就是渠道名与分类名，它们本身不是秘密；
    而形状上的任何凭据字段早在 `validate()` 就被拒了，进不了这里。
    """
    if key == DISCOVERY_KEY:
        cfg: DiscoveryConfig = value
        return f"enabled={len(cfg.enabled)}[{','.join(cfg.enabled)}] default={cfg.default or '∅'}"
    items: list[CategorySpec] = value
    names = ",".join(item.name for item in items)
    return f"categories={len(items)} enabled={sum(1 for i in items if i.enabled)} [{names}]"[:240]


# ------------------------------------------------------------------ 读写


async def refresh(session: AsyncSession) -> dict[str, Any]:
    """整表读一遍，只留下白名单里且能解析的键。坏行跳过并告警，绝不让配置面整体不可读。"""
    global _loaded_at, _snapshot
    loaded: dict[str, Any] = {}
    for key, value in (await session.execute(select(SystemSetting.key, SystemSetting.value))).all():
        if key not in KNOWN_KEYS:
            logger.warning("system_settings.skipped", key=key, reason="未登记的配置键")
            continue
        try:
            loaded[key] = validate(key, value)
        except RequestInvalidError as exc:
            logger.warning("system_settings.skipped", key=key, reason=str(exc.message))
    _snapshot = loaded
    _loaded_at = time.monotonic()
    return loaded


async def get(session: AsyncSession, key: str) -> Any:
    """异步读：TTL 过期就先刷新，再取快照。调用方必须握着会话。"""
    if not is_fresh():
        await refresh(session)
    return peek(key)


async def refresh_with(
    factory: Callable[[], AbstractAsyncContextManager[AsyncSession]], *, force: bool = False
) -> bool:
    """常驻进程每轮开头调它：TTL 过期才真去读一次库，快照仍新就直接返回。

    TTL 门是必要的——worker 的空转间隔是 10 秒量级，不设门就等于把"每轮刷一次"
    写成"每秒查一次库"。失败只告警、返回 False，与心跳同纪律：配置刷新不了就用
    最后已知值继续跑，一次数据库抖动不该把采集全线停掉。返回值让"这一轮刷没刷成"
    是个可断言的事实，而不是注释。
    """
    if not force and is_fresh():
        return True
    try:
        async with factory() as session:
            await refresh(session)
        return True
    except Exception as exc:  # noqa: BLE001 可观测性/配置面故障不得放大成停摆
        logger.warning("system_settings.refresh_failed", reason=str(exc)[:200])
        return False


async def put(
    session: AsyncSession,
    key: str,
    value: object,
    *,
    actor: User | None = None,
) -> Any:
    """写一行配置：校验 ⇒ 覆盖 ⇒ 刷新本进程快照 ⇒ 结构化审计（谁、何时、旧值摘要、新值摘要）。

    `actor=None` 只留给非人工写入（播种/迁移回填）；那种行的 `updated_by` 为空，
    审计里靠 `actor_sub=""` 显式说出"这不是人写的"，而不是伪造一个操作者。
    """
    parsed = validate(key, value)
    existing = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    dumped = (
        _DISCOVERY_ADAPTER.dump_python(parsed, mode="json")
        if key == DISCOVERY_KEY
        else _CATEGORIES_ADAPTER.dump_python(parsed, mode="json")
    )
    row = existing or SystemSetting(key=key)
    # 旧值摘要必须在**改这个对象之前**取：`existing` 与 `row` 是同一个 SQLAlchemy 实例，
    # 先赋新值再算摘要会报出"旧值=新值"——审计里那条"改之前是什么"就成了假的（本机实测抓到）。
    old_digest = _prior_digest(key, existing) if existing is not None else ""
    row.value = dumped
    row.updated_by = actor.id if actor is not None else None
    row.updated_at = datetime.now(UTC)
    session.add(row)
    await session.flush()
    # 提交权在本服务（本仓约定：Service 内 commit，见 `engine_keys.py`）。
    # 放在审计之前是刻意的：提交失败就不该留下一条"改过了"的审计。
    await session.commit()

    _snapshot[key] = parsed
    global _loaded_at
    _loaded_at = time.monotonic()

    logger.info(
        "system_setting.changed",
        key=key,
        actor_sub=actor.sub if actor is not None else "",
        actor_role=actor.role if actor is not None else "",
        old_row=existing is not None,
        old_digest=old_digest,
        new_digest=digest(key, parsed),
        ts=datetime.now(UTC).isoformat(),
    )
    return parsed


def _prior_digest(key: str, row: SystemSetting) -> str:
    """旧值摘要：库里那行解析不出来时也要报得出形状，不能让审计在坏数据上抛错。"""
    try:
        return digest(key, validate(key, row.value))
    except RequestInvalidError:
        return "不可解析的旧值"
