# @ci 步级读数（S1.3.1 的验收面，D-V4-01：契约收编 Done 只能由 @ci ubuntu 判）

- run_id=38731161342  job_id=116409001417  job=backend  head_sha=`6ec473aefcbfa12bda322a12f6f4122d49c88891`
- job conclusion=**success**（2026-10-15T11:58:27Z → 12:01:09Z）
- 步 **「Contract drift gate (gen_contracts --check)」= success**
  （取自 `jobs_ci_6ec473a.json` 的 `steps[]`，原始响应同目录）
  ⇒ CI 接受了新提交的产物 `packages/contracts/schemas/collection.schema.json`，
  且 6 个 dto.ts 仍与生成结果一致。**这一步没有 `continue-on-error`，失败即 fail job。**
- 同 run 其余 job：workflow-lint / backend / frontend / compose / compose-smoke 全 success；
  `Security` 另一个工作流 run 38731161065 = success。

## 这条读数的**适用范围**（别把它读成它没说的东西）

它证明的是**字符比较版**（`read_text()`）在 CI 上绿。
本文件写完后 `check()` 改成**字节比较**（`read_bytes()`），
所以"字节比较版在 @ci 上也绿"目前是**推断**（依据：`.gitattributes` 钉 `* text=auto eol=lf`，
ubuntu 检出即 LF），**凭据未取**。取到之后追加在下面，取不到就红着说明。

## 字节比较版的 @ci 读数（后续提交，**已取到**）

- 提交 `c1657d6`（把 `check()` / `check_schemas()` 改成 `read_bytes()` 之后）
- run_id=**38734298632**  job_id=**116419550320**  job=backend  conclusion=**success**
  （2026-10-15T12:23:46Z → 12:26:22Z；原始响应 `jobs_ci_c1657d6.json`）
- 步 **「Contract drift gate (gen_contracts --check)」= success**
  ⇒ 前面写的"CI 按 `.gitattributes` 检出 LF ⇒ 字节比较预期 rc=0"这条**推断被读数证实**，
  不再是推断。同 run `Security` run 38734298616 = success。
- 反面仍成立：本机 worktree 那 6 个 dto.ts 在字节比较版之前是 CRLF，
  `@win` 直接跑 `--check` 当时 rc=1（这正是字节比较想抓的东西，不是 CI 的问题）。
