"""S2.1.1「改前红」的真实 pytest 复现件（不启服务、不装依赖、只读）。

卡面 S2.1.1 第 1 步是「只写测试，模块不存在 ⇒ ImportError 即红」。这条红当时只发生在
我写实现**之前**，没有留档（第一轮复审 Q-4 指出：只有推断、没有运行记录）。本文件把
那个瞬时状态做成可重放的：用一个 `sys.meta_path` finder 只拦 `app.services.article_identity`
这一个模块名，其余导入照常——等价于「该文件还不存在」，但**不动工作树**（不删、不 mv）。

复现（两条命令，均在仓库根）：

    # 红：实现被拦
    PYTHONPATH=apps/api:docs/06_validation/evidence/EVD-V2-02 \
      python -m pytest apps/api/tests/test_article_identity.py -q --noconftest \
      -p block_article_identity_plugin -p no:cacheprovider
    # 绿：同一份用例、不加 -p
    PYTHONPATH=apps/api python -m pytest apps/api/tests/test_article_identity.py -q --noconftest

`--noconftest` 与上面两条命令共用：本机没装 sqlalchemy（实测 ModuleNotFoundError），
默认收集会卡在 `apps/api/tests/conftest.py` 的第三方导入上；本用例文件不消费任何 conftest 夹具。
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys

TARGET = "app.services.article_identity"


class _BlockFinder(importlib.abc.MetaPathFinder):
    """只伪造「这一个模块不存在」，其它模块的解析路径完全交给系统。"""

    def find_spec(self, fullname, path=None, target=None):  # noqa: D102
        if fullname == TARGET or fullname.startswith(TARGET + "."):
            raise ModuleNotFoundError(f"BLOCKED for S2.1.1 red-check: {fullname}", name=fullname)
        return None


_blocker = _BlockFinder()


def pytest_configure(config) -> None:  # noqa: ANN001
    """把拦截器插在 sys.meta_path 最前，且注册一个 autouse 夹具供用例侧自检。"""
    sys.meta_path.insert(0, _blocker)
    config._ai_blocker = _blocker


def pytest_unconfigure(config) -> None:  # noqa: ANN001
    if getattr(config, "_ai_blocker", None) is not None and _blocker in sys.meta_path:
        sys.meta_path.remove(_blocker)


def machine_readable_note() -> str:
    """供人核对：拦截器只在被显式加载时生效，本文件本身不产生 IO。"""
    return f"blocks={TARGET}"
