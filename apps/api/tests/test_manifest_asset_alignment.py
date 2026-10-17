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
3. **可逆性**：`downgrade()` 必须真的拆掉 `upgrade()` 建的四件事（不许写 `raise`）。
   D-V2-02 要求 CI ubuntu 上跑 `upgrade → downgrade → upgrade`，这条现在是**机检**：
   `.github/workflows/ci.yml` backend job 的 "Migration roundtrip" 步（2026-10-17 补，
   补之前该步不存在——本文件的这条说法曾连续两天是"文档里有、门禁里没有"）。
   本门判的是 AST 形状（不需要 PG 就能红），CI 那步判的是真库执行，两者不是同一件事。
4. **CI 探针自己的极性**（`test_roundtrip_probe_has_polarity`）：CI 那步的第二层直查
   `information_schema` / `pg_indexes`，因为"版本戳变了"不等价于"形状被拆了"——
   `downgrade()` 空操作也会重标版本（先例 `ab1004w1a_secret_aes.py:119-121`）。
   探针是工具，工具也要被钉住两个极性，否则第一次真跑才发现它恒绿。

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


def _index_and_fk_shapes(fn: ast.FunctionDef) -> tuple[dict, dict, list[str]]:
    """从 upgrade() 的 AST 里读 create_index / create_foreign_key 的形状，外加**重名清单**。

    重名要单独返回：dict 是后写覆盖的，"同名索引建了两次、正确那支在后"会被静默吞掉
    （第二轮验证抓出的最后一个 AST 盲区）。真库上它会撞 PG 的重名错误、由 "Migrate schema" 步先红，
    但那属于"靠另一层兜住"，不是"本层有判定力"。
    """
    indexes: dict[str, tuple[str, list[str]]] = {}
    fks: dict[str, tuple] = {}
    idx_seen: list[str] = []
    fk_seen: list[str] = []
    for call in _calls(fn):
        name = _op_name(call)
        if name == "create_index":
            idx_name = ast.literal_eval(call.args[0])
            idx_seen.append(idx_name)
            indexes[idx_name] = (
                ast.literal_eval(call.args[1]),
                ast.literal_eval(call.args[2]),  # 整个 List 节点求值；逐元素 literal_eval 会去迭代 AST 本身
            )
        elif name == "create_foreign_key":
            fk_name = ast.literal_eval(call.args[0])
            fk_seen.append(fk_name)
            fks[fk_name] = (
                ast.literal_eval(call.args[1]),
                ast.literal_eval(call.args[2]),
                ast.literal_eval(call.args[3]),
                ast.literal_eval(call.args[4]),
                _kw(call, "ondelete"),
            )
    # 两类各判各的重名：索引名与约束名在 PG 里不是同一个命名空间，混判会报假违例
    dup = sorted({n for n in idx_seen if idx_seen.count(n) > 1} | {n for n in fk_seen if fk_seen.count(n) > 1})
    return indexes, fks, dup


def _migration_src(rev: str = NEW_REV) -> str:
    return next(p for p in VERSIONS.glob(f"{rev}*.py")).read_text(encoding="utf-8-sig")


# 本步**应当**建的两个索引，写成显式期望而不是"从迁移里读出来再跟模型并集比"：
# 并集判据被验证轮（2026-10-17）实测击穿——把 ix_manifest_source_article_key 从
# ArticleManifest 挪到 JobItem 仍然绿（两支名字进了同一个集合，没人管它建在哪张表上），
# 而模型多声明、迁移少建也绿（循环只单向遍历迁移侧）。
_REQUIRED_INDEXES: dict[str, tuple[str, list[str]]] = {
    "ix_manifest_source_article_key": ("article_manifests", ["source_id", "article_key"]),
    "ix_job_items_manifest_id": ("job_items", ["manifest_id"]),
}
_MODEL_BY_TABLE = {"article_manifests": ArticleManifest, "job_items": JobItem}
# ⑤的锚：迁移里给 job_items 建索引那一行（原文里唯一，反证靠删它）
_IDX_ON_JOB_ITEMS = '    op.create_index("ix_job_items_manifest_id", "job_items", ["manifest_id"])\n'


def _model_index_names_by_table() -> dict[str, set[str]]:
    """{表名: 该表模型声明的索引名}——**按表分桶**，不分桶就判不出"建错了表"。"""
    return {t: {i.name for i in m.__table__.indexes} for t, m in _MODEL_BY_TABLE.items()}


def _assert_indexes_agree(
    migration_idx: dict[str, tuple[str, list[str]]],
    model_idx: dict[str, set[str]],
    dup_names: list[str] | tuple[str, ...] = (),
) -> None:
    """迁移侧与模型侧的索引必须**集合相等**且**逐表对号**；不符就抛 AssertionError（判据本体，畸形输入要用它）。"""
    assert not dup_names, f"同一个 upgrade() 里重名建了多次：{sorted(dup_names)}——dict 后写覆盖前写，形状会被静默吞掉"
    missing = sorted(set(_REQUIRED_INDEXES) - set(migration_idx))
    extra = sorted(set(migration_idx) - set(_REQUIRED_INDEXES))
    assert not missing and not extra, (
        f"迁移建的索引与设计要求不符：模型声明而迁移没建 {missing}、迁移多建 {extra}"
    )
    for name, (table, cols) in _REQUIRED_INDEXES.items():
        assert migration_idx[name] == (table, cols), f"{name} 的所属表或列序漂了：{migration_idx[name]}"
        assert name in model_idx.get(table, set()), (
            f"{name} 没声明在 {table} 的模型上——声明到别的表 = 建到别的表，"
            f"这支复合索引等于没建（模型实得 {sorted(model_idx.get(table, set()))}）"
        )


def test_shape_guard_bites_on_the_seven_ways_it_could_be_broken() -> None:
    """判据自己的反证：把迁移/模型改坏七种，每种都必须让对应判据红（不咬人的门等于没有门）。

    这些发就是"以后有人这么改就会红"的具体形状。全部在内存里做，不碰磁盘。
    """
    src = _migration_src()
    base_cols = _add_columns(_fn_src(src, "upgrade"))
    base_idx, base_fk, base_dup = _index_and_fk_shapes(_fn_src(src, "upgrade"))
    assert not base_dup, f"现状就该没有重名：{base_dup}"
    real_model_idx = _model_index_names_by_table()

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

    # ⑤ 模型声明了、迁移却少建一个 —— 库里没这支索引，Diff 全表扫；
    #    旧判据（并集 + 单向循环）对这一发完全放行，这是它必须咬住的形状。
    m5 = src.replace(_IDX_ON_JOB_ITEMS, "")
    assert m5 != src, "锚漂了：⑤没删掉那行 create_index，等于没测"
    dropped_idx = _index_and_fk_shapes(_fn_src(m5, "upgrade"))[0]
    assert "ix_job_items_manifest_id" not in dropped_idx, "⑤的删除没生效：迁移侧仍读得到那支索引"
    with pytest.raises(AssertionError, match="模型声明而迁移没建"):
        _assert_indexes_agree(dropped_idx, real_model_idx)

    # ⑥ 索引声明挪到了别的表（名字不变、形状不变）—— 只有按表判才拦得住。
    #    构造直接从真实模型侧派生，不手写别的索引名：写死的名字一旦与模型不符，
    #    这一发就在验证我自己的臆造而不是验证判据。
    relocated = {
        "article_manifests": real_model_idx["article_manifests"] - {"ix_manifest_source_article_key"},
        "job_items": real_model_idx["job_items"] | {"ix_manifest_source_article_key"},
    }
    assert "ix_manifest_source_article_key" not in relocated["article_manifests"], "⑥的构造本身没成立"
    with pytest.raises(AssertionError, match="没声明在 article_manifests"):
        _assert_indexes_agree(base_idx, relocated)

    # ⑦ 同名索引建了两次、**正确那支在后** —— dict 后写覆盖，形状层必须靠重名清单出声
    #    （第二轮验证给的最后一个 AST 盲区；真库上它会撞 PG 的重名错，但那是不属于本层的兜底）
    dup_src = src.replace(
        _IDX_ON_JOB_ITEMS,
        '    op.create_index("ix_manifest_source_article_key", "job_items", ["manifest_id"])\n' + _IDX_ON_JOB_ITEMS,
    )
    assert dup_src != src, "锚漂了：⑦没注入第二支同名索引"
    dup_idx, _, dup_names = _index_and_fk_shapes(_fn_src(dup_src, "upgrade"))
    assert dup_names == ["ix_manifest_source_article_key"], f"⑦的重名没被提取器看见：{dup_names}"
    assert dup_idx["ix_manifest_source_article_key"] == ("job_items", ["manifest_id"]), (
        "⑦的构造本身要成立：覆盖后读到的必须是**错的那一支**，否则这发测的是别的东西"
    )
    with pytest.raises(AssertionError, match="重名建了多次"):
        _assert_indexes_agree(dup_idx, real_model_idx, dup_names)

    # 反证的反证：锚若失效（上面每发的 `assert m != src`），这一发就必须红——用空替换验证计数不骗人
    assert src.count('ondelete="SET NULL",') == 1, "③的锚在源码里出现多次，替换会漏改"
    assert src.count("    op.drop_index(\"ix_job_items_manifest_id\"") == 1, "④的锚不唯一"
    assert src.count(_IDX_ON_JOB_ITEMS) == 1, "⑤的锚不唯一"


def test_indexes_and_foreign_key_line_up_with_the_model() -> None:
    indexes, fks, dup_names = _index_and_fk_shapes(_fn_body(NEW_REV, "upgrade"))
    # 形状 + 集合相等 + 逐表对号 + 重名，四件事一次判完（判据本体见 _assert_indexes_agree，
    # 它的反证在 test_shape_guard_bites_on_the_seven_ways_it_could_be_broken 里逐发给出）
    _assert_indexes_agree(indexes, _model_index_names_by_table(), dup_names)
    assert "fk_job_items_manifest_id" in fks
    table, ref_table, local, remote, ondelete = fks["fk_job_items_manifest_id"]
    assert (table, ref_table, local, remote) == ("job_items", "article_manifests", ["manifest_id"], ["id"])
    assert ondelete == "SET NULL", f"FK 删除行为应为 SET NULL（在途条目不该随清单消失），实得 {ondelete}"
    mapped_fk = next(iter(JobItem.__table__.columns["manifest_id"].foreign_keys))
    assert mapped_fk.ondelete == "SET NULL", "模型侧 ondelete 与迁移不一致"
    # FK 的**名字**两侧不必一致，且这是仓库既有形态而不是本步引入的漂移：
    # env.py 没有 naming_convention，模型侧 13 支 FK 全部匿名、迁移侧一律显式命名
    # （先例 `ab1004m3b_engine_key_registration.py:15` 把名字拼成 SQLAlchemy 默认式）。
    # 判据因此只比"存在 + 目标 + ondelete"，不把名字的不对称伪装成一条会红的规则——
    # 那会让下一位读者以为两侧名字是同步的。真要同步得给全库加 naming_convention，属 STEP-12 之外的独立裁决。
    assert len(JobItem.__table__.columns["manifest_id"].foreign_keys) == 1, "manifest_id 上出现了第二支 FK"


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


def _load_probe():
    """按文件路径加载 CI 用的探针（scripts/ 不在包路径里，与 test_collection_contract 同法）。"""
    import importlib.util

    path = Path(__file__).resolve().parents[3] / "scripts" / "migration_roundtrip_probe.py"
    spec = importlib.util.spec_from_file_location("migration_roundtrip_probe", path)
    assert spec and spec.loader, f"探针文件不在位：{path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_roundtrip_probe_has_polarity() -> None:
    """CI 往返步的形状探针必须在"没真降级"时出声——这是它唯一不能是恒真的地方。

    为什么这条要存在（第二轮验证的原话大意）：`alembic current` 比字符串只证明**版本戳变了**，
    而 `downgrade()` 里什么都不做也会重标版本（先例 `ab1004w1a_secret_aes.py:119-121`）。
    探针直查 information_schema / pg_indexes，但探针自己也是个会撒谎的工具，所以它的判据
    `evaluate()` 要在这里被钉住两个极性，而不是等到 CI 上第一次真跑才发现它恒绿。
    """
    probe = _load_probe()
    want_cols = set(probe.COLUMNS.items())
    want_idx = {(t, n) for n, t in probe.INDEXES.items()}

    # 正例：升级后齐全 / 降级后全空，两种模式各应一次绿
    assert probe.evaluate(want_cols, want_idx, "present") == []
    assert probe.evaluate(set(), set(), "absent") == []

    # 反例（这才是判定力）：降级后仍留着列或索引 ⇒ absent 必须点名
    assert probe.evaluate({("job_items", "manifest_id")}, set(), "absent") == ["降级后仍在：列 job_items.manifest_id"]
    assert probe.evaluate(set(), {("article_manifests", "ix_manifest_source_article_key")}, "absent") == [
        "降级后仍在：索引 article_manifests.ix_manifest_source_article_key"
    ]
    # 升级后少建 ⇒ present 必须点名，且两列都缺时给两条而不是一条（合并成一条会丢信息）
    assert probe.evaluate({("article_manifests", "article_key")}, want_idx, "present") == ["缺列 job_items.manifest_id"]
    assert len(probe.evaluate(set(), set(), "present")) == 4

    # 精度与 AST 门那一层保持一致：索引**名字对但表不对**时 present 必须算没建
    stray = {("job_items", "ix_manifest_source_article_key"), ("job_items", "ix_job_items_manifest_id")}
    assert probe.evaluate(want_cols, stray, "present") == ["缺索引 article_manifests.ix_manifest_source_article_key"]
    # 而 absent 反过来按**名字**判（索引名在 schema 内全局唯一）：不管残留报在哪张表上都要出声
    assert probe.evaluate(set(), {("someone_elses_table", "ix_job_items_manifest_id")}, "absent") == [
        "降级后仍在：索引 someone_elses_table.ix_job_items_manifest_id"
    ]

    # 升级后齐全 ⇒ present 绿而 absent 红；降级后全空 ⇒ absent 绿而 present 红。
    # 这两行就是"探针不是恒真"的直接证明——任何一种"全绿"都只在一个极上不绿。
    assert probe.evaluate(want_cols, want_idx, "absent") != []
    assert probe.evaluate(set(), set(), "present") != []

    # 模式拼错时必须出声，不能悄悄当通过（CI 里 `--expect=persent` 这类手滑很常见）
    assert probe.evaluate(want_cols, want_idx, "present "), "expect 带了空格就得红"
    assert probe.evaluate(set(), set(), "") != []


# ── S4.1 / S4.3 / S4.4 的行为面：写侧算键 + P-2 常驻 + 同篇只入列一次 + 崩溃回退 ──────
#
# `db_session` 那几条在**本机无 PG 时 skip**（conftest 的既有口径），`@ci ubuntu` 才是 Done 面；
# 不连库的两条（`_map_row` / `_apply_update`）先给本机读数——它们就是 P-2 修复的写侧本体，
# "红→绿"能在本机拿到的那部分证据全在这里（变异反证见 10-执行过程 记录 §12）。

import uuid  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

from sqlalchemy import select  # noqa: E402
from structlog.testing import capture_logs  # noqa: E402

from app.models.entities import ContentAsset, Job, JobItem, ShortLinkMap, Source, User  # noqa: E402
from app.services.article_identity import canonical_article_key  # noqa: E402
from app.services.job_worker import JobWorker  # noqa: E402
from app.services.manifest import (  # noqa: E402
    MANIFEST_STATUS_DISCOVERED,
    MANIFEST_STATUS_ENQUEUED,
    ManifestSyncService,
    _map_row,
)
from app.services.subscription import SourceSubscriptionService  # noqa: E402

_ART_URL = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ%3D%3D&mid=2650&idx=1&sn=probe-a"
_ART_KEY = canonical_article_key(_ART_URL)
_ALT_URL = "https://mp.weixin.qq.com/s/AAAAaaaaBBBBcccc?chksm=x&sn=AAAAaaaaBBBBcccc"
# 短链形态的 token（`parse_wechat_url(...).short_token` 取的是 `/s/` 后面那一段，不含查询串）
_SHORT_TOKEN = "AAAAaaaaBBBBcccc"


def _rowmap(external_id: str, url: str) -> dict[str, object]:
    return {"id": external_id, "workUrl": url, "title": "t", "publishTime": "2026-10-17 08:00:00"}


def _manifest_row(
    source_id: str,
    external_id: str,
    url: str,
    key: str | None = _ART_KEY,
    status: str = MANIFEST_STATUS_DISCOVERED,
) -> ArticleManifest:
    return ArticleManifest(
        id=f"m-{uuid.uuid4().hex[:8]}",
        source_id=source_id,
        external_id=external_id,
        article_key=key,
        url=url,
        title="t",
        content_hash="h-" + uuid.uuid4().hex[:8],
        status=status,
    )


def test_map_row_writes_the_cross_channel_key_not_the_channel_id() -> None:
    """S4.3.1：`external_id` 与 `article_key` 同时出现，但取的是两支不同的东西。"""
    mapped = _map_row(_rowmap("workUuid-1", _ART_URL))
    assert mapped is not None
    assert mapped["external_id"] == "workUuid-1", "渠道幂等键不该被规范键顶掉（uq_manifest_source_external 靠它）"
    assert mapped["article_key"] == _ART_KEY, "Diff 要减的是这一支，P-2 就错在它当时根本不在这支键空间里"
    # 只有 id、没有 URL：行**照收**（"见过这篇"的真实记录），但规范键是 NULL ⇒
    # 它不会被 Diff 通入队列，只会被无键积压计数报出来（本文件那条连库用例判后果）。
    no_url = _map_row({"id": "workUuid-2", "title": "t"})
    assert no_url is not None and no_url["article_key"] is None and no_url["url"] == ""
    # id 与 URL 都没有 ⇒ 整行不收（既无渠道身份也无正文地址，落库就是把脏数据固化）
    assert _map_row({"title": "t"}) is None
    # 无身份一律 NULL，绝不写 `""`：`""` 不是合法 ArticleKey，还会让所有无键行互撞成一支键
    for produced in (mapped, no_url):
        assert produced is not None and produced["article_key"] != "", "D-V9-04：不许用空串冒充身份"


def test_url_change_makes_the_stored_key_follow() -> None:
    """S4.3.1.1：同一 `(source, external)` 行换了 URL，规范键必须跟着重算。

    留着旧键的话 Diff 会拿**上一篇**的身份去减资产——同篇两形态各排一次队，
    而 P-2 的读数会伪装成"修好了"。
    """
    existing = ArticleManifest(
        id="m-x",
        source_id="src-x",
        external_id="workUuid-1",
        article_key=_ART_KEY,
        url=_ART_URL,
        title="t",
        content_hash="h",
        status="DISCOVERED",
    )
    mapped = _map_row(_rowmap("workUuid-1", _ALT_URL))
    assert mapped is not None and mapped["article_key"] != existing.article_key
    assert ManifestSyncService._apply_update(existing, mapped) == "updated", "URL 变了却没算更新"
    assert existing.article_key == mapped["article_key"] == canonical_article_key(_ALT_URL)
    # 四态由入列/回写/自愈三处持有，重新发现不该把状态倒档
    assert existing.status == "DISCOVERED"


def test_an_upstream_row_missing_fields_never_blanks_the_stored_ones() -> None:
    """`_apply_update` 的"空值不覆盖"守卫本身：删掉它这条必须红（此前全仓零覆盖）。

    上游回一条"有 id、没 URL / 没标题 / 没发布时间"的行是**真实形状**（`_map_row` 对这种行给
    `url=""`、`article_key=None`）。照单更新会把一行可用记录降级成"身份被自己抹掉"的僵尸行：
    `article_key IS NULL` 随即被 Diff 挡在门外，而这不会有任何报错。
    另一半同样要紧：非空的新值**必须**照覆盖，否则这条守卫会变成"永不更新"的第二个缺陷。
    """
    existing = ArticleManifest(
        id="m-g",
        source_id="src-g",
        external_id="workUuid-1",
        article_key=_ART_KEY,
        url=_ART_URL,
        title="旧标题",
        publish_time=datetime(2026, 10, 17, 8, 0, tzinfo=UTC),
        content_hash="h",
        status="DISCOVERED",
    )
    before = (existing.url, existing.article_key, existing.title, existing.publish_time)

    # 缺字段的行：五个可变列都不许被空值抹掉
    assert (
        ManifestSyncService._apply_update(
            existing,
            {"url": "", "article_key": None, "title": "", "publish_time": None, "content_hash": ""},
        )
        == "unchanged"
    )
    assert (existing.url, existing.article_key, existing.title, existing.publish_time) == before

    # 反向：非空新值照常覆盖（守卫不是"停止更新"）
    assert (
        ManifestSyncService._apply_update(existing, {"url": _ALT_URL, "title": "新标题"}) == "updated"
    )
    assert existing.url == _ALT_URL and existing.title == "新标题"


class _OneSessionCtx:
    """让 JobWorker 复用夹具那条会话：它的 `commit()` 在 `create_savepoint` 模式下只放保存点。

    不把 worker 换成假会话是有意的——`recover_stale` 的 SQL 形状（状态 + 时间锚 + 在途排除）
    正是这一步要判的东西；假会话会把它变成"我信我自己写的谓词"。
    """

    def __init__(self, session: object) -> None:
        self._s = session

    def __call__(self) -> _OneSessionCtx:
        return self

    async def __aenter__(self) -> object:
        return self._s

    async def __aexit__(self, *exc: object) -> bool:
        return False


async def _noop_ingest(*args: object, **kwargs: object) -> dict[str, object]:
    return {}


async def _seed_source(db_session) -> Source:
    """每条用例一套 biz：夹具只回滚外层事务，固定 biz 撞上并发会话已提交的行时，
    `uq_source_type_external` 会把红记成"实现坏了"，其实是测试前提过期。
    """
    src = Source(type="wechat_oa", external_id=f"Mprobe{uuid.uuid4().hex[:12]}", name="probe")
    db_session.add(src)
    await db_session.flush()
    return src


async def _seed_user(db_session) -> User:
    """`Job.user_id` 是 `users.id` 的 NOT NULL 外键——不种用户，建 Job 会当场 FK viol。

    这条是写完用例后对着模型核出来的（本机跑不到连库分支，所以只能靠读约束清单，
    而不是等 @ci 告诉我）。
    """
    user = User(sub=f"sub-probe-{uuid.uuid4().hex[:12]}", email=f"probe-{uuid.uuid4().hex[:8]}@example.invalid")
    db_session.add(user)
    await db_session.flush()
    return user


def _item(job_id: str, row: ArticleManifest) -> JobItem:
    """在途条目：`manifest_id` 必须真指到清单行——在途面就是从这支关联减文章键的。"""
    return JobItem(
        id=f"i-{uuid.uuid4().hex[:8]}",
        job_id=job_id,
        external_id=row.external_id,
        url=row.url,
        manifest_id=row.id,
    )


def _asset(source_id: str, key: str, status: str = "READY") -> ContentAsset:
    return ContentAsset(
        id=f"a-{uuid.uuid4().hex[:8]}",
        source_id=source_id,
        external_id=key,
        url=_ART_URL,
        title="t",
        content_hash="ah-" + uuid.uuid4().hex[:8],
        content_markdown="# x",
        status=status,
    )


async def test_ready_article_is_not_re_enqueued(db_session) -> None:
    """S4.1.1：P-2 探针转常驻——已 READY 入库的篇，下一轮 Diff 新增数必须是 0。

    改前这条读数是 1（清单拿 `external_id='workUuid-1'` 去减资产的 `external_id=规范键`，
    两支键空间不相交）。反向对照同样关键：资产不是 READY 时必须立刻回到 1，
    否则那个"0"是空种出来的假绿。
    """
    src = await _seed_source(db_session)
    m = _manifest_row(src.id, "workUuid-1", _ART_URL)
    db_session.add(m)
    db_session.add(_asset(src.id, _ART_KEY))
    await db_session.flush()

    svc = SourceSubscriptionService(db_session)
    assert await svc._compute_new_manifests(src.id, "sub-p2") == [], "已入库的篇又被入列 ⇒ P-2 复发"

    asset = (await db_session.scalars(select(ContentAsset).where(ContentAsset.source_id == src.id))).one()
    asset.status = "FETCHED"
    await db_session.flush()
    rows = await svc._compute_new_manifests(src.id, "sub-p2")
    assert [r.id for r in rows] == [m.id], "反向对照没回到 1 条，说明上面那个 0 是空种出来的"


async def test_two_url_forms_of_one_article_enqueue_once(db_session) -> None:
    """S4.1.2：同篇短链/长链两形态各一条清单 ⇒ 一轮只入列一次，入库后两条都不再入列。

    这一条以前是**恒真**的：它写了 `second.article_key = first.article_key`，把要证的等式当成
    前提。真实的 `canonical_article_key` 对两支 URL 给的是**不同的键**
    （长链 `b:<biz>:<mid>:<idx>`、短链 `s:<token>`，见 `article_identity.py:162-170`），
    所以"按 article_key 减"自己并不能把两种形态并起来。能并的唯一既有真源是
    `short_link_maps`——生产里由 `kb.py:_save_short_link` 在短链首抓拿到长链后落一行。
    本用例显式播那一行，并把三个面各钉一次：同轮收敛、跨形态在途、跨形态已入库。
    """
    src = await _seed_source(db_session)
    long_row = _manifest_row(src.id, "workUuid-long", _ART_URL)
    short_row = _manifest_row(src.id, "workUuid-short", _ALT_URL, key=canonical_article_key(_ALT_URL))
    assert short_row.article_key == f"s:{_SHORT_TOKEN}"
    assert short_row.article_key != long_row.article_key, "前提：两支键空间本就不同，减键本身并不了形态"
    db_session.add_all([long_row, short_row])
    db_session.add(ShortLinkMap(short_key=_SHORT_TOKEN, article_key=_ART_KEY, biz=""))
    await db_session.flush()

    svc = SourceSubscriptionService(db_session)
    rows = await svc._compute_new_manifests(src.id, "sub-forms")
    # 断言"只剩一行"而不钉死是哪一行：`created_at` 是**事务**时间戳，同批 flush 的两行它全等，
    # 排序靠 `id` 做 tie-break（见 `_compute_new_manifests`），所以赢的是"确定同一行"而不是"最早那一行"。
    assert len(rows) == 1, f"同篇两形态一轮只该入列一次，实得 {len(rows)} 行"
    again = await svc._compute_new_manifests(src.id, "sub-forms")
    assert [r.id for r in again] == [r.id for r in rows], "同一份数据的收敛结果必须可重复，不能靠查询计划"

    # 在途面跨形态：把入列的那一支挂进活动 Job，被收敛掉的那一支也不能再排一次队
    user = await _seed_user(db_session)
    job = Job(
        type="sync_account",
        user_id=user.id,
        idempotency_key=f"sync_account:sub-forms:{uuid.uuid4().hex[:8]}",
        status="QUEUED",
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add(_item(job.id, rows[0]))
    rows[0].status = MANIFEST_STATUS_ENQUEUED
    await db_session.flush()
    assert await svc._compute_new_manifests(src.id, "sub-forms") == [], "同篇第二形态绕过了在途保护"

    # 入库完成：Job 终态 + READY 资产（资产锚的是长链键），两条都该被减掉
    job.status = "SUCCEEDED"
    db_session.add(_asset(src.id, _ART_KEY))
    await db_session.flush()
    # 这里**不**用 `expire_all()`：`@ci` 真库跑出来的第一条红就是它——expire 之后在 async 会话里
    # 同步访问 `src.id` 会触发一次隐式刷新，SQLAlchemy 直接 `MissingGreenlet`（本机无 PG 时这条
    # 用例整体 skip，所以这个错只在真库上现形）。`flush()` 已经让新资产对后续 SELECT 可见，
    # Diff 每次都是新查询，不需要靠 expire 来"看得见"。
    assert await svc._compute_new_manifests(src.id, "sub-forms") == []


async def test_two_forms_without_a_short_link_map_enqueue_twice(db_session) -> None:
    """把 `_with_effective_keys` 的**局限**钉成事实，而不是写在 docstring 里等人信。

    短链 token 没有映射行 = 这篇还没被真实抓过（映射由首抓写入），此时两种形态本轮各排一次队。
    代价是**一次性**的（抓取落地后映射就位，后续轮次收敛），与 D-V9-01 登记的
    "存量首次再入库各多一次抓取"同族。这条用例的反面就是上面那条：删掉映射行 ⇒ 读数从 1 变 2。
    """
    src = await _seed_source(db_session)
    db_session.add_all(
        [
            _manifest_row(src.id, "workUuid-long", _ART_URL),
            _manifest_row(src.id, "workUuid-short", _ALT_URL, key=canonical_article_key(_ALT_URL)),
        ]
    )
    await db_session.flush()

    svc = SourceSubscriptionService(db_session)
    rows = await svc._compute_new_manifests(src.id, "sub-nomap")
    assert len(rows) == 2, "没有短链映射时不该假装收敛——把不可得的行为改成 1 就是自研判据的那一型假绿"


async def test_null_key_manifest_waits_for_backfill_and_is_counted(db_session) -> None:
    """D-V9-04 的后果必须可见：`article_key IS NULL` 的存量行不入列，但要计数告警。

    两头都钉：① 不被静默丢掉（告警事件名可查）；② 也不被"顺手拿 external_id 顶一下"放进来
    ——那正是 P-2 的复发形状。这条同时是 STEP-07 回填的**门槛读数**：回填前后各跑一次，
    事件里的行数应当从 >0 变 0。
    """
    src = await _seed_source(db_session)
    m = _manifest_row(src.id, "workUuid-nokey", _ART_URL, key=None)
    db_session.add(m)
    await db_session.flush()

    svc = SourceSubscriptionService(db_session)
    with capture_logs() as logs:
        rows = await svc._compute_new_manifests(src.id, "sub-null")
    assert rows == [], "无规范键的行不该入列（拿 NULL 去减资产会让所有无键行互撞成一支键）"
    events = [e for e in logs if e.get("event") == "manifest.diff.null_key_backlog"]
    assert events and events[0]["rows"] >= 1, f"无键积压没出声：{[e.get('event') for e in logs]}"
    assert m.status == MANIFEST_STATUS_DISCOVERED, "Diff 里不该顺手改状态"


async def test_recover_stale_rolls_back_orphan_enqueued_manifest(db_session) -> None:
    """S4.4.3.1：worker 崩溃后，超时且无人认领的 ENQUEUED 回 DISCOVERED——三条对照各拦一种假绿。

    - 超时 + 无活动 Job ⇒ 回退（正例）
    - **没超时** + 无活动 Job ⇒ 不回退（证明时间锚有判定力，而不是"见 ENQUEUED 就退"）
    - 超时 + 有 QUEUED Job 认领 ⇒ 不回退（证明在途保护在起作用，worker 不与自己抢同一篇）
    - DISCOVERED 的旧行 ⇒ 不动（证明回退面只认 ENQUEUED）
    """
    src = await _seed_source(db_session)
    stale = _manifest_row(src.id, "w-stale", _ART_URL, status=MANIFEST_STATUS_ENQUEUED)
    stale.updated_at = datetime.now(UTC) - timedelta(hours=1)
    fresh = _manifest_row(src.id, "w-fresh", _ART_URL, status=MANIFEST_STATUS_ENQUEUED)
    held = _manifest_row(src.id, "w-held", _ART_URL, status=MANIFEST_STATUS_ENQUEUED)
    held.updated_at = datetime.now(UTC) - timedelta(hours=1)
    untouched = _manifest_row(src.id, "w-disc", _ART_URL, status=MANIFEST_STATUS_DISCOVERED)
    untouched.updated_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add_all([stale, fresh, held, untouched])
    await db_session.flush()

    user = await _seed_user(db_session)
    job = Job(
        type="sync_account",
        user_id=user.id,
        idempotency_key=f"sync_account:stale:{uuid.uuid4().hex[:8]}",
        status="QUEUED",
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add(_item(job.id, held))
    await db_session.flush()

    worker = JobWorker(
        _OneSessionCtx(db_session),  # type: ignore[arg-type]
        _noop_ingest,  # type: ignore[arg-type]
        heartbeat_enabled=False,
        manifest_enqueued_ttl_seconds=60,
    )
    assert await worker.recover_stale() == 0, "本轮没有 stale job，返回值不该被清单回退污染"
    # 逐行 `await refresh(...)` 而不是 `expire_all()`：后者把整个 identity map 清空，
    # 之后 `stale.status` 这类**同步**属性访问就在 async 会话里触发隐式刷新 ⇒
    # `MissingGreenlet`（`@ci` 真库上的第二条红）。显式 refresh 是 async 会话里唯一合法的再读法。
    for row in (stale, fresh, held, untouched):
        await db_session.refresh(row)

    assert stale.status == MANIFEST_STATUS_DISCOVERED, "超时且无人认领的 ENQUEUED 必须回 DISCOVERED，否则永久卡死"
    assert fresh.status == MANIFEST_STATUS_ENQUEUED, "没超时也被回退 ⇒ 时间锚失去判定力"
    assert held.status == MANIFEST_STATUS_ENQUEUED, "有 QUEUED Job 认领还被回退 ⇒ 自愈会与在途条目抢同一篇"
    assert untouched.status == MANIFEST_STATUS_DISCOVERED
