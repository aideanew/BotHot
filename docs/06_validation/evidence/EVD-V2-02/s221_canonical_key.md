# S2.2.1 + S2.2.2：文章规范键落地（ADR-0011），调用点迁移留下一批

批次：`STEP-02` S2.2.1（用例）+ S2.2.2（实现），基线 `main@281bb86`。
读数标机器位（`@win` = 本机 Win10 + `apps/api/.venv`）。

## 1. 交付面

`apps/api/app/services/article_identity.py` 新增两个公开函数（`__all__` 已同步）：

- `normalize_url(url)` —— scheme/host 小写、去 fragment、去追踪参数（含 `utm_*`）、其余参数按 (键,值) 排序。
- `canonical_article_key(url)` —— ADR-0011 §2 的三分支：
  `b:{biz}:{mid}:{idx}` / `s:{token}` / `h:` + `sha256(normalize_url(url))[:32]`，解析一律委托 `parse_wechat_url`。

ADR-0011 §3 的**五条不变量逐条有归属用例**（`tests/test_article_identity.py`，本批 +10 条 ⇒ 24 条）：

| 不变量 | 用例 |
|---|---|
| ①任何输入 ≠ `s` 且长度 ≥ 8 | `test_every_input_yields_a_usable_key`（12 条语料）+ `test_bare_short_path_is_no_longer_the_letter_s` |
| ②同篇长链书写无关 | `test_same_article_with_tracking_or_fragment_shares_the_key` |
| ③同 `__biz` 不同 `mid` 必异键 | `test_same_biz_different_mid_diverges` |
| ④`s:` ∈ [8,64]、`h:` 恒 34 | `test_short_link_and_offsite_branches`、`test_malformed_long_link_falls_back_to_hash_branch` |
| ⑤不得自己再解析一遍 URL | `test_canonical_key_does_not_reparse_the_url`（AST） |

## 2. 实现期做的三个判断（都不是显然的）

1. **脏输入抛 `TypeError`，不归零成常量键**。`parse_wechat_url` 的口径是"非 str 归零返回"，
   但身份键层若照抄，所有脏输入会共享同一个键（静默碰撞）——那比抛出来坏。
2. **`normalize_url` 对"没有 scheme 也没有 host"的输入原样返回**。归一把 `""` 与 `"/"` 都折成 `/`，
   两种无关脏输入于是得到同一个文章身份；这条是我写语料唯一性断言时**被撞出来的**，不是想到的。
3. **`+` 的口径在这里与 `parse_wechat_url` 故意不同**：那边把裸 `+` 当字面加号（防 `__biz` 裂成两条资产），
   这里按 form 口径还原成空格——因为产物只是哈希输入串，要的是"同篇同串"，不是"值可逆"。
   写在 docstring 里，免得后来人当成一处笔误"顺手统一"。

## 3. 两条我自己造的缺陷，由既有证明件抓出来（这一节是本文件的主要价值）

- **PI-1 导入白名单**：`EVD-V2-02/prove_article_identity.py:73` 的 `ALLOWED_IMPORTS` 只有
  `{__future__, dataclasses, urllib.parse}`，我加 `hashlib` 后 `--self-test` 立刻 BAD。
  处置是**把 `hashlib` 加进白名单并注明理由**（ADR-0011 §2 定义上要求 sha256；hashlib 是标准库、纯计算、无 IO），
  而**不是**把 `import hashlib` 挪进函数体绕过扫描——后者正是"合规靠位置而不是靠理由"的规避，
  且本仓库 `kb.py::_hash` 已有那种写法，我不再复制它。
- **`inspect.getsource` 在证明通道里不可用**：PI-6 的等价重构（把 `_DEFAULT_IDX` 内联成字面量）
  报我的 AST 用例假红。根因不是实现变了语义，而是证明件把实现 **exec 进内存**，
  那时 `getsource` 抛 `OSError: source code not available` ⇒ 用例会**因为运行方式**而红。
  处置：AST 用例改为按 `article_identity.__file__` 读源码 + `ast.parse` + `ast.get_source_segment`，
  两条通道都成立（`SELF-TEST PASS` 复测）。这条也写进用例 docstring，防止将来被"简化"回 getsource。
  顺带修的是我自己写错的锚：先是 `or _DEFAULT_IDX)`（实际是 `...}`），self-test 的锚存在性检查直接拒绝了我猜的锚。

## 4. 读数（`@win`）

- `pytest tests/test_article_identity.py -q` → **24 passed**（本批 +10）
- `pytest tests/test_article_identity.py tests/test_kb_longlink_ingest.py -q` → **35 passed**
  （后者是 `parse_wechat_url` 的下游依赖，按"调用面而不是主题"选的）
- `--cov=app.services.article_identity` → **52 statements / 0 miss = 100%**（卡面 S2.2.2.2）
- `ruff check app/services/article_identity.py tests/test_article_identity.py` → `All checks passed!`
- `mypy app/services/article_identity.py` → `Success: no issues found in 1 source file`
- `prove_article_identity.py` → `合计 PASS=12 FAIL=0`；`--self-test` → `SELF-TEST PASS`
  （12 个实现变异体各自让指定用例变红 + 17 个判据样本对敏感 + 4 个等价重构不假红 + cp936 编码自证）

## 5. 本批**没有**做（为什么没做）

- **S2.2.3 调用点迁移**：`kb.py` 五处（现读 `:241/:282/:461/:467/:510`，不是卡面写的 235/276/426/432/471）
  与 `_save_short_link` 仍走旧的 `_article_key`。规范键现在**没有任何生产者**，只有消费者（测试）。
  理由：这一改会动入库身份 ⇒ 存量资产键与新模式并存，必须同时做 S2.2.4 的历史兼容（旧裸 token 只读再查一次），
  否则短链二次入库会重抓。两者拆开推就是把自己刚在 S1.4.3 犯过的"局部绿当全量绿"再犯一次。
- **S2.3.3 batch_ingest 委托 + 漂移守卫**（`batch_ingest.py:44` 是同一算法的第二份实现）。
- **S2.2.4 历史兼容**、**S2.2.3.3 P-3 探针转正**（`test_kb_longlink_ingest.py::test_two_distinct_long_links`，期望 fetch_count=2）、
  **S2.2.3.4** `test_kb_multisource_anchor.py:76` 的 `assert key == "s"` 前提改写。
- 没跑全量后端套件：本批只**新增**函数与新用例，无调用者行为变化；调用面 =
  `grep -rn "article_identity" app tests` 的全部命中（`kb.py:634` 与 `test_kb_longlink_ingest.py:51`，都只 import
  `parse_wechat_url`），两条都已实跑。

状态：**S2.2.1 / S2.2.2 已确认（`@win`）**；S2.2.2.1 的"S2.2.1 转绿"与 S2.2.2.2 的 100% 覆盖达成。
下一步是 S2.2.3 + S2.2.4 + S2.3.3 同批（它们互为前提），做完才谈得上 STEP-02 的 `@ci` 判定。
