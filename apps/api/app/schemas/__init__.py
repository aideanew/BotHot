"""app/schemas —— 响应形状层（不属于领域模型，也不属于契约生成物）。

目前只有一个模块：`pagination`（D-V3-02 的分页目标壳）。契约生成物的唯一源仍在
`app/contracts/`（ADR-0008），本包不放 Pydantic 契约模型，避免长出第二个真相源。
"""
