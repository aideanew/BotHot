/**
 * engine 域 — 契约 DTO
 *
 * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）
 * 源：packages/contracts/schemas/engine.schema.json（← apps/api/app/contracts/engine.py，ADR-0008）
 */

export interface EngineCapability {
  activeSource: string | null;
  allowlisted: boolean;
  available: boolean;
  configured: boolean;
  decryptFailed: boolean;
  description: string;
  engine: string;
  implemented: boolean;
  keyEnv: string;
  reason: EngineReason;
}

export interface EngineList {
  defaultEngine: string;
  items: Array<EngineCapability>;
}

export type EngineReason = "ok" | "not_allowlisted" | "key_missing" | "not_implemented";

export interface SpaceEngineBinding {
  engine: string;
  engineKbId: string;
  spaceId: string;
}
