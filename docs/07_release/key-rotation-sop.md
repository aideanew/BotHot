---
id: KEY-ROTATION-SOP
type: convention
title: 落库加密主密钥轮换规程（SOP）
status: active
owner: engineering
created: 2026-09-30
updated: 2026-09-30
version: 1.0
---

# 落库加密主密钥轮换规程（SOP）

> **状态**：active（W7 交付，2026-09-30）
> **适用范围**：`PUSH_SECRET_MASTER_KEY` 与 `ENGINE_KEY_MASTER_KEY` 两把落库加密主密钥。
> **配套工具**：`scripts/rotate_keys.sh`（**默认 dry-run**，零写入）。
> **一句话**：本仓的主密钥是**单密钥、无版本化 keyring**。轮换 = 「换密钥」**+**「重加密存量密文」，
> 只做前一半会让旧密文**永久不可解**——而这不是推测，是解密路径 fail-closed 的直接后果（见 §2）。

---

## 0. 事实基线（读源码实证，非推测）

| 主密钥 | 加密什么 | 密文形态 | AAD 绑定 | 密钥缺失/畸形时 | 解密失败时的后果 |
|---|---|---|---|---|---|
| `PUSH_SECRET_MASTER_KEY` | `bot_channels.secret_enc`（飞书/钉钉加签密钥等） | `b64(nonce).b64(ct+tag)` | `bot_channel.id` | `DependencyUnavailableError`（fail-closed，绝不回落明文） | 渠道投递全拒 |
| `ENGINE_KEY_MASTER_KEY` | `engine_key_registrations.secret_ref`（main/coze/dify/fastgpt 的 API Key） | 同上 | `engine` 名 | 同上 | 该引擎被报成「未配置」 |

| 事实 | 证据位置 |
|---|---|
| 两个主密钥各自**只有一个** `master`，没有 keyring / key version / 多密钥并存 | `core/secret_crypto.py:27,30`；`core/engine_keyring.py:67` |
| 密钥长度固定 32 字节（AES-256）；非 32 字节即拒绝 | `core/secret_crypto.py:24`；`core/engine_keyring.py:33` |
| 密文格式 `b64(nonce).b64(ct+tag)`，两段各自 base64 编码 | `core/secret_crypto.py:50-68`；`core/engine_keyring.py:92-103` |
| AAD 绑定，密文**不可**在渠道/引擎位之间搬移（换 id 解密必失败） | `core/secret_crypto.py:70-94`；`core/engine_keyring.py:106-120` |
| 密钥轮换后，旧密文解密**抛 `RequestInvalidError`**，不返回空、不回落明文 | 同上（`except InvalidTag … raise RequestInvalidError`） |
| 渠道密钥的历史存量里可能有**旧式 base64（非 AES）**形态 | `is_aes_ciphertext()` / `decrypt_legacy_base64()`，`core/secret_crypto.py:96-110` |
| 线上启动守卫把两把主密钥的**缺失**列为违规项（共 7 项） | `core/config.py:205-241`（主密钥两项在 `:236,:238`） |

**结论（本规程的全部前提）**：这两把主密钥**没有平滑过渡能力**——不存在「新旧密钥并排、都能解」的状态。
因此轮换的唯一安全形态是：**在同一个事务里把存量密文从旧密钥重加密为新密钥**，然后才切 env。

---

## 1. 触发条件

| 类型 | 触发场景 | 时限 |
|---|---|---|
| **事件驱动（最高优先）** | 主密钥出现在 git 历史 / CI 日志 / 聊天记录 / 第三方工单；承载密钥的机器或备份介质丢失、被入侵；曾接触密钥的人员离职 | **立即**（先按 §6 评估影响面，再执行 §4） |
| **定期** | 常规密钥轮换周期 | 建议 **12 个月**一次（无合规硬要求时的工程默认）；有等保/客户审计要求时按其要求 |
| **被动** | `security.yml` 的 gitleaks 步骤检出主密钥形态字符串（🔴 阻断） | 在解除阻断前完成轮换 |
| **恢复** | env 与库内密文已经不一致（例如误改了 env）：`scripts/rotate_keys.sh --verify` 报不可解 | 按 §6 回滚，不要盲目轮换 |

---

## 2. 为什么不能「只改 env」

这是本规程最容易被误判的一点，写清楚以免再犯：

- 对运行时而言，`PUSH_SECRET_MASTER_KEY` 只是**一把**钥匙。换成新值后，库里那些用旧值加密的密文
  在新钥匙下解密必然失败（AAD + GCM tag 校验不过）。
- 失败不是「降级成明文」——`decrypt_channel_secret` 抛 `RequestInvalidError`
  （`core/secret_crypto.py:70-94`），调用方 `push_scheduler.py:183` 会让该渠道的投递整体失败；
  `engine_keys.py:89` 则会把该引擎判成「未配置」，**回落 env 或直接不可用**。
- 也就是说：**只改 env = 一次全渠道投递故障 + 引擎凭据全失效**，且因为 fail-closed，
  它看起来「什么都不报错、只是全都不能用」，排查成本高。

所以：**改 env 是轮换的最后一步，不是第一步。**

---

## 3. 处置总流程（六阶段）

```text
① 冻结      停止渠道/引擎凭据的变更操作（避免边改边漏）
      ▼
② 前置检查  rotate_keys.sh --verify  确认「当前部署密钥」能解开全部存量密文
      ▼
③ 干跑      rotate_keys.sh（默认 dry-run）确认影响行数与后续步骤
      ▼
④ 重加密    rotate_keys.sh --apply  备份 → 单事务重加密 → 产出新 env 文件
      ▼
⑤ 切换      替换部署环境密钥 → **滚动重启 backend / scheduler / worker 三进程**
      ▼
⑥ 验证+销毁 --verify 与一次真实投递 → 清理备份与旧密钥的所有副本
```

---

## 4. 详细步骤（命令级）

### 4.1 前置检查

```bash
# 需要：目标库 DSN + 当前部署的两把密钥（与后端进程用的完全一致）
export DATABASE_URL='postgresql+psycopg://<user>:<pass>@<host>:<port>/<db>'
export PUSH_SECRET_MASTER_KEY='<当前部署值>'
export ENGINE_KEY_MASTER_KEY='<当前部署值>'
export PYTHON=/path/to/backend/venv/bin/python   # 需同时具备 sqlalchemy / cryptography / backend 包

bash scripts/rotate_keys.sh --verify
```

- **必须看到** `✅ 当前 env 密钥可解开全部存量密文`。出现「不可解」= 当前 env 密钥不是当初加密它的那把，
  **不要继续轮换**，转到 §6。
- 顺带确认存量形态：输出会报「其中旧式 base64 明文 N 行」。N > 0 表示有历史存量，
  轮换时会一并升级为 AES 密文（这是顺带收益，需在变更单里说明）。

### 4.2 干跑（默认行为，零写入）

```bash
bash scripts/rotate_keys.sh
```

输出会列出：备份路径、将重加密的行数、是否刷新 `key_id`、新 env 文件路径，
以及**脚本刻意不做**的人工步骤。不带 `--apply` 时脚本**不连库写入、不创建任何文件**。

### 4.3 执行重加密

```bash
# 生产环境建议把产物与备份放到仓库外
export BACKUP_DIR=/var/backups/bothot-key-rotation
bash scripts/rotate_keys.sh --apply
```

`--apply` 依次做五件事，任一步失败即整轮中止：

1. **备份**：把受影响密文导出为 JSON 快照（配合旧密钥即可回滚）。
2. **重加密渠道密钥**：逐行 `旧密钥解密 → 新密钥加密`，AAD 仍是各行的 `bot_channels.id`。
3. **重加密引擎 Key**：同上，AAD 仍是 `engine` 名。
4. **刷新 `key_id`**：它是「轮换/审计句柄」（`models/entities.py:259`），服务层每次覆盖登记都会换新
   （`services/engine_keys.py:110,122`、`api/v1/admin.py:354`）。密文变了而句柄不变会让审计链路指错版本。
   如需保留旧值：`ROTATE_REFRESH_KEY_ID=0`。
   > ⚠️ **这一点是本规程里唯一「脚本改了运行时可观测值」的地方**（`GET /engines` 返回的 `keyId` 会变）。
   > 若不希望轮换触碰该字段，请显式设 `ROTATE_REFRESH_KEY_ID=0` 并把该决定记录到变更单。
5. **产出新 env 文件**：写到 `$BACKUP_DIR/env.rotated-<ts>`，**不直接改 `.env`**——改环境文件是运维动作，
   由脚本静默改写会造出「密钥换了但没人知道」的形态。

**安全约束（脚本已内建，不可绕过）**：

- 新密钥与旧密钥相同 → **拒绝执行**（这会给出「已轮换」的假象，比不轮换更危险）。
- 全程不打印任何明文或密钥值，只打印 id / 行数 / 状态。
- 三步重加密在**单事务**内完成（`engine.begin()`），不存在「渠道换了、引擎没换」的半轮换。
- 产物目录内置 `*` 规则自我忽略（`.gitignore`），密钥与快照永不进 git 视野。
  `git check-ignore -v $BACKUP_DIR/keys-backup-*.json` 可自证。

### 4.4 替换环境密钥并滚动重启

```bash
cat "$BACKUP_DIR/env.rotated-<ts>"     # 审阅后才替换
```

1. 把两行新值写入部署环境（K8s Secret / Compose env / 配置中心的同名键）。
2. **滚动重启 `backend` / `scheduler` / `worker` 三个进程**。
   - 三个进程都参与解密：Web 侧读渠道与引擎状态，scheduler 按渠道投递，worker 跑任务。
   - **缺任何一个**都会出现「一部分进程能解、另一部分解不了」的分裂状态——
     典型症状是「手动测试投递成功、定时投递全失败」。
3. 重启顺序无关，但**必须全部重启完再进入验证**。

### 4.5 验证

```bash
# ① 用新密钥复核全部存量密文
bash scripts/rotate_keys.sh --verify        # 期望 ✅

# ② 业务面真实验证（比 ① 更有说服力：它走的是完整解密链路）
#    - 管理端触发一次「测试投递」到任一已配置渠道 → 期望 delivered=true
#    - GET /api/v1/engines → 已登记引擎应显示「已配置」，而不是回落成「未配置」
```

> ① 与 ② 都要做。①只证明密文可解，②才证明**进程真的拿到了新密钥**（漏重启会在这里暴露）。

### 4.6 清理与销毁

- [ ] `--verify` 通过 + 一次真实渠道投递成功 + 引擎状态正确
- [ ] 删除 `$BACKUP_DIR/env.rotated-*` 与 `keys-backup-*.json`
- [ ] 销毁**旧密钥的所有副本**：配置中心历史版本、K8s Secret 旧 revision、部署脚本、
      临时文件、聊天记录、工单、CI 变量、备份介质
- [ ] 在变更单记录：轮换时间、执行人、受影响行数、验证证据
- [ ] 若为事件驱动（泄露），补充事故复盘到 `docs/08_knowledge/`

> 备份文件是**密文快照**：旧密钥一旦销毁，它既无回滚价值、又只剩泄露面，必须一并清理。

---

## 5. 替代路径：引擎 Key 可以「清空重登记」

引擎 Key 与渠道密钥有一个关键差别：**明文在 operator 手上**（登记时由人输入，
`POST /api/v1/admin/...`，见 `services/engine_keys.py:98`）。因此引擎侧有一条更省事的路：

1. 记录当前各引擎位的 Key（从密钥管理系统里取，不要从数据库取）。
2. `ENGINE_KEY_MASTER_KEY` 换成新值，重启三进程。
3. 逐个重新登记（登记即用当前密钥重新加密；`secret_ref` 与 `key_id` 都会换新）。
4. 对未重新登记的引擎位：`resolve_engine_key()` 会回落 env，env 也没有则判为「未配置」——
   这是**可见**的失败（不是静默错误），但仍应以「全部重新登记」为完成标准。

**渠道密钥没有这条捷径**：`secret_enc` 的明文只在加密那一刻存在（`bots.py:199,274`），
库里的密文是它的唯一副本。所以渠道侧**必须**走 §4 的重加密路径。

---

## 6. 回滚

| 场景 | 症状 | 处置 |
|---|---|---|
| **已换 env、未重加密**（最常见的人为失误） | `--verify` 报「不可解」；渠道投递全拒 | 把 env **改回旧值**并重启三进程 → 立即恢复。然后按 §4 走正确顺序（先重加密，后换 env）。 |
| **已 apply、env 出错或新密钥丢失** | `--verify` 报「不可解」 | 用 `keys-backup-<ts>.json` 配合旧密钥回写密文：`--apply` 时显式传 `OLD_*=新密钥`、`NEW_*=旧密钥`（即反向重加密），再换回 env。 |
| **备份也丢了、旧密钥也没了** | 密文永不可解 | **不可逆**。渠道密钥只能重新向飞书/钉钉/企微平台申请并重新填写（走 `PATCH /api/v1/bots/channels/{id}`，`bots.py:274`）；引擎 Key 按 §5 重新登记。数据面无需回滚（密文本身就是唯一的数据），补齐凭据即可恢复。 |

> 记住一个不变式：**「哪把密钥能解开当前密文」这件事，只能通过 `--verify` 得知，不能靠记忆。**

---

## 7. 未被主密钥覆盖的敏感面（**重要发现**）

主密钥只保护上面两列。以下敏感面**不在**本规程覆盖范围内，需要单独处置：

| 面 | 现状 | 处置建议 |
|---|---|---|
| `bot_channels.extra_config` | **明文 JSON**（`models/bothot_entities.py:35-36` 的注释明确写着它承载「飞书 app_id/app_secret、钉钉 access_token 等」），主密钥**不加密它** | 走平台侧「重置应用密钥」而非本规程；若要落库加密，需另立变更（属数据模型改动） |
| `bot_channels.webhook_url` | 明文（设计如此：相当于门牌号） | 泄露风险由平台 webhook 的加签机制承担，不视为密钥 |
| `OIDC_CLIENT_SECRET`、`SESSION_COOKIE_*` | 环境变量，不入库、不被主密钥加密 | 走各自的平台侧轮换流程；`OIDC_CLIENT_SECRET` 仍是占位值时启动守卫会拒绝（`core/config.py:224-225`） |
| 上游 provider 的 API Key（Dajiala / JustOneAPI / TikHub / Wellbyte / SiliconFlow 等） | 环境变量 | 由对应平台侧轮换 |

---

## 8. 局限与本规程的已知缺口

1. **无 keyring / 无双密钥过渡**：这是本规程最大的结构性风险——任何轮换都伴随一次
   「重加密窗口」，窗口内若进程被滚动重启到一半，会出现短暂的分裂状态。
   缓解手段只有「一次把三进程全部重启完」。
   > **建议（不属本工作流范围，需架构线决策）**：为两个模块引入多密钥 keyring
   > （`key_id → master` 映射 + 「用最新密钥加密、按 key_id 解密」），
   > 则轮换退化为「加一把新钥匙 → 滚动重启 → 重加密 → 删旧钥匙」，全程无需停机。
   > 这与 `engine_key_registrations.key_id` 既有的「轮换/审计句柄」语义天然契合。
2. **`--apply` 不是幂等操作**：重复执行会用又一把新密钥再次重加密（结果正确但需再切一次 env）。
   执行前请确认没有并发的第二次执行。
3. **多实例并发**：脚本不取分布式锁。必须保证轮换期间**没有第二个 operator 同时执行**，
   且滚动重启与 `--apply` 不重叠。
4. **本规程只覆盖「主动轮换」**，不覆盖「密钥疑似泄露时的取证」（日志审计、影响面评估）——
   那属于事故响应流程，见 `docs/08_knowledge/` 下的复盘文档（待建）。

---

## 9. 附录 A：脚本用法速查

| 命令 | 作用 | 是否写库 |
|---|---|---|
| `rotate_keys.sh` | 计划（**默认**） | ❌ |
| `rotate_keys.sh --verify` | 校验当前部署密钥能否解开全部存量密文 | ❌ |
| `rotate_keys.sh --apply` | 备份 + 重加密 + 产出新 env 文件 | ⚠️ 单事务重写两列 |
| `rotate_keys.sh --generate push\|engine` | 只生成一把新主密钥并打印 | ❌ |
| `rotate_keys.sh --help` | 用法 | ❌ |

关键环境变量：`DATABASE_URL`、`PUSH_SECRET_MASTER_KEY`、`ENGINE_KEY_MASTER_KEY`、
`OLD_*`（**仅 `--apply` 生效**）、`NEW_*`（缺省自动生成）、`PYTHON`、`BACKUP_DIR`、`ROTATE_REFRESH_KEY_ID`。

> **`--verify` 与 `--apply` 取密钥的规则不同，且这个差异是有意的**：
> - `--verify` 回答「**当前部署的**密钥能否解开存量密文」→ 只认 `PUSH_SECRET_MASTER_KEY` / `ENGINE_KEY_MASTER_KEY`，
>   **忽略** `OLD_*`。若它也认 `OLD_*`，环境里一把陈旧的 `OLD_*` 会让校验答成另一个问题
>   （报 FAIL 或报 OK 都可能与真实部署无关），校验的全部价值就没了。
> - `--apply` 回答「库里那份密文是**用哪把钥匙**上的」→ `OLD_*` 优先（恢复场景下 env 已换、库未换）。
>
> 两种模式都会在输出里打印**「解密所用渠道/引擎密钥」的来源**，结论永远可追溯到具体变量名。

## 10. 附录 B：本地可复现的证据

本规程与脚本的行为已用隔离 PG（端口 5546）做过端到端往返验证，覆盖 9 个判据：
默认零写入、旧密钥可解、重加密成功、新密钥可解、**旧密钥转为不可解**、
明文保真、`key_id` 刷新、AAD 绑定未被破坏、拒绝「新==旧」假轮换。

复现方式（改 `DATABASE_URL` 指向无用库即可安全重跑）：

```bash
export DATABASE_URL='postgresql+psycopg://bothot:bothot@127.0.0.1:5546/bothot'
export PYTHON=/path/to/backend/venv/bin/python
bash scripts/rotate_keys.sh --verify      # 第 ①②④⑤ 判据
bash scripts/rotate_keys.sh               # 第 1 判据（零写入）
```

## 11. S2.1：extra_config 同受主密钥覆盖（2026-10-08 起）

`bot_channels.extra_config`（飞书 app_secret / 钉钉 access_token 等）自迁移
`ab1005w5b` 起为 AES-256-GCM 密文，AAD = `{channel_id}:extra_config`（域分隔，
与 secret_enc 密文不可互换）。

**轮换影响**：本规程的窗口期双密钥重加密**必须同时覆盖 extra_config 列**——
只重加密 secret_enc 会让所有 extra_config 在新密钥下永久不可解（fail-closed，
运行时投递路径 400 语义）。`scripts/rotate_keys.sh` 若未扩展列覆盖，轮换后需手工执行：

```sql
-- 窗口期重加密（应用内完成，SQL 仅示意读取范围）
SELECT id, extra_config FROM bot_channels WHERE extra_config <> '' AND extra_config NOT LIKE '{%';
```

**存量兼容**：读侧 `decrypt_extra_config` 对 `{` 开头的明文 JSON 原样放行
（兜底迁移前存量行 / 迁移回滚场景），密文解密失败 fail-closed。
迁移期纪律：存在明文待迁行而主密钥缺失 → **中止迁移**（与 ab1004w1a 同裁定）。
