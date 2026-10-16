"""契约包（ADR-0008）：后端 Python 代码是契约的唯一源，TS 与 JSON Schema 一律生成。

放这里的模块只描述**形状与不变量**，不含业务行为、不 import services/providers/models。
当前在位：`collection`（采集域）、`identity`（身份与权限边界）；其余域的收编见同卡 S1.2.2。

`Divergence` 定义在这里而不是某个域里：它是"模型 vs 冻结稿"差异的公共记录格式，
各域都往 `CONTRACT_DIVERGENCES` 里填条目，比对脚本按 (域, ref, field) 匹配放行。
把它放进任何一个域都会让别的域反向依赖它。
"""
from __future__ import annotations

from typing import NamedTuple


class Divergence(NamedTuple):
    """一条"模型 vs 冻结稿"的已知差异，**带责任人**。

    `kind` 五值：
      `structural`   等价写法，接受集不变；
      `tightening`   模型比 JSON Schema 严（冻结稿自己说明里的意图），接受集**收窄**；
      `serialization` 接受集不变，但 `model_dump()` 会物化冻结稿没有的默认值；
      `strictness`   接受集不变，但多余字段被丢弃而非透传；
      `documentation` 只影响人读文本（description / x-* 注释），不影响校验。

    `rule` 是这条差异的**消费者标识**，不是注释：`tests/test_collection_contract.py` 的元测试
    要求每条登记都真的被消费——要么被比对器实际用到，要么有一个可执行断言替它兑现在 `reason`
    里许的诺。第三轮独立验证就是拿这个打的：`x-not`、"另设 dump 形状检查"、`strictness` 三条
    当时都是**只有承诺、没有实现者**的装饰条目。

    比对脚本的纪律不变：**表里没有的差异一律算违规**（红）。
    """

    ref: str
    field: str
    kind: str
    rule: str
    draft: str
    model: str
    reason: str
