"""STEP-04 S4.2：新列的**形状对齐**机检（迁移 ↔ 模型 ↔ 契约），全部不需连库。

为什么这条门要存在（本仓库的现行形状）：`ab1006c1a` 只加两列，真正的行为改动在后面几步。
如果"迁移里写的列"与"模型里声明的列"漂了，症状不会是当场报错，而是
①CI 的 `alembic upgrade head` 建出的库里缺一列，连库用例在**别的**断言上红；
②`gen_contracts` 内省模型生成 dto.ts，产物与真实 schema 静默不一致。
两头都要等到连库或前端才炸——所以把"两边一致"提前到不需要 PG 的地方判。

覆盖三件事：
1. **单头 + 新迁移挂得住**：版本目录里只有一个 head，且 `ab1006c1a` 的 `down_revision`
   正好是它之前那个头（挂错父版本是并行开发的典型产物，W1-W5 那批就分叉过五路）。
2. **迁移 ↔ 模型逐列对齐**：从迁移 AST 里读出 add_column/create_index/create_foreign_key，
   与 SQLAlchemy metadata 的列名、可空性、类型长度、索引列序、FK 目标与 ondelete 一一比。
   任一侧单独改动都必须让这里红。
3. **可逆性**：`downgrade()` 必须真的拆掉 `upgrade()` 建的四件事（不许写 `raise`，
   因为 D-V2-02 要求 CI 上跑 `upgrade → downgrade → upgrade` 往返）。

另外钉一条 D-V9-04 的形状：契约侧 `article_key` 必填、DB 侧可空，这是**故意不对称**
（未回填的行不该对外序列化）；而 `""` 与裸末段 `s` 都不是合法键，写侧绝不能用它们占位。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.models.entities import ArticleManifest, JobItem

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
NEW_REV = "ab1006c1a"


def _revisions() -> dict[str, str | None]:
    """{revision: down_revision}，只读版本目录里的声明。

    两种赋值形态都要认：`revision = "x"`（Assign）与 `revision: str = "x"`（AnnAssign）。
    本仓库的迁移用的是后者——只认前者会让这个字典**永远是空的**，
    于是所有下游断言都在跟一个空集比，看着像"迁移不存在"，其实是指南针坏了。
    """
    out: dict[str, str | None] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        rev, down = None, "«未声明»"
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
                value = node.value
            else:
                continue
            if value is None:
                continue
            for name in names:
                if name == "revision":
                    rev = ast.literal_eval(value)
                elif name == "down_revision":
                    down = ast.literal_eval(value)
        if rev is not None:
            out[rev] = down
    return out


def _fn_src(tree_src: str, name: str) -> ast.FunctionDef:
    """从**给定的源码文本**里取顶层函数（不是只从磁盘那一份）——畸形输入要靠它复现。"""
    for node in ast.parse(tree_src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"源码里没有 {name}()")


def _fn_body(rev: str, name: str) -> ast.FunctionDef:
    path = next(p for p in VERSIONS.glob(f"{rev}*.py"))
    return _fn_src(path.read_text(encoding="utf-8-sig"), name)


def _calls(fn: ast.FunctionDef) -> list[ast.Call]:
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]


def _kw(call: ast.Call, key: str):
    for k in call.keywords:
        if k.arg == key:
            return ast.literal_eval(k.value)
    return None


def _op_name(call: ast.Call) -> str:
    assert isinstance(call.func, ast.Attribute)
    return call.func.attr


def _add_columns(fn: ast.FunctionDef) -> dict[str, list[tuple[str, str, bool, int | None]]]:
    """{表名: [(列名, 类型名, nullable, 长度)]}，取自 op.add_column。"""
    out: dict[str, list[tuple[str, str, bool, int | None]]] = {}
    for call in _calls(fn):
        if _op_name(call) != "add_column":
            continue
        table = ast.literal_eval(call.args[0])
        col_node = call.args[1]
        assert isinstance(col_node, ast.Call), "add_column 的第二实参必须是 sa.Column(...)"
        col_name = ast.literal_eval(col_node.args[0])
        type_call = col_node.args[1]
        assert isinstance(type_call, ast.Call)
        type_name = type_call.func.attr  # type: ignore[union-attr]
        length = _kw(type_call, "length")
        out.setdefault(table, []).append((col_name, type_name, _kw(col_node, "nullable") is not False, length))
    return out


def test_new_revision_exists_and_chains_to_the_previous_head() -> None:
    revs = _revisions()
    assert NEW_REV in revs, f"版本目录里没有 {NEW_REV}：新迁移没落进 alembic/versions/"
    heads = {r for r in revs if r not in {d for d in revs.values() if d}}
    assert len(heads) == 1, f"存在 {len(heads)} 个 head（分叉迁移）：{sorted(heads)}"
    parent = revs[NEW_REV]
    assert parent is not None and parent in revs, f"{NEW_REV} 的 down_revision={parent!r} 不是已知版本"
    # 新 head 必须挂在**旧头**上：挂到中间某个祖先，等于把后面的迁移全丢掉
    older = {r for r in revs if r != NEW_REV}
    reachable = set()
    cursor = parent
    while cursor in older:
        reachable.add(cursor)
        cursor = revs[cursor]
    assert NEW_REV not in reachable
    assert len(revs) - len(reachable) == 1, (
        f"{NEW_REV} 的父链只回溯到 {cursor!r}，中间漏掉 {len(revs) - len(reachable) - 1} 个版本 ⇒ 挂错父版本"
    )


def test_model_declares_exactly_the_columns_the_migration_adds() -> None:
    """迁移与模型逐列对齐：名/可空/类型长度三样都必须一致。"""
    added = _add_columns(_fn_body(NEW_REV, "upgrade"))
    assert set(added) == {"article_manifests", "job_items"}, f"本迁移不该碰别的表：{sorted(added)}"

    expected = {
        ArticleManifest: ("article_key", "article_manifests"),
        JobItem: ("manifest_id", "job_items"),
    }
    for model, (col_name, table) in expected.items():
        cols = added[table]
        assert [c[0] for c in cols] == [col_name], f"{table} 应只加 {col_name}，实得 {[c[0] for c in cols]}"
        _, type_name, nullable, length = cols[0]
        assert (type_name, length) == ("String", 128 if col_name == "article_key" else 36), (
            f"{col_name} 类型应为 String(128/36)，实得 {type_name}({length})"
        )
        mapped = model.__table__.columns[col_name]
        assert nullable is True and mapped.nullable is True, (
            f"{col_name} 可空性两侧不一致：迁移={nullable} 模型={mapped.nullable}（D-V9-04 定的是都可空）"
        )
        assert str(mapped.type) == f"VARCHAR({length})", f"{col_name} 模型侧长度漂了：{mapped.type}"


def _index_and_fk_shapes(fn: ast.FunctionDef) -> tuple[dict, dict]:
    """从 upgrade() 的 AST 里读 create_index / create_foreign_key 的形状（纯函数，畸形输入要用它）。"""
    indexes: dict[str, tuple[str, list[str]]] = {}
    fks: dict[str, tuple] = {}
    for call in _calls(fn):
        name = _op_name(call)
        if name == "create_index":
            indexes[ast.literal_eval(call.args[0])] = (
                ast.literal_eval(call.args[1]),
                ast.literal_eval(call.args[2]),  # 整个 List 节点求值；逐元素 literal_eval 会去迭代 AST 本身
            )
        elif name == "create_foreign_key":
            fks[ast.literal_eval(call.args[0])] = (
                ast.literal_eval(call.args[1]),
                ast.literal_eval(call.args[2]),
                ast.literal_eval(call.args[3]),
                ast.literal_eval(call.args[4]),
                _kw(call, "ondelete"),
            )
    return indexes, fks


def _migration_src(rev: str = NEW_REV) -> str:
    return next(p for p in VERSIONS.glob(f"{rev}*.py")).read_text(encoding="utf-8-sig")


def test_shape_guard_bites_on_the_four_ways_it_could_be_broken() -> None:
    """判据自己的反证：把迁移改坏四种，每种都必须**与模型不一致**（不咬人的门等于没有门）。

    这四发就是"以后有人这么改就会红"的具体形状。全部在内存里做，不碰磁盘。
    """
    src = _migration_src()
    base_cols = _add_columns(_fn_src(src, "upgrade"))
    base_idx, base_fk = _index_and_fk_shapes(_fn_src(src, "upgrade"))

    # ① 把新列改成 NOT NULL —— 与模型的 nullable=True 分叉
    m1 = src.replace('sa.Column("article_key", sa.String(length=128), nullable=True)',
                     'sa.Column("article_key", sa.String(length=128), nullable=False)')
    assert m1 != src, "锚漂了：①这一发压根没改动源码，等于没测"
    got = _add_columns(_fn_src(m1, "upgrade"))["article_manifests"][0]
    assert got[2] is False and base_cols["article_manifests"][0][2] is True

    # ② 索引少一列 —— 复合索引退化成单列，Diff 会走不到它
    m2 = src.replace('["source_id", "article_key"],', '["source_id"],')
    assert m2 != src, "锚漂了：②没改动源码"
    assert _index_and_fk_shapes(_fn_src(m2, "upgrade"))[0]["ix_manifest_source_article_key"] != (
        base_idx["ix_manifest_source_article_key"]
    )

    # ③ FK 改成 CASCADE —— 删清单会连带删掉在途条目
    m3 = src.replace('ondelete="SET NULL",', 'ondelete="CASCADE",')
    assert m3 != src, "锚漂了：③没改动源码"
    assert _index_and_fk_shapes(_fn_src(m3, "upgrade"))[1]["fk_job_items_manifest_id"][4] == "CASCADE"
    assert base_fk["fk_job_items_manifest_id"][4] == "SET NULL"

    # ④ downgrade 里塞一个 raise —— CI 的往返会当场跑不了
    m4 = src.replace("    op.drop_index(\"ix_job_items_manifest_id\"",
                     "    raise RuntimeError('no downgrade')\n    op.drop_index(\"ix_job_items_manifest_id\"")
    assert m4 != src, "锚漂了：④没改动源码"
    assert [n for n in ast.walk(_fn_src(m4, "downgrade")) if isinstance(n, ast.Raise)], "④应有一个 Raise 节点"
    assert not [n for n in ast.walk(_fn_src(src, "downgrade")) if isinstance(n, ast.Raise)]

    # 反证的反证：锚若失效（上面每发的 `assert m != src`），这一发就必须红——用空替换验证计数不骗人
    assert src.count('ondelete="SET NULL",') == 1, "③的锚在源码里出现多次，替换会漏改"
    assert src.count("    op.drop_index(\"ix_job_items_manifest_id\"") == 1, "④的锚不唯一"


def test_indexes_and_foreign_key_line_up_with_the_model() -> None:
    indexes, fks = _index_and_fk_shapes(_fn_body(NEW_REV, "upgrade"))
    assert indexes.get("ix_manifest_source_article_key") == ("article_manifests", ["source_id", "article_key"]), (
        f"清单侧复合索引形状变了：{indexes.get('ix_manifest_source_article_key')}"
    )
    assert indexes.get("ix_job_items_manifest_id") == ("job_items", ["manifest_id"]), (
        f"job_items.manifest_id 索引缺失或列序不对：{indexes.get('ix_job_items_manifest_id')}"
    )
    # 模型侧索引必须同时声明，否则 autogenerate 会想把它们再建一遍（漂移的第二种形状）
    idx_names = {i.name for i in ArticleManifest.__table__.indexes} | {i.name for i in JobItem.__table__.indexes}
    for name in indexes:
        assert name in idx_names, f"{name} 只在迁移里存在、模型里没声明 ⇒ 元数据与库会分叉"
    assert "fk_job_items_manifest_id" in fks
    table, ref_table, local, remote, ondelete = fks["fk_job_items_manifest_id"]
    assert (table, ref_table, local, remote) == ("job_items", "article_manifests", ["manifest_id"], ["id"])
    assert ondelete == "SET NULL", f"FK 删除行为应为 SET NULL（在途条目不该随清单消失），实得 {ondelete}"
    mapped_fk = next(iter(JobItem.__table__.columns["manifest_id"].foreign_keys))
    assert mapped_fk.ondelete == "SET NULL", "模型侧 ondelete 与迁移不一致"


def test_downgrade_reverses_everything_upgrade_builds() -> None:
    """可逆性：D-V2-02 要求 CI 跑 upgrade→downgrade→upgrade，所以 downgrade 不能是 `raise`。"""
    up, down = _fn_body(NEW_REV, "upgrade"), _fn_body(NEW_REV, "downgrade")
    up_ops = [_op_name(c) for c in _calls(up)]
    down_ops = [_op_name(c) for c in _calls(down)]
    # 按 AST 节点判，不按字形判：本件的 downgrade docstring 里就写着「不写成 raise RuntimeError」，
    # 拿子串扫文本会把自己的说明当成违例（这正是本仓库给判据反复修的那一族错）。
    raises = [n for n in ast.walk(down) if isinstance(n, ast.Raise)]
    assert not raises, f"downgrade 里有 {len(raises)} 处 raise：CI 的 upgrade→downgrade→upgrade 跑不了"
    for needed in ("drop_index", "drop_constraint", "drop_column"):
        assert needed in down_ops, f"downgrade 缺 {needed}()，upgrade 建的东西没被拆干净：{down_ops}"
    assert down_ops.count("drop_column") == up_ops.count("add_column") == 2
    assert down_ops.count("drop_index") == up_ops.count("create_index") == 2
    # 顺序：先拆依赖者（job_items 的 FK/列），再拆被引用者（article_manifests 的列）
    assert down_ops.index("drop_column") < len(down_ops) - 1, "最后一步才拆 article_manifests.article_key"


def test_placeholder_values_are_not_valid_keys_and_the_asymmetry_is_deliberate() -> None:
    """D-V9-04 的两端要同时钉住：`""`/裸 `s` 不是合法键；契约必填而列可空。"""
    from pydantic import ValidationError

    from app.contracts.collection import ArticleManifest as ManifestDto

    base = {
        "id": "m-1",
        "source_id": "s-1",
        "external_id": "workUuid-1",
        "url": "https://mp.weixin.qq.com/s?__biz=MjM5&mid=1&idx=1&sn=aa",
        "title": "t",
        "status": "DISCOVERED",
    }
    for bad in ("", "s", "long-key-001"):  # 空串、旧坍缩键、裸末段——都不许当占位值
        with pytest.raises(ValidationError):
            ManifestDto.model_validate({**base, "article_key": bad})
    assert ArticleManifest.__table__.columns["article_key"].nullable is True
    field = ManifestDto.model_fields["article_key"]
    assert field.is_required(), "契约侧 article_key 必须保持必填：回填前的行不该被序列化出去"
