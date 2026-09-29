/**
 * 引导页共享类型与步骤定义（R0.6.2 由 app/onboarding/page.tsx 抽出）
 *
 * `STEPS` 同时被步骤条（StepIndicator）、步骤面板（StepPanels）与
 * 页面本地的断点校验（`readProgress` 用 `STEPS.length` 判越界）引用，
 * 留在页面里会让三处各自 import 同一段字面量。
 */
export interface StepDef {
  id: number;
  label: string;
  desc: string;
}

export interface OnboardingProgress {
  step: number;
  spaceId: string;
  spaceName: string;
  engine: string;
  savedAt: number;
}

/** 引导页三步定义（步号即用户心智里的「第 N 步」） */
export const STEPS: readonly StepDef[] = [
  { id: 1, label: "起名建库", desc: "给知识库起个名字，选引擎" },
  { id: 2, label: "选来源", desc: "粘贴文章或订阅公众号" },
  { id: 3, label: "提问", desc: "基于来源开始问答" },
];
