// Stored vocabulary (Chinese labels and status codes) shown in the interface language.
// Mirrors _VALUES/_ZH in src/openx_workbench/asset_management.py.
import type { Lang } from "./api";

const EN: Record<string, string> = {
  未知: "Unknown", 直道: "Straight", 弯道: "Curve", 交叉口: "Intersection", 停车场: "Parking", 环岛: "Roundabout", 匝道: "Ramp",
  乘用车: "Passenger car", 商用车: "Commercial vehicle", 两轮车: "Two-wheeler", 行人: "Pedestrian", 骑行者: "Cyclist",
  障碍物: "Obstacle", 动物: "Animal",
  rule: "Rule labels", rule_only: "Rule classified", classified: "Model reviewed", manual_confirmed: "Confirmed", failed: "Failed", pending: "Pending",
  not_tested: "Not tested", playable: "Playable", warning: "Warning", unsupported: "Unsupported", timeout: "Timed out",
  road_missing: "Road file missing",
  // typed requirement vocabulary (src/openx_workbench/pdf_v2/scene_schemas.py)
  高速路: "Motorway", 匝道合流: "Ramp merge", 卡车: "Truck", 客车: "Bus", 厢式车: "Van", 挂车: "Trailer", 摩托车: "Motorcycle",
  三轮车: "Tricycle", 正前方: "Ahead", 正后方: "Behind", 并排同车道: "Alongside, same lane", 左前方: "Front left", 左后方: "Rear left",
  左并排: "Alongside left", 右前方: "Front right", 右后方: "Rear right", 右并排: "Alongside right", 未知方位: "Unknown bearing",
  同向: "Same direction", 对向: "Oncoming", 横向: "Crossing", 静止: "Stationary", 匀速行驶: "Constant speed", 变速: "Speed change",
  刹停: "Brake to stop", 变道: "Lane change", 定距跟车: "Follow at distance", 倒车: "Reverse", 偏离车道: "Lane departure", 被测系统控制: "System under test",
  遮挡: "Occlusion", 相对距离: "Relative distance", 绝对距离: "Absolute distance", 车头时距: "Time headway", 速度: "Speed",
  相对速度: "Relative speed", 晴天: "Clear", 雨天: "Rain", 雾天: "Fog", 雪天: "Snow", 沙尘: "Sand or dust", 日间: "Day", 夜间: "Night",
  儿童: "Child", 成人: "Adult", 隧道: "Tunnel", 收费站: "Toll station", 服务区: "Service area", 实线: "Solid line", 虚线: "Dashed line",
  泊入: "Park in", 泊出: "Park out", 功能试验: "Functional test", 误作用试验: "False activation test", 激活边界试验: "Activation boundary test",
  驾驶员干预试验: "Driver intervention test", 左: "Left", 右: "Right", 单向: "One-way", 双向: "Two-way",
  直行: "Straight on", 左转: "Left turn", 右转: "Right turn", 掉头: "U-turn", 交通信号灯: "Traffic light", 限速标志: "Speed limit sign",
  最左侧车道: "Leftmost lane", 最右侧车道: "Rightmost lane", 中间车道: "Middle lane",
};
const ZH: Record<string, string> = {
  rule: "规则生成", rule_only: "规则分类", classified: "模型复核", manual_confirmed: "人工确认", failed: "失败", pending: "待分类",
  not_tested: "未检测", playable: "可播放", warning: "有警告", unsupported: "不支持", timeout: "超时",
  road_missing: "道路文件缺失",
};

export const valueLabel = (value: string, lang: Lang) => (lang === "zh" ? ZH[value] : EN[value]) ?? value;

// Road features (parser road types), e.g. inferred from a map name when the road file is missing.
const ROAD_FEATURES: Record<string, string> = {
  straight: "直道", curve: "弯道", junction: "交叉口", motorway: "高速路", parking: "停车场", roundabout: "环岛",
};
export const roadFeatureLabel = (feature: string, lang: Lang) => valueLabel(ROAD_FEATURES[feature] ?? feature, lang);

/** Preview states that mean the version was tried and could not play. */
export const PREVIEW_FAILED = new Set(["failed", "unsupported", "timeout"]);
