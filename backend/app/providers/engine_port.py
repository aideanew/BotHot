"""AB-P004 P4 引擎可插拔端口层（ADR-0004 P0 端口抽取）。

KnowledgeEnginePort：建库/上传/检索三方法最小契约（防腐层，与 LangBot 客户端同级）。
- E0 内置 LangBotAdapter：搬运现状 providers/langbot 调用，行为零变更（回归一致）；
- E1 主平台 RagflowAdapter：骨架（Key 未配置时明确报不可用，不假装可用）；
- E2/E3/E4 SaaS（Coze/Dify/FastGPT）：登记 allowlist 位，按 Key 到位逐个接，本期骨架。

规则（ADR-0004 §三）：
1. 资产层与引擎解耦：ContentAsset(content_markdown) 唯一真源，引擎只收文件/文本上传；
2. 空间绑定引擎：KnowledgeSpace.engine + engine_kb_id（与 langbot_kb_uuid 双写）；
3. 问答扇出按 space.engine 路由；
4. 密钥纪律（T5.4 后）：第三方 API Key 走登记表（密文落库）或 env 兜底，
   代码零明文；「有凭据/无凭据」只由 core.engine_keyring.resolve_engine_key 判定。
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.engine_keyring import resolve_engine_key, snapshot
from app.providers.langbot.client import LangBotClient


class KnowledgeEnginePort(Protocol):
    """引擎位最小契约（六方法，ADR-0004 §三端口）。"""

    name: str

    async def create_kb(self, space_name: str) -> str:
        """建库 → 引擎侧 KB 标识（builtin=LangBot KB uuid；main/coze/dify/fastgpt=各自 dataset id）。"""
        ...

    async def upload_file(self, kb_id: str, filename: str, content: str | bytes) -> str:
        """上传文件/文本 → 引擎侧文件标识。SaaS 缺 URL 上传时用 markdown 转文件兜底（契约④）。"""
        ...

    async def ingest_status(self, kb_id: str, file_id: str) -> str:
        """文件入库状态：completed|processing|pending|failed|timeout（与 LangBot 状态映射同口径）。"""
        ...

    async def retrieve(self, kb_id: str, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        """检索 → 结果列表（原文+来源+文档ID）；统一返回 shape 供 SSE citations 消费。"""
        ...

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        """删除单个文件。"""
        ...

    async def delete_kb(self, kb_id: str) -> None:
        """删除整库（含回滚责任：调用方先删库再删 PG）。"""
        ...


class LangBotAdapter:
    """E0 内置引擎适配器：1:1 搬运 LangBotClient 现状调用（行为零变更回归）。"""

    name = "builtin"

    def __init__(self, client: LangBotClient) -> None:
        self._client = client

    async def create_kb(self, space_name: str) -> str:
        # 建库需 engine_id + embedding_uuid（LangBot 建库两参），由调用方（kb service）预取后传入；
        # 端口签名简化：LangBotAdapter 建库走 client.create_kb 原路径（经 kb service 编排）
        raise NotImplementedError(
            "LangBot 建库需 engine/embedding 预取，走 KnowledgeBaseService.ensure_kb 原路径"
        )

    async def upload_file(self, kb_id: str, filename: str, content: str | bytes) -> str:
        return await self._client.upload_document(filename, content)

    async def ingest_status(self, kb_id: str, file_id: str) -> str:
        for entry in await self._client.list_kb_files(kb_id):
            identity = str(entry.get("file_name") or entry.get("uuid") or entry.get("id"))
            if identity == file_id:
                return str(entry.get("status", "unknown"))
        return "unknown"

    async def retrieve(self, kb_id: str, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        results = await self._client.retrieve(kb_id, question, top_k)
        return results if isinstance(results, list) else []

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        await self._client.delete_kb_file(kb_id, file_id)

    async def delete_kb(self, kb_id: str) -> None:
        await self._client.delete_kb(kb_id)


class RagflowAdapter:
    """E1 主平台 RAGFlow 系骨架：Key 未配置时明确不可用（不假装可用）。

    主平台 RAGFlow 拓展系：kb 映射主平台库 id；检索/上传走主平台统一账号体系。
    实接需 MAIN_KB_API_BASE/MAIN_KB_API_KEY 到位（env），本期骨架登记槽位。
    """

    name = "main"
    implemented = False  # R1 修复：六方法未实接前恒 False，杜绝伪 available 触发 50001

    def __init__(self, api_base: str = "", api_key: str = "") -> None:
        self._api_base = api_base
        self._api_key = api_key

    @property
    def available(self) -> bool:
        return self.implemented and bool(self._api_base and self._api_key)

    def _require(self) -> None:
        if not self.available:
            raise RuntimeError("主平台 RAGFlow 引擎未配置（MAIN_KB_API_BASE/KEY 缺失），请联系管理员")

    async def create_kb(self, space_name: str) -> str:
        self._require()
        raise NotImplementedError("RagflowAdapter 实接待主平台排期（ADR-0004 P2）")

    async def upload_file(self, kb_id: str, filename: str, content: str | bytes) -> str:
        self._require()
        raise NotImplementedError("RagflowAdapter 实接待主平台排期（ADR-0004 P2）")

    async def ingest_status(self, kb_id: str, file_id: str) -> str:
        self._require()
        raise NotImplementedError("RagflowAdapter 实接待主平台排期（ADR-0004 P2）")

    async def retrieve(self, kb_id: str, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._require()
        raise NotImplementedError("RagflowAdapter 实接待主平台排期（ADR-0004 P2）")

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        self._require()
        raise NotImplementedError("RagflowAdapter 实接待主平台排期（ADR-0004 P2）")

    async def delete_kb(self, kb_id: str) -> None:
        self._require()
        raise NotImplementedError("RagflowAdapter 实接待主平台排期（ADR-0004 P2）")


class SaasAdapter:
    """E2/E3/E4 SaaS 适配器骨架（Coze/Dify/FastGPT）：登记 allowlist 位。

    8 项契约（ADR-0004 §四）：注册拿 Key/建库/上传文件/URL 上传（缺则 markdown 转文件兜底）/
    托管解析/检索（原文+来源+文档ID）/更新删除/小白步数。
    本期 Key 未到位：available=False，调用明确报不可用；实接按 Coze→Dify→FastGPT 逐个开。
    """

    implemented = False  # R1 修复：六方法未实接前恒 False（同 RagflowAdapter 口径）

    def __init__(self, name: str, api_key: str = "") -> None:
        self.name = name
        self._api_key = api_key

    @property
    def available(self) -> bool:
        return self.implemented and bool(self._api_key)

    def _require(self) -> None:
        if not self.available:
            raise RuntimeError(f"{self.name} 引擎未配置（API Key 缺失），请联系管理员配置 env")

    async def create_kb(self, space_name: str) -> str:
        self._require()
        raise NotImplementedError(f"{self.name} SaaS 实接待 Key 到位（ADR-0004 P3）")

    async def upload_file(self, kb_id: str, filename: str, content: str | bytes) -> str:
        self._require()
        raise NotImplementedError(f"{self.name} SaaS 实接待 Key 到位（ADR-0004 P3）")

    async def ingest_status(self, kb_id: str, file_id: str) -> str:
        self._require()
        raise NotImplementedError(f"{self.name} SaaS 实接待 Key 到位（ADR-0004 P3）")

    async def retrieve(self, kb_id: str, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._require()
        raise NotImplementedError(f"{self.name} SaaS 实接待 Key 到位（ADR-0004 P3）")

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        self._require()
        raise NotImplementedError(f"{self.name} SaaS 实接待 Key 到位（ADR-0004 P3）")

    async def delete_kb(self, kb_id: str) -> None:
        self._require()
        raise NotImplementedError(f"{self.name} SaaS 实接待 Key 到位（ADR-0004 P3）")


# ------------------------------------------------------------------ 引擎注册表（5 位默认顺序）

ENGINE_ORDER = ["builtin", "main", "coze", "dify", "fastgpt"]


def make_engine(name: str, settings: Any, langbot_client: LangBotClient | None = None) -> KnowledgeEnginePort:
    """按引擎位名构造适配器。Key 由 resolve_engine_key 单一解析（登记表 > env，代码零明文）。"""
    if name == "builtin":
        if langbot_client is None:
            raise ValueError("builtin 引擎需 LangBotClient 装配")
        return LangBotAdapter(langbot_client)
    if name == "main":
        return RagflowAdapter(
            api_base=str(getattr(settings, "main_kb_api_base", "") or ""),
            api_key=resolve_engine_key(name, settings, snapshot()).key,
        )
    if name in ("coze", "dify", "fastgpt"):
        return SaasAdapter(name, api_key=resolve_engine_key(name, settings, snapshot()).key)
    raise ValueError(f"未知引擎位: {name}（合法：{'/'.join(ENGINE_ORDER)}）")


# ------------------------------------------------------------------ 引擎路由（BE-02）

# 引擎 Key 缺失 / 未开放 时的不可用提示（10004/403 语义，见 engines.py PATCH 端点）
ENGINE_UNAVAILABLE_HINT = "引擎 %s 不可用（不在开放名单 / API Key 未配置 / 适配器未实现），详见 EngineSwitcher 三态提示"

# R1 修复：实接状态注册表——骨架位（六方法 NotImplementedError）不可路由，杜绝伪 available
ENGINE_IMPLEMENTED: dict[str, bool] = {
    "builtin": True,
    "main": False,  # RagflowAdapter 实接后置 True（需 MAIN_KB Key 轮换 + allowlist 显式开）
    "coze": False,
    "dify": False,
    "fastgpt": False,
}


class EngineRouter:
    """按 space.engine 分发引擎适配器与 kb 标识（BE-02 路由层，薄封装）。

    - kb_id_for(space)：builtin → langbot_kb_uuid；非 builtin → engine_kb_id（空串=未实接）；
    - adapter_for(space)：builtin → LangBotAdapter(注入 client)；非 builtin → make_engine；
    - available(engine)：Key 是否就绪（builtin 恒 True）；allowlisted(engine)：是否在开放名单。
    """

    def __init__(self, settings: Any, langbot_client: LangBotClient | None = None) -> None:
        self._settings = settings
        self._langbot_client = langbot_client

    def allowlisted(self, engine: str) -> bool:
        allow = [x.strip() for x in str(getattr(self._settings, "kb_engine_allowlist", "builtin")).split(",")]
        return engine in allow

    def configured(self, engine: str) -> bool:
        """引擎是否已配置可用凭据（builtin 恒 True；登记表 > env，由单一谓词判定）。"""
        return resolve_engine_key(engine, self._settings, snapshot()).configured

    def available(self, engine: str) -> bool:
        """available = 配置了就绪 且 在开放名单 且 已实接（R1：三条件同口径，见 ENGINE_IMPLEMENTED）。"""
        return (
            self.configured(engine)
            and self.allowlisted(engine)
            and ENGINE_IMPLEMENTED.get(engine, False)
        )

    def kb_id_for(self, space: Any) -> str:
        """空间当前引擎的 KB 标识（builtin 取 langbot_kb_uuid；非 builtin 取 engine_kb_id）。"""
        engine = str(getattr(space, "engine", "builtin") or "builtin")
        if engine == "builtin":
            return str(getattr(space, "langbot_kb_uuid", "") or "")
        return str(getattr(space, "engine_kb_id", "") or "")

    def adapter_for(self, space: Any) -> KnowledgeEnginePort:
        """按 space.engine 分发适配器；不可用引擎抛 ValueError（调用方转 10004/50002）。"""
        engine = str(getattr(space, "engine", "builtin") or "builtin")
        if engine not in ENGINE_ORDER:
            raise ValueError(f"未知引擎位: {engine}")
        if not self.available(engine):
            raise ValueError(ENGINE_UNAVAILABLE_HINT % engine)
        return make_engine(engine, self._settings, self._langbot_client)
