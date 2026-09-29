import { describe, expect, it } from "vitest";
import { normalizeMeData } from "../lib/api";

/**
 * C-T7 真实态适配钉死：/auth/me 载荷归一化。
 * 真实后端返回嵌套 { user, wallet }；mock/旧契约为扁平形态。
 * 缺陷背景：真实态 wallet 为对象被直接渲染 → React #31 崩溃。
 */
describe("normalizeMeData — /auth/me 载荷归一化", () => {
  it("真实嵌套形态：user 层解包 + wallet 对象格式化为 ¥ 串", () => {
    const me = normalizeMeData({
      user: {
        sub: "01a08a06",
        email: "c-t7@aidean.local",
        nickname: "C-T7联调",
        tier: "NORMAL",
        role: "USER",
      },
      wallet: {
        balanceYuan: "0.00",
        heldYuan: "0.00",
        availableYuan: "0.00",
        currency: "CNY",
      },
    });
    expect(me).toEqual({
      sub: "01a08a06",
      email: "c-t7@aidean.local",
      nickname: "C-T7联调",
      tier: "NORMAL",
      wallet: "¥0.00",
      is_admin: false,
      providerUnreachable: false,
    });
  });

  it("SPEC-M3 批次 2：is_admin 只认 wire 的 is_admin，主平台 role 枚举一律不驱动", () => {
    // 真实 userinfo 的 role 是大写枚举（USER/ADMIN），与本地授权阶梯不同源。
    // 若有人"顺手"用 role 推导 is_admin，本测立刻失败——门禁就会与后端 10004 分歧。
    expect(
      normalizeMeData({ user: { sub: "s", role: "ADMIN" } }).is_admin
    ).toBe(false);
    expect(
      normalizeMeData({ user: { sub: "s", role: "admin" } }).is_admin
    ).toBe(false);
    expect(normalizeMeData({ user: { is_admin: true } }).is_admin).toBe(true);
    // 兼容历史字符串形态
    expect(normalizeMeData({ user: { is_admin: "true" } }).is_admin).toBe(true);
    // 脏值一律 fail closed
    expect(normalizeMeData({ user: { is_admin: "no" } }).is_admin).toBe(false);
    expect(normalizeMeData({ user: { is_admin: undefined } }).is_admin).toBe(false);
  });

  it("扁平形态（mock/旧契约）：wallet 字符串原样保留", () => {
    const me = normalizeMeData({
      sub: "mock-user-001",
      email: "admin@bothot.local",
      nickname: "演示用户",
      tier: "pro",
      wallet: "¥128.50",
    });
    expect(me.nickname).toBe("演示用户");
    expect(me.wallet).toBe("¥128.50");
  });

  it("非 CNY 币种：币码原样前缀", () => {
    const me = normalizeMeData({
      user: { sub: "s", tier: "NORMAL" },
      wallet: { balanceYuan: 12.5, currency: "USD" },
    });
    expect(me.wallet).toBe("USD 12.50");
  });

  it("字段缺失/null：回空串与 — 兜底，不抛错", () => {
    expect(normalizeMeData(null)).toEqual({
      sub: "",
      email: "",
      nickname: "",
      tier: "",
      wallet: "—",
      is_admin: false,
      providerUnreachable: false,
    });
    const me = normalizeMeData({ user: { nickname: "只昵称" } });
    expect(me.nickname).toBe("只昵称");
    expect(me.sub).toBe("");
    expect(me.wallet).toBe("—");
  });

  it("依赖降级态：主平台不可达时不渲染 ¥0.00（那会把「查不到」谎报成「余额清零」）", () => {
    const me = normalizeMeData({
      user: { sub: "qa-admin-001", email: "qa-admin@bothot.local", nickname: "QA管理员", is_admin: true },
      wallet: { balanceYuan: 0, currency: "CNY", available: false },
      providerUnreachable: true,
    });
    expect(me.providerUnreachable).toBe(true);
    expect(me.wallet).toBe("余额暂不可查");
    expect(me.is_admin).toBe(true);
  });

  it("仅 wallet.available === false 未标 providerUnreachable：同样不渲染 ¥0.00", () => {
    const me = normalizeMeData({
      user: { sub: "s" },
      wallet: { balanceYuan: "0.00", currency: "CNY", available: false },
    });
    expect(me.wallet).toBe("余额暂不可查");
  });

  it("未标记降级的零余额：仍是 ¥0.00（区分「真的 0」与「查不到」）", () => {
    const me = normalizeMeData({
      user: { sub: "s" },
      wallet: { balanceYuan: "0.00", currency: "CNY" },
    });
    expect(me.wallet).toBe("¥0.00");
    expect(me.providerUnreachable).toBe(false);
  });
});
