// Stored vocabulary (Chinese labels and status codes) shown in the interface language.
// Mirrors _VALUES/_ZH in src/openx_workbench/asset_management.py.
import type { Lang } from "./api";

const EN: Record<string, string> = {
  未知: "Unknown", 直道: "Straight", 弯道: "Curve", 交叉口: "Intersection", 停车场: "Parking", 环岛: "Roundabout", 匝道: "Ramp",
  乘用车: "Passenger car", 商用车: "Commercial vehicle", 两轮车: "Two-wheeler", 行人: "Pedestrian", 骑行者: "Cyclist",
  障碍物: "Obstacle", 动物: "Animal",
  rule_only: "Rule classified", classified: "Model reviewed", manual_confirmed: "Confirmed", failed: "Failed", pending: "Pending",
  not_tested: "Not tested", playable: "Playable", warning: "Warning", unsupported: "Unsupported", timeout: "Timed out",
};
const ZH: Record<string, string> = {
  rule_only: "规则分类", classified: "模型复核", manual_confirmed: "人工确认", failed: "失败", pending: "待分类",
  not_tested: "未测试", playable: "可播放", warning: "有警告", unsupported: "不支持", timeout: "超时",
};

export const valueLabel = (value: string, lang: Lang) => (lang === "zh" ? ZH[value] : EN[value]) ?? value;

/** Preview states that mean the version was tried and could not play. */
export const PREVIEW_FAILED = new Set(["failed", "unsupported", "timeout"]);
