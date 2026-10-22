"""STEP-19 S19.2.1：端口准则复验（REQ-C-002）。

卡面要求"全仓是否存在 BotHot 服务占 3000"与"3200/3300/5433/6380 与 AGENTS 端口表逐项核对"。
两条判据的形状不同，分开判：

1. **宿主侧零占用 3000**——这条判 YAML 真解析出来的 `ports` 映射，不判 grep 文本：
   `grep '3000'` 在本仓会命中 `30004` 错误码、`AIDEAN_ISSUER=http://…:3000`（那是**主平台**的地址，
   不是 BotHot 在监听）与注释里的"容器内仍 3000"，文本扫描既误报又漏报。
2. **判据自己得能红**——同一套谓词必须对一条伪造的 `3000:3000` 映射变红。
   只判"现网 compose 里没有 3000"的守卫，等价于把结论写在 `scanned == 0` 上：
   compose 被改名/被拆分成多文件时它会静默恒绿（STEP-00P 那一条门就是这么修的）。

逐项核对的读数（2026-10-22 现读 `docker/compose.yml`）在 EVD-V3-19/verdicts.md，
本文件只把"能机械判的那半"钉成用例。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

API = Path(__file__).resolve().parents[1]
REPO = API.parents[1]
COMPOSE_PATHS = sorted((REPO / "docker").glob("compose*.yml"))

#: 主平台专用端口（AGENTS.md 端口表：BotHot 任何服务禁止占用宿主侧它）
FORBIDDEN_HOST_PORT = "3000"
#: 本仓合法出现的宿主端口（AGENTS.md 表 + compose 现读）
EXPECTED_HOST_PORTS = {"3200": "frontend(Next.js)", "3300": "backend(FastAPI)", "5300": "langbot"}


def _host_port(mapping: str) -> str:
    """`[[IP:]HOST:]CONTAINER[/PROTO]` 形状里取宿主段。

    compose 的短语法有三种长度：`3300:3300`、`3200:3000`、`127.0.0.1:5433:5432`。
    宿主段永远是**倒数第二段**（最后一段是容器侧），所以不能取 `split(":")[0]`。
    """
    parts = str(mapping).split(":")
    return parts[-2] if len(parts) >= 2 else parts[0]


def _published_ports(doc: object) -> list[tuple[str, str]]:
    """返回 (service, 宿主端口)。`ports` 未写的服务（expose-only / host 网络）自然贡献 0 条。"""
    services = (doc or {}).get("services") or {}
    out: list[tuple[str, str]] = []
    for name, spec in services.items():
        for mapping in (spec or {}).get("ports") or []:
            out.append((str(name), _host_port(mapping)))
    return out


def test_compose_files_were_actually_parsed() -> None:
    """扫描面非空：`scanned == 0` 不是通过。compose 改名或目录挪走时，本卡所有结论都无来源。"""
    assert COMPOSE_PATHS, f"docker/ 下没有 compose*.yml（现读 {REPO / 'docker'}）"
    total = 0
    for path in COMPOSE_PATHS:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(doc, dict) and "services" in doc, f"{path.name} 解析出来没有 services 段"
        total += len(_published_ports(doc))
    assert total > 0, "compose 里一条端口映射都没解析出来 ⇒ 谓词失去来源，下面的绿没有含义"


@pytest.mark.parametrize("path", COMPOSE_PATHS, ids=lambda p: p.name)
def test_no_bot_hot_service_publishes_the_main_platform_port(path: Path) -> None:
    """S19.2.1 的正体：BotHot 的任何服务都不得把宿主 3000 占上。"""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    hits = [f"{svc}->{host}" for svc, host in _published_ports(doc) if host == FORBIDDEN_HOST_PORT]
    assert hits == [], f"{path.name} 占用主平台 3000：{hits}"


def test_the_predicate_fails_on_a_service_that_does_take_3000() -> None:
    """反向极性：伪造一份 `3000:3000` 与一份 `127.0.0.1:3000:3000`，谓词必须都抓住。

    没有这一条，上一节只是"现在的 compose 恰好没有"，不是"这件事被管住了"。
    """
    fake = {
        "services": {
            "evil": {"ports": ["3000:3000"]},
            "evil2": {"ports": ["127.0.0.1:3000:3000"]},
            "ok": {"ports": ["3200:3000", "5433:5432"]},
        }
    }
    got = [f"{svc}->{host}" for svc, host in _published_ports(fake) if host == FORBIDDEN_HOST_PORT]
    assert got == ["evil->3000", "evil2->3000"], f"谓词的极性不对：{got}"


def test_dockerfile_expose_does_not_declare_3000_for_the_backend() -> None:
    """容器内 EXPOSE 是文档性的，但后端那一行的口径要跟端口表一致（3300）。

    `apps/web/Dockerfile` 的 `EXPOSE 3000` 是 Next.js 自身的监听口（宿主映射 3200），
    它**不**违反端口准则，所以这里只判后端，不去"修"一个正确的东西。
    """
    api_expose = re.findall(
        r"^EXPOSE\s+(\d+)", (API / "Dockerfile").read_text(encoding="utf-8"), flags=re.M
    )
    assert api_expose == ["3300"], f"apps/api/Dockerfile 的 EXPOSE={api_expose}（端口表：后端 3300）"


def test_frontend_host_mapping_is_3200_not_3000() -> None:
    """compose 里 frontend 必须是 `3200:3000`（容器内 3000、宿主 3200）——这条把"逐项核对"里最容易被读错的一格钉住。"""
    doc = yaml.safe_load((REPO / "docker" / "compose.yml").read_text(encoding="utf-8"))
    services = doc.get("services") or {}
    frontend = next(
        (spec for name, spec in services.items() if "front" in name.lower() or "web" in name.lower()), None
    )
    assert frontend is not None, "compose 里找不到 frontend 服务，本判据的来源已经消失"
    mappings = [str(m) for m in (frontend.get("ports") or [])]
    assert any(_host_port(m) == "3200" for m in mappings), f"frontend 宿主侧不是 3200：{mappings}"


def test_every_documented_bot_hot_host_port_is_actually_published() -> None:
    """端口表里 BotHot 自己该占的三个宿主口（3200/3300/5300）必须在 compose 里都出现。

    只判"没占 3000"是不够的：把 frontend 的映射整行删掉，上一条也绿。
    这一条判的是"表里承诺的端口真的在提供服务"，两向合起来才是逐项核对。

    表里另有 5433（PG）/ 6380（Redis）两行**不在此断言**：compose 自 2026-10-09 起把两个底座
    移交给共享基础设施（注释写的是宿主 5435 / 6379），所以"表说有、实里没有"是文档漂移，
    不是端口违规——按卡面「禁止修改 AGENTS.md（结论转 STEP-17/12）」登记为 P-78 与判定读数。
    """
    published: set[str] = set()
    for path in COMPOSE_PATHS:
        published.update(host for _, host in _published_ports(yaml.safe_load(path.read_text(encoding="utf-8"))))
    missing = {port: who for port, who in EXPECTED_HOST_PORTS.items() if port not in published}
    assert not missing, f"端口表承诺的宿主端口在 compose 里找不到：{missing}；实际发布={sorted(published)}"
