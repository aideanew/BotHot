"""LangBot 防腐层（B-T8）：全部 LangBot HTTP 细节收口于此，上层只见领域语义。

契约基准：M0 报告 §四（API 全链均已实证）。
- 鉴权：lbk_ API Key 创建端点 400 未解（M0 遗留）→ 管理员登录换 JWT，缓存复用，
  401 自动重登一次；
- 建库：POST /api/v1/knowledge/bases 须 knowledge_engine_plugin_id（LangRAG 引擎）
  + creation_settings.embedding_model_uuid（硅基流动，compose env 已配）；
- ingest：上传 → 触发为异步 task → 轮询 KB 文件清单至 completed/failed。

错误映射（复用既有码，未新增，合规 A 口径）：
- LangBot 404 → 30004（资源不存在语义）
- LangBot 其他 4xx / 响应形状异常 → 30002 LANGBOT_API_ERROR
- LangBot 5xx / 网络不可达 / 超时 → 50002 DEPENDENCY_UNAVAILABLE
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import DependencyUnavailableError, LangbotApiError, ResourceNotFoundError

DEFAULT_TIMEOUT = 15.0
_SEARCH_TYPE_DEFAULT = "vector"


class LangBotClient:
    """LangBot HTTP 客户端（登录态内缓存；单实例进程内复用）。"""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        http: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._http = http or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        self._owns_http = http is None
        self._token: str | None = None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # -------------------------------------------------------------- 鉴权

    async def _login(self) -> str:
        try:
            resp = await self._http.post(
                f"{self._base_url}/api/v1/user/auth",
                # v4.10.9 源码 user.py:68 读 json_data['user']——字段名是 user 非 username
                json={"user": self._username, "password": self._password},
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"LangBot 不可达: {exc}") from exc
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"LangBot 登录 5xx: {resp.status_code}")
        if resp.status_code != 200:
            raise LangbotApiError(f"LangBot 登录失败: {resp.status_code}")
        token = _extract_token(resp.json())
        if not token:
            raise LangbotApiError("LangBot 登录响应缺 token")
        self._token = token
        return token

    async def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            await self._login()
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """带登录态请求；401 重登一次重试；状态码 → 领域错误映射。"""
        url = f"{self._base_url}{path}"
        for attempt in (1, 2):  # 第 1 次带缓存 token；401 后重登重试一次
            headers = await self._auth_headers()
            try:
                resp = await self._http.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise DependencyUnavailableError(f"LangBot 不可达: {exc}") from exc
            if resp.status_code == 401 and attempt == 1:
                self._token = None  # token 失效 → 强制重登
                continue
            break
        if resp.status_code == 404:
            raise ResourceNotFoundError(f"LangBot 资源不存在: {path}")
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"LangBot 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            raise LangbotApiError(f"LangBot {resp.status_code}: {_safe_body(resp)}", upstream_status=resp.status_code)
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            payload = resp.json()
        except ValueError as exc:
            raise LangbotApiError(f"LangBot 响应非 JSON: {_safe_body(resp)}") from exc
        # LangBot 惯例：HTTP 200 + body {code: 0} 表成功；code≠0 表业务错误
        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise LangbotApiError(f"LangBot 业务错误 code={payload.get('code')}: {str(payload.get('msg', ''))[:120]}")
        return payload

    # -------------------------------------------------------------- 元信息（建库前置）

    async def list_engines(self) -> list[dict[str, Any]]:
        """知识引擎清单（取 caps 含 doc_ingestion 的插件 id）。"""
        data = await self._request("GET", "/api/v1/knowledge/engines")
        return _unwrap_list(data)

    async def list_embedding_models(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/provider/models/embedding")
        return _unwrap_list(data)

    async def register_provider(self, name: str, base_url: str, api_key: str) -> str:
        """注册 OpenAI 兼容 provider → uuid（M0 §四：requester=openai-chat-completions）。"""
        payload = {
            "name": name,
            "requester": "openai-chat-completions",
            "base_url": base_url,
            "api_keys": [api_key],
        }
        data = await self._request("POST", "/api/v1/provider/providers", json=payload)
        uuid_ = data.get("uuid") or (data.get("data") or {}).get("uuid")
        if not uuid_:
            raise LangbotApiError("注册 provider 响应缺 uuid")
        return str(uuid_)

    async def register_embedding_model(self, name: str, provider_uuid: str) -> str:
        """注册 embedding 模型 → uuid。"""
        payload = {"name": name, "provider_uuid": provider_uuid, "extra_args": {}}
        data = await self._request("POST", "/api/v1/provider/models/embedding", json=payload)
        uuid_ = data.get("uuid") or (data.get("data") or {}).get("uuid")
        if not uuid_:
            raise LangbotApiError("注册 embedding 模型响应缺 uuid")
        return str(uuid_)

    # -------------------------------------------------------------- 知识库生命周期

    async def create_kb(
        self, name: str, engine_plugin_id: str, embedding_model_uuid: str
    ) -> str:
        """建库 → kb uuid（LangRAG schema：index_type=chunk + 默认切分参数）。"""
        payload = {
            "name": name,
            "knowledge_engine_plugin_id": engine_plugin_id,
            "creation_settings": {
                "embedding_model_uuid": embedding_model_uuid,
                "index_type": "chunk",
                "chunk_size": 512,
                "chunk_overlap": 64,
            },
        }
        data = await self._request("POST", "/api/v1/knowledge/bases", json=payload)
        kb_uuid = data.get("uuid") or data.get("data", {}).get("uuid") if isinstance(data, dict) else None
        if not kb_uuid:
            raise LangbotApiError("建库响应缺 uuid")
        return str(kb_uuid)

    async def upload_document(self, filename: str, content: bytes | str) -> str:
        """multipart 上传 → file_id（LangBot 文档库暂存）。"""
        files = {"file": (filename, content if isinstance(content, bytes) else content.encode("utf-8"))}
        data = await self._request("POST", "/api/v1/files/documents", files=files)
        # 实测 v4.10.9：{code:0, data:{file_id: "v1/.../xxx.md"}}（路径形态 id）
        file_id = data.get("data", {}).get("file_id") if isinstance(data, dict) else None
        if not file_id:
            raise LangbotApiError("上传响应缺 file_id")
        return str(file_id)

    async def trigger_ingest(self, kb_uuid: str, file_id: str) -> str:
        """触发异步 ingest → task/记录 id（轮询凭证）。"""
        data = await self._request("POST", f"/api/v1/knowledge/bases/{kb_uuid}/files", json={"file_id": file_id})
        task_id = (
            data.get("task_id") or data.get("id") or data.get("data", {}).get("id")
            if isinstance(data, dict)
            else None
        )
        return str(task_id or "")  # 部分 LangBot 版本无 task id：轮询走文件清单

    async def list_kb_files(self, kb_uuid: str) -> list[dict[str, Any]]:
        """KB 文件清单（含 status：completed/processing/failed）。"""
        data = await self._request("GET", f"/api/v1/knowledge/bases/{kb_uuid}/files")
        return _unwrap_list(data)

    async def delete_kb_file(self, kb_uuid: str, file_id: str) -> None:
        """删除 KB 内文档。

        实测 v4.10.9：`DELETE bases/<kb>/files/<file_id>` 返回 405（路由不存在），
        文件级删除在本版本**永远**不可用——不是暂时故障，重试无用。
        调用方（spaces._delete_engine_file）据 `upstream_status == 405` 降级为告警后
        继续删 PG 行；此处仍如实抛错，由调用方决定是否可容忍。
        状态码映射：404 → ResourceNotFoundError（文件已不在）；5xx → DependencyUnavailableError。
        """
        await self._request("DELETE", f"/api/v1/knowledge/bases/{kb_uuid}/files/{file_id}")

    async def delete_kb(self, kb_uuid: str) -> None:
        """整库删除（冒烟实测 200；临时/重置场景用）。"""
        await self._request("DELETE", f"/api/v1/knowledge/bases/{kb_uuid}")

    async def retrieve(
        self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = _SEARCH_TYPE_DEFAULT
    ) -> list[dict[str, Any]]:
        """检索（B-T9 问答链用；此处先通链路）。"""
        payload = {
            "query": query,
            "retrieval_settings": {"top_k": top_k, "search_type": search_type},
        }
        data = await self._request("POST", f"/api/v1/knowledge/bases/{kb_uuid}/retrieve", json=payload)
        # 实测 v4.10.9：{code:0, data:{results:[{content:{text,file_name,...}, score, distance}]}}
        results = data.get("data", {}).get("results") if isinstance(data, dict) else None
        if results is None:
            raise LangbotApiError("retrieve 响应缺 results")
        return results


# ------------------------------------------------------------------ 内部工具


def _extract_token(payload: Any) -> str:
    """LangBot 登录响应 token 位置：data.token 或顶层 token。"""
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and data.get("token"):
            return str(data["token"])
        if payload.get("token"):
            return str(payload["token"])
    return ""


def _unwrap_list(payload: Any) -> list[dict[str, Any]]:
    """清单响应归一：{data: [...]} / {data: {items: [...]}} / [...]。"""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, list):
            return data
        for key in ("items", "list", "engines", "models", "files"):
            if isinstance(data, dict) and isinstance(data.get(key), list):
                return data[key]
    raise LangbotApiError("LangBot 清单响应形状异常")


def _safe_body(resp: httpx.Response) -> str:
    return resp.text[:200]
