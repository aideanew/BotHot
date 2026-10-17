---
id: ADR-0011
type: decision
title: 文章规范键（canonical article key）格式
status: accepted
owner: architecture
created: 2026-10-15
updated: 2026-10-15
---

# ADR-0011：文章规范键格式

- **裁决**：D-V2-01 = 方案 A，已签（`docs/03_solution/decisions/decision-log.md` 第 41 行，2026-10-15 12:04，用户授权代选）。
- **关联**：D-V3-01（键空间统一）、D-13（host 闸门）、STEP-02 S2.2、STEP-01（契约收编）、STEP-04（`article_manifests.article_key`）、STEP-07（存量回填）。
- **命名约定**：本目录历史为小写 `adr-NNNN-kebab-slug.md`，本文件随该约定；历次规划正文写作大写 `ADR-0011` 是同一对象的另一种称呼，以本文件路径为准。

## 1. 背景与被否证的现状

`apps/api/app/services/kb.py:554-557` 的 `_article_key(url)` 只做两件事：剥掉 `[?&#]` 之后的部分、取 `rsplit("/")[-1]`。
对微信**长链** `https://mp.weixin.qq.com/s?__biz=…&mid=…&idx=1&sn=…` 而言，剥掉 query 后末段就是字母 `s` ⇒

- **同一公众号同一号的两篇不同文章得到同一个键**（P-3 冒名：等值查 `external_id='s'` 会命中同号首篇资产，`hitCache=True` 但内容不是那一篇）。
- 旧版为此加过 `Source.url.like('%article_key%')` 兜底，反而让 `scalar_one_or_none()` 抛 `MultipleResultsFound`（P-4，500）。该兜底已在 `078dc30` 删除，删除时又带入短链二次入库重抓的回归（STEP-R0 处理）。

实测锚：`apps/api/tests/test_kb_multisource_anchor.py:75` 至今用 `assert key == "s"` 把这个退化形状钉成用例前提；`docs/任务规划V0.3.0/evidence/probes_4afaedd.txt:19` 是 P-4 的实跑崩栈读数。

## 2. 决策

```
canonical_article_key(url: str) -> str
  p = parse_wechat_url(url)                     # apps/api/app/services/article_identity.py:54，唯一解析源，不改
  if p.host == "mp.weixin.qq.com":
      if p.biz and p.mid:   return f"b:{p.biz}:{p.mid}:{p.idx or '1'}"
      if p.short_token:     return f"s:{p.short_token}"
  return "h:" + sha256(normalize_url(url)).hexdigest()[:32]
```

`normalize_url`：scheme/host 小写；去 fragment；去追踪参数
（`chksm scene srcid from isappinstalled clicktime enterid sessionid ascene devicetype version lang
exportkey key uin pass_ticket wx_header nettype utm_*`）；其余参数按键排序。

**理由**：前缀让三种来源（长链、短链、非微信）互不碰撞且**自描述来源**——看到 `b:` 就知道可解出 biz/mid/idx，
看到 `h:` 就知道是不可解析 URL 的降级身份。这让"键来自哪里"成为可读事实，而不是需要回查 URL 才能推断。
正则可校验，故能进契约（`ArticleKey.pattern`）并被契约测试锚住。

## 3. 不变量（契约测试锚，STEP-01 S1.4.1 / STEP-02 S2.2.1）

1. 任何输入的返回值 ≠ `"s"`，且长度 ≥ 8。
2. 同一篇文章的长链（含或不含追踪参数、含或不含 fragment）→ **同一个** `b:` 键。
3. 同一 `__biz` 下两个不同 `mid` → **不同**键（直接否证 §1 的坍缩）。
4. `s:` 分支的 token 长度 ∈ [8, 64]；`h:` 分支恒 34 字符（`h:` + 32 hex）。
5. 规范键函数**不得**在自己内部重新实现 URL 解析——必须委托 `parse_wechat_url`（单一来源；
   `apps/api/tests/test_asset_fragment_guard.py` 一带的 AST 判据同族）。

## 4. 与短链映射的关系

首次抓取前短链只能得 `s:` 键；抓取后经 `ShortLinkMap(short_key → article_key=b:…)` 归一
（`kb.py:274-278` 改为写规范键）。注意该表的写入条件是 `final_key != short_key`，
直抓后 URL 不变的短链写不进去 ⇒ **不能用映射表替代 STEP-R0 的资产反查**（V0.6.0 STEP-R0 §3 已列此为被否决方案③）。

## 5. 历史兼容与回填

- 缓存未命中规范键时，**仅短链**再用旧裸 token 只读查一次（不改写数据）；改写归 STEP-07 回填脚本。
- 存量 `content_assets.external_id` 含 `"s"` 与裸 token 两类脏键 ⇒ 回填前**不得**依赖等值查做跨号判定；
  `MIN_FRAGMENT_LEN=8` 这条长度守卫在回填完成前继续承担实际防护（见 `apps/api/app/repositories/asset.py:22`）。
- 回填顺序：DDL（`ab1006c1a`，STEP-04）→ 只读审计 → dry-run → 测试库实跑并验证可回滚 → 备份 → 生产实跑（D-V2-06）。

## 6. 代价与局限

- 键变长（≤128，`String(128)` 现有列宽足够，**零迁移**即可写入），外部若有人按裸 token 查询需适配——
  仓内消费方只有 `kb.py` 与 `services/batch_ingest.py` 两处，可控。
- 本 ADR 只定"怎么生成键"，**不解决**"已存在的错键数据怎么办"（STEP-07），也**不改变**
  `Source.external_id = biz or _article_key(url)` 这一源侧键口径（D-V3-01 只统一文章身份）。
- `h:` 分支对"同一篇文章的不同镜像 URL"给不同键——这是有意的（无法证明同源就不同源），
  但意味着站外转载不会产生缓存命中。

## 7. 验收（本 ADR 生效的机器判据）

```bash
# @linux/@ci：以下三项全绿才算落地
cd apps/api
.venv/bin/python -m pytest tests/test_article_identity.py -q -k canonical
.venv/bin/python -m pytest tests/test_kb_longlink_ingest.py -q -rs        # P-3：同号两篇各自独立入库
grep -rn 'rsplit("/")' app/services/kb.py app/services/batch_ingest.py     # 期望仅剩委托前的兼容薄壳或空
```

## 8. 实施期更正（2026-10-16，不重开裁决）

§2 的伪码按字面实现时，**§3.1 / §3.4 与 §6 的"≤128 零迁移"三条都不成立**。
第二轮独立验证（读数 `EVD-V2-02/s221_canonical_key.md` §6）实测四类产物，全部被契约 `ArticleKey` 拒收：

| 输入（`Source.url` 这类自由字段真能装进去） | 按 §2 字面实现的输出 | 违反了什么 |
|---|---|---|
| `?__biz=MjM5&mid=1&idx=1` | `b:MjM5:1:1` | biz 段 4 字符 < `{8,64}` |
| `/s/abc` | `s:abc` | 总长 5 < `minLength: 8` |
| `?__biz=` + 130×`A` | 136 字符的 `b:` 键 | 超 `maxLength: 128` ⇒ **Postgres `varchar(128)` 直接 DataError**，"零迁移"是假的 |
| `?__biz=AAAAAAAA:B&mid=C` 与 `?__biz=AAAAAAAA&mid=B:C` | **同一个键串** `b:AAAAAAAA:B:C:1` | `b:` 用 `:` 分段，`:` 逃进段值就冒名 ⇒ 与本 ADR 要消灭的 §1 坍缩同族 |

**更正的口径**：§2 的三分支与 §2 的理由（前缀自描述来源）**不变**；变的是采纳条件——
`b:` / `s:` 两支必须先验证整键形状（`article_identity.CANONICAL_B_KEY` / `CANONICAL_S_KEY`，
字符类与长度界与契约三支逐段同文），验证不过则降级 `h:`。`h:` 恒 34 字符、恒被接受，
且是"归一后 URL"的哈希，所以脏输入之间不会共享身份（这也是为什么 `normalize_url` 对
无 scheme 且无 host 的输入**原样返回**而不是归零——否则 `""` 与 `/` 会折成同一个串）。

判据侧的反证已进 `docs/06_validation/evidence/EVD-V2-02/prove_article_identity.py` 的 `MUTANTS`
（新增三条：摘掉 b: 验证 / 摘掉 s: 验证 / 让脏输入重新折叠），`--self-test` 逐条确认指定用例变红。
§7 的三条验收命令不变，仍然有效。

## 8. 数字段规范化（2026-10-17，V0.13.0 STEP-02 S2.4 追加）

`b:` 支里的 `mid`/`idx` 是**整数语义**：微信服务端按数字解析它们，所以
`mid=02650&idx=01` 与 `mid=2650&idx=1` 指向同一篇文章。键函数因此对这两段做
`_canon_int`：纯 ASCII 十进制才 `str(int(x))`（去前导零），其余**原样保留**，
再由 `ArticleKey` 的 pattern 把关。两个边界是这条规范化的成立条件，不是实现细节：

- `"²".isdigit()` / `"٥".isdigit()` 在 Python 里为真而 `int("²")` 抛 ValueError ⇒ 判据必须是
  `isascii() and isdigit()`，否则一条脏 URL 会把解析函数变成运行期崩溃；
- `mid="0"` 规范化后仍是 `"0"` 而不是空串 ⇒ 空 `mid` 在本 ADR 里有独立语义（掉 `h:` 兜底支），
  把零抹成空等于把一种身份坍缩换成另一种。

同一篇文章的**短链与长链**仍是两支不同的键（`s:<token>` 与 `b:<biz>:<mid>:<idx>`），这不在
本 ADR 的"同文同键"范围内解决：并键的读侧真源是 `short_link_maps`，见决策台账 D-V9-06
与 `docs/06_validation/evidence/EVD-V13-22/`、STEP-04 卡头。
证据：`docs/任务规划V0.13.0/evidence/314d7f2/probe_leading_zero.txt`；
判据：`apps/api/tests/test_article_identity.py` 的 S2.4 三条（含两条反极性）。
