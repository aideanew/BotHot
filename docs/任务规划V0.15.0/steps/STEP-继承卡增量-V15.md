# 继承卡增量（V0.15.0）

权威卡面仍在 `docs/任务规划V0.13.0/steps/`（D-V11-07）。本版只有一项增量。

## STEP-15b +1（P-34 / D-V12-09）
| L3 | 内容 | 判据 | owner |
|---|---|---|---|
| S15b.V15.1 | vitest 全局 setup 把 `fetch`（及 `XMLHttpRequest` 若存在）换成“调用即抛并带调用栈”的桩；各 spec 需要网络时显式 `vi.stubGlobal` 声明 | 先红：在任一 spec 里调一次未桩 fetch ⇒ 红并点名文件；r043 spec 在 CI-Windows 连续 3 个 head_sha 绿；禁止 `retry` | 规划方 |

## 状态更新（不增项）
- 00P：✅（验收①依 D-V12-04 在 @linux 非空批 rc=0 判已确认；@win 面随 STEP-27 S27.4）。
- 00T：V14.1/V14.2/V14.3 已交付，余原 9 项。
- 00R：V14.1 已交付，余原 9 项。
- 00H：仍余 S00H.2.3（缺 Windows durations；执行方 07 §7）。
