"""422（10005）的文案构造器：只报「字段路径 + 错误类型 + 原因」，绝不回显调用方的值。

来源：P-62 / D-V18-05（STEP-33 S33.2）。旧实现是
`failure(10005, f"请求参数校验失败: {exc.errors()[:1]}")`——把 pydantic 的错误字典整份格式化进
message。那份字典里有 `input`（就是调用方提交的原值），部分类型的 `msg` 还会把原值**内插进句子**
（自定义校验器 `raise ValueError(f"坏值 {v}")` 是最常见的一种），`ctx` 里也常有 `expected`/`error`
这类带值的字段。仓库是 public、响应体与访问日志都是暴露面 ⇒ 凭据形字段一旦被塞进请求就永久留档。

三条设计决定，都写在代码里而不是靠人记：
1. **不用 pydantic 的 `msg` 原文**。原因文案由本模块按 `type` 给固定句。
   理由不只是防内插：上游哪天改一句措辞，本仓的对外文案就会跟着变，
   而没有一条用例会因此变红——那是"文档与现实分叉"的标准生成方式。
2. **`type` 未知 ⇒ 固定泛化原因**，不退回 `msg`。判据不能建立在"上游不会新增会内插的类型"上。
3. **字段路径也做形状约束**。`extra="forbid"` 的错误里，`loc` 带着**调用方自己起的字段名**，
   把凭据串当键名提交就能绕过"不读 input"这条规矩 ⇒ 非标识符形状的路径段一律换成「字段」。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

#: 允许原样出现在"字段路径"里的段名：C/JSON 风格的标识符（前端与运营都按它定位字段）。
_SEGMENT_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

#: 每个 pydantic 错误类型对应一句固定原因（不带任何调用方可控的文本）。
REASONS: dict[str, str] = {
    "missing": "缺少必填字段",
    "extra_forbidden": "这个字段不在该接口接受的范围内",
    "list_type": "应为列表",
    "dict_type": "应为对象",
    "model_attributes_type": "应为对象",
    "string_type": "应为字符串",
    "int_type": "应为整数",
    "float_type": "应为数值",
    "bool_type": "应为布尔值",
    "bytes_type": "应为字节串",
    "callable_type": "应为可调用对象",
    "none_required": "该字段必须留空",
    "int_parsing": "无法解析成整数",
    "float_parsing": "无法解析成数值",
    "bool_parsing": "无法解析成布尔值",
    "json_invalid": "请求体不是合法 JSON",
    "string_unicode": "字符串里含有不允许的字符",
    "string_pattern_mismatch": "格式不符合该字段的要求",
    "string_too_short": "长度低于下限",
    "string_too_long": "长度超过上限",
    "too_short": "元素个数低于下限",
    "too_long": "元素个数超过上限",
    "greater_than": "数值必须大于下限",
    "greater_than_equal": "数值必须不小于下限",
    "less_than": "数值必须小于上限",
    "less_than_equal": "数值必须不大于上限",
    "multiple_of": "数值必须是指定步长的整数倍",
    "max_length_exceeded": "长度超过上限",
    "min_length": "长度低于下限",
    "enum": "取值不在允许集合内",
    "literal_error": "取值不在允许集合内",
    "url_parsing": "不是合法 URL",
    "url_scheme": "URL 的协议不在允许集合内",
    "date_parsing": "不是合法日期",
    "datetime_parsing": "不是合法日期时间",
    "datetime_from_date_parsing": "无法从日期推出日期时间",
    "time_parsing": "不是合法时间",
    "time_delta_parsing": "不是合法时长",
    "uuid_parsing": "不是合法 UUID",
    "decimal_parsing": "无法解析成十进制数",
    "value_error": "取值被该字段的校验规则拒绝",
    "assertion_error": "取值未通过该字段的断言",
    "dataclass_type": "应为该类型要求的对象",
}

GENERIC_REASON = "字段不合法"
_NO_LOC = "请求体"
_EMPTY_ERRORS = "请求参数校验失败：无法定位到具体字段"


def _path_segment(part: object) -> str:
    """把 `loc` 的一段变成可安全外发的文本。

    列表下标是整数 ⇒ 原样（`body.categories.0.name` 这种路径对定位有用）；
    字符串段只在长成标识符时原样，其它一律「字段」——调用方起的键名不能进文案。
    """
    if isinstance(part, int) and not isinstance(part, bool):
        return str(part) if part >= 0 else "字段"
    if isinstance(part, str) and _SEGMENT_SAFE.match(part):
        return part
    return "字段"


def _path(loc: object) -> str:
    if not isinstance(loc, list | tuple) or not loc:
        return _NO_LOC
    return ".".join(_path_segment(part) for part in loc)


def reason_for(error_type: object) -> str:
    """`type` → 固定原因。未知类型走泛化句，**永不退回 msg**。"""
    if isinstance(error_type, str):
        known = REASONS.get(error_type)
        if known is not None:
            return known
        # 自定义校验器在某些 pydantic 版本里带后缀（value_error.xxx）；按前缀认，不按 msg 认。
        head = error_type.split(".", 1)[0]
        if head in REASONS:
            return REASONS[head]
    return GENERIC_REASON


def _type_text(error_type: object) -> str:
    """类型名要给出去（前端按它本地化），但它本身也可能是调用方可控文本吗？
    不会——`type` 由 pydantic 常量给出。这里只做形状约束，防的是"哪天有人把它当字符串原样拼"。
    """
    if isinstance(error_type, str) and re.match(r"^[a-z][a-z0-9_.]{0,63}$", error_type):
        return error_type
    return "invalid"


def build_validation_message(errors: Sequence[Any]) -> str:
    """`RequestValidationError.errors()` → 一句不含调用方值的文案。

    只展开**第一条**（旧实现也是取 `[:1]`），其余以「另有 N 处」计数：把整份列表铺开既增大
    暴露面，又让前端无法稳定定位"该改哪个字段"。
    """
    if not errors:
        return _EMPTY_ERRORS
    first = errors[0] if isinstance(errors[0], dict) else {}
    path = _path(first.get("loc"))
    error_type = _type_text(first.get("type"))
    message = f"请求参数校验失败：{path}（{error_type}）：{reason_for(first.get('type'))}"
    rest = len(errors) - 1
    if rest > 0:
        message += f"；另有 {rest} 处不合法"
    return message
