import { vi } from "vitest";

/**
 * S35.4（P-105 / D-V18-08）：单元测试禁止拨网——未桩的 `fetch` 直接抛错。
 *
 * 旧行为：happy-dom 基址是 localhost:3000（主平台端口），未被 mock 覆盖的相对路径
 * fetch 真的去连，拿 ECONNREFUSED（AggregateError）后要么被组件吞掉、要么被 node
 * 当未处理拒绝打印——39 处/49 文件全绿 ⇒ "没有后端的机器照样绿"，判定力是假的。
 *
 * 这里的抛错桩是**底线**而不是 mock：谁真的需要 fetch，谁就 `vi.stubGlobal("fetch", …)`
 * 声明自己要什么形状的响应；桩会覆盖本抛错桩。反证判据见
 * `tests/setup-fetch-guard.spec.ts`：删掉一个用例自己的桩 ⇒ 它必须红。
 */
const _original = globalThis.fetch;
void _original; // 保留引用便于排查（本桩按文件环境安装，不做全局恢复）

globalThis.fetch = vi.fn(async (..._args: Parameters<typeof fetch>): Promise<Response> => {
  throw new Error(
    "S35.4 fetch-guard：单测拨了未桩的 fetch。请 vi.stubGlobal('fetch', …) 声明期望的响应"
      + "（P-105：单元测试禁止真实网络；基址已钉 http://localhost:3200/）",
  );
}) as unknown as typeof fetch;
