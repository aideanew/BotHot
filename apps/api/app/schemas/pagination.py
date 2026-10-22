"""app/schemas/pagination —— 分页目标壳（D-V3-02；STEP-14a S14a.2.1/S14a.2.2）。

两条口径住在这一个文件里，是因为存量客户端不能破：

- 旧口径 `limit` / `offset`：admin 五个清单端点与它们下面的 service 签名用的就是它；
- 新口径 `page` / `pageSize`：D-V3-02 的目标壳，前端 `usePagedList` 缺的那一格是 `hasMore`。

换算只做一次，就在 `page_query`；键名只定义一次，就在 `Page`。
装配函数 `page_shell` 只增键不删键，所以旧客户端继续读 `items/total/limit/offset` 零回归。

本模块**刻意不写 `from __future__ import annotations`**：`make_page_query` 是闭包依赖，
它的形参注解里带着 `le=max_size` 这类运行期值；一旦注解变成字符串（PEP 563），
pydantic 在生成 OpenAPI 时无法重建 `ForwardRef`，报错点是 `app.openapi()` 而不是本文件——
2026-10-22 实测：`test_r48_admin_routes_registered` 红在 `PydanticUserError: TypeAdapter[...]
is not fully defined`。
"""

from dataclasses import dataclass
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PageParams:
    """解析后的分页位置。`limit`/`offset` 是唯一真相，`page` 由它们导出——

    反过来（以 `page` 为真相）会让旧口径请求要么报错要么偷偷改掉调用方给的偏移。
    """

    limit: int
    offset: int

    @property
    def page(self) -> int:
        return self.offset // self.limit + 1


class Page(BaseModel, Generic[T]):
    """目标壳 `{items, page, pageSize, total, hasMore}`，外加旧键 `limit`/`offset`。

    键名大小写不一致是历史事实：存量 page 壳的响应写的是 `page_size`（snake_case），
    而 D-V3-02 要的是 `pageSize`。本模型是这件事**唯一的定义处**，
    新端点一律走它；存量 `bots.py` / `hot.py` 的 `page_size` 不在本卡面上动
    （改了就是破客户端，且那三处归 STEP-15 的消费面）。
    """

    model_config = ConfigDict(populate_by_name=True)

    items: list[T]
    total: int
    limit: int
    offset: int
    page: int
    page_size: int = Field(alias="pageSize")
    has_more: bool = Field(alias="hasMore")


def make_page_query(
    *, default_size: int = DEFAULT_PAGE_SIZE, max_size: int = MAX_PAGE_SIZE
):
    """造一个分页依赖。上限**逐端点声明**，不设全局统一值——

    存量 admin 清单的 `limit` 上限并不一致（`/spaces/{id}/docs` 是 200，其余是 100），
    收成一个全局值就等于偷偷改掉某一边：收紧会让旧客户端的 `limit=200` 直接 422，
    放宽会把另一个端点的 DoS 面撑开。所以这里把边界留在调用点上写。
    """

    async def dep(
        limit: Annotated[
            int | None, Query(ge=1, le=max_size, description="旧口径：SQL LIMIT")
        ] = None,
        offset: Annotated[int | None, Query(ge=0, description="旧口径：SQL OFFSET")] = None,
        page: Annotated[int | None, Query(ge=1, description="新口径：1 起的页码")] = None,
        page_size: Annotated[
            int | None,
            Query(alias="pageSize", ge=1, le=max_size, description="新口径：每页条数"),
        ] = None,
    ) -> PageParams:
        """两壳并存时的优先级：给了任一旧参数，就整段按旧参数解释。

        旧客户端只发 `limit`/`offset`，新客户端只发 `page`/`pageSize`；两者同时出现是异常而不是
        一种选择，此时按先存在的公开面（旧参数）解释，不静默换算成第三种位置——
        静默换算会让一次误拼的 `?page=2&limit=50` 变成"第 2 页但每页 50 条"这种没人要的东西。
        """
        if limit is not None or offset is not None:
            return PageParams(
                limit=default_size if limit is None else limit,
                offset=0 if offset is None else offset,
            )
        size = default_size if page_size is None else page_size
        number = 1 if page is None else page
        return PageParams(limit=size, offset=(number - 1) * size)

    return dep


page_query = make_page_query()


def page_shell(items: list[Any], total: int, params: PageParams) -> dict[str, Any]:
    """装配 `success(data=…)` 的那一份 `data`。

    `hasMore` 用已经拿到的 `total` 算，不额外发一次 COUNT——多那一次 COUNT 换来的读数
    与本轮 `items` 不是同一时刻，反而会让"最后一页正好填满"被判成还有下一页。
    """
    return Page[dict[str, Any]](
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
        page=params.page,
        pageSize=params.limit,
        hasMore=params.offset + len(items) < total,
    ).model_dump(by_alias=True)
