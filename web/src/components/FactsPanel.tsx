import { useState } from "react";
import { Alert, App, Button, Collapse, Modal, Table, Tag, Tooltip } from "antd";
import { EditOutlined, HistoryOutlined } from "@ant-design/icons";
import { api, urls, type FieldEvidence, type Revision, type Scene, type SceneStructure } from "../api";
import { useT } from "../i18n";
import { valueLabel } from "../vocab";
import { FactEditor } from "./FactEditor";

const UNKNOWN = new Set(["", "未知", "unknown", "未知方位", "未知朝向"]);

export const PARAM_LABEL: Record<string, [string, string]> = {
  ego_speed_kph: ["主车速度（km/h）", "Ego speed (km/h)"],
  ttc_value: ["TTC (s)", "TTC (s)"],
  lane_count: ["车道数", "Lane count"],
  curve_radius_m: ["弯道半径（m）", "Curve radius (m)"],
  fog_visibility_m: ["能见度（m）", "Visibility (m)"],
  speed_limits_kph: ["限速标志（km/h）", "Speed limit signs (km/h)"],
  target_speeds_kph: ["目标速度（km/h）", "Target speeds (km/h)"],
  lateral_direction: ["横向方向", "Lateral direction"],
  lateral_speeds_mps: ["横向速度（m/s）", "Lateral speeds (m/s)"],
  lateral_speed_range_mps: ["横向速度范围（m/s）", "Lateral speed range (m/s)"],
  lane_direction: ["车道方向", "Lane direction"],
  weather: ["天气", "Weather"],
  time_of_day: ["时段", "Time of day"],
  end_condition: ["结束条件", "End condition"],
};

const isStructured = (s: Scene): s is Scene & { structure: SceneStructure } => Object.keys(s.structure ?? {}).length > 0;

/** Where a spatial fact comes from: stated, implied (with its reasoning), read from a figure (shown
 * on hover with what was seen in it) or to check; the quote on hover. */
function EvidenceMark({ item, figure }: { item?: FieldEvidence; figure?: string }) {
  const { t } = useT();
  if (!item || (item.source === "未知" && !item.review)) return null;
  const drawn = item.source === "图";
  const [label, tone] = item.review ? [t("待复核", "Check"), "review"]
    : item.source === "推出" ? [t("推出", "Implied"), "modify"]
    : drawn ? [t("看图", "Figure"), "modify"] : [t("原文", "Stated"), "not"];
  const lines = [
    item.quote && (drawn ? t(`示意图：${item.quote}`, `Figure: ${item.quote}`) : t(`原文：“${item.quote}”`, `Source: “${item.quote}”`)),
    // A figure reading says what the figure shows in its own words, under the figure.
    item.reason && (drawn ? item.reason : t(`推理：${item.reason}`, `Reasoning: ${item.reason}`)),
    item.review,
  ].filter(Boolean) as string[];
  return (
    <Tooltip title={<div className="evidence-tip">
      {figure && <img className="evidence-figure" src={figure} alt={item.quote ?? ""} />}
      {lines.map((line, i) => <div key={i}>{line}</div>)}
    </div>}>
      <Tag className={`mtag ${tone} evidence-mark`} tabIndex={0}>{label}</Tag>
    </Tooltip>
  );
}

/** Saved facts exactly as stored: zero stays zero and missing stays "not specified"; nothing is inferred. */
export function FactsPanel({ projectId, scene, onChanged }: { projectId: string; scene: Scene; onChanged: (s: Scene) => void }) {
  const { t, lang } = useT();
  const { message } = App.useApp();
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState<Revision[] | null>(null);

  const value = (item: unknown): React.ReactNode => {
    if (item == null || (typeof item === "string" && UNKNOWN.has(item)) || (Array.isArray(item) && !item.length)
      || (typeof item === "object" && !Array.isArray(item) && !Object.keys(item as object).length)) {
      return <span className="fact-unknown">{t("未明确", "Not specified")}</span>;
    }
    if (typeof item === "number") return String(Number(item.toPrecision(15)));
    if (Array.isArray(item)) return item.map((x) => (typeof x === "object" ? JSON.stringify(x) : valueLabel(String(x), lang))).join(" · ");
    if (typeof item === "object") return JSON.stringify(item);
    return valueLabel(String(item), lang);
  };
  const label = (key: string) => (PARAM_LABEL[key] ? t(...PARAM_LABEL[key]) : key);

  const rows: [string, unknown, FieldEvidence?][] = [];
  let params: Record<string, unknown>;
  let primary: string[];
  if (isStructured(scene)) {
    const s = scene.structure;
    rows.push([t("道路类型", "Road type"), s.road_class], [t("被测功能", "Tested function"), s.tested_function],
      [t("试验目的", "Test intent"), s.test_intent], [t("主车动作", "Ego actions"), s.ego_actions],
      [t("主车路口走向", "Ego at the junction"), s.ego_turn, s.evidence?.ego_turn], [t("主车车道", "Ego lane"), s.ego_lane, s.evidence?.ego_lane],
      [t("交通控制设施", "Traffic control"), s.traffic_controls], [t("触发条件", "Trigger types"), s.semantic_triggers]);
    params = s.params ?? {};
    primary = ["ego_speed_kph", "target_speeds_kph", "ttc_value", "lane_count", "weather", "time_of_day"];
  } else {
    rows.push([t("道路类型", "Road types"), scene.road_types], [t("参与者", "Participants"), scene.entities],
      [t("动作", "Actions"), scene.actions], [t("触发条件", "Triggers"), scene.triggers]);
    params = { ...scene.parameters };
    if (!("ttc_value" in params) && "ttc_s" in params) {
      params.ttc_value = params.ttc_s;
      delete params.ttc_s;
    }
    primary = ["ego_speed_kph", "ttc_value", "lane_count"];
  }
  primary.forEach((key) => rows.push([label(key), params[key]]));
  Object.entries(params).forEach(([key, item]) => !primary.includes(key) && item != null && rows.push([label(key), item]));
  if (!isStructured(scene)) rows.push([label("weather"), scene.weather], [label("time_of_day"), scene.time_of_day]);
  const participants = isStructured(scene) ? scene.structure.participants ?? [] : [];
  const reviewFlags = isStructured(scene) ? scene.structure.review_flags ?? [] : [];
  const marked = rows.some(([, , item]) => item) || participants.some((a) => Object.keys(a.evidence ?? {}).length);
  // The figure a fact was read from, cut out of its page.
  const figure = (item?: FieldEvidence) => {
    const found = item?.source === "图" ? scene.figures?.find((f) => f.label === item.quote?.replace(/\s+/g, "")) : undefined;
    return found && urls.page(projectId, scene.document_id, found.page, 360, found.clip);
  };

  const openHistory = () => api.revisions(projectId, scene.document_id, scene.scene_id).then(setHistory).catch((e: Error) => message.error(e.message));

  return (
    <div className="facts">
      <div className="facts-title" title={scene.title}>{scene.section_id && <span className="muted">{scene.section_id}</span>} {scene.title}</div>
      <div className="facts-head">
        <span className="sec-title">{t("已保存的需求事实", "Saved requirement facts")}</span>
        <span className="muted">{t(`修订 ${scene.revision}`, `Revision ${scene.revision}`)}</span>
      </div>
      {scene.preferred_text && <p className="facts-text">{scene.preferred_text}</p>}
      <table className="fact-sheet">
        <tbody>
          {rows.map(([name, item, evidence], i) => (
            <tr key={i}><th scope="row">{name}</th><td>{value(item)} <EvidenceMark item={evidence} figure={figure(evidence)} /></td></tr>
          ))}
        </tbody>
      </table>
      {participants.length > 0 && (
        <>
          <div className="sec-title facts-sub">{t("其他参与者", "Other participants")}</div>
          <table className="fact-sheet actors">
            <thead>
              <tr>{[t("参与者类型", "Participant"), t("方位", "Bearing"), t("朝向", "Facing"), t("动作", "Actions"), t("速度（km/h）", "Speed (km/h)"), t("任选组", "Either-or")].map((h) => <th key={h} scope="col">{h}</th>)}</tr>
            </thead>
            <tbody>
              {participants.map((a, i) => (
                <tr key={i}>{(["kind", "bearing", "facing", "actions", "speed_kph", "alternative_group"] as const).map((k) => (
                  <td key={k}>{value(a[k])}{k in (a.evidence ?? {}) && <> <EvidenceMark item={a.evidence?.[k]} figure={figure(a.evidence?.[k])} /></>}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {marked && <p className="muted facts-note">{t("“原文”“推出”“看图”标出方位、朝向、车道等事实的依据，悬停可看引句或示意图；“待复核”请对照原文核对。", "“Stated”, “Implied” and “Figure” show what bearings, facings and lanes rest on; hover for the quote or the figure. Check items marked “Check” against the source.")}</p>}
      {reviewFlags.map((flag, i) => <Alert key={`r${i}`} type="warning" showIcon title={flag} className="facts-alert" />)}
      {scene.issues.map((issue, i) => <Alert key={i} type="warning" showIcon title={issue} className="facts-alert" />)}
      {scene.ocr && <p className="muted facts-note">{t("包含本机 OCR 识别的证据，请对照原文复核。", "Includes locally recognized OCR evidence; review against the source.")}</p>}

      <div className="facts-actions">
        <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>{t("编辑事实", "Edit facts")}</Button>
        {scene.revision > 1 && <Button icon={<HistoryOutlined />} onClick={openHistory}>{t("修订历史", "Revision history")}</Button>}
      </div>
      <p className="muted facts-note">{t("候选检索和复用建议均基于已保存的需求事实；修改后，已确认的结论将标为“待重新确认”。", "Candidate search and reuse suggestions use the saved facts; editing them marks a confirmed conclusion for reconfirmation.")}</p>
      <Collapse size="small" ghost items={[{
        key: "raw",
        label: t("结构与分类（原始记录）", "Structure and classification (raw)"),
        children: <pre className="json-view">{JSON.stringify({ structure: scene.structure, classification: scene.classification }, null, 2)}</pre>,
      }]} />

      <FactEditor open={editing} onClose={() => setEditing(false)} projectId={projectId} scene={scene}
        onSaved={(s) => { setEditing(false); onChanged(s); message.success(t(`已保存修订 ${s.revision}`, `Saved revision ${s.revision}`)); }} />
      <Modal title={t("修订历史", "Revision history")} open={history !== null} onCancel={() => setHistory(null)} footer={null} width={640}>
        <Table<Revision>
          size="small"
          rowKey="revision"
          pagination={false}
          dataSource={history ?? []}
          columns={[
            { title: t("修订", "Revision"), dataIndex: "revision", width: 70 },
            { title: t("标题", "Title"), dataIndex: "title", ellipsis: true },
            { title: t("参数", "Parameters"), key: "p", ellipsis: true, render: (_, r) => JSON.stringify(Object.keys(r.structure ?? {}).length ? (r.structure as SceneStructure).params : r.parameters) },
          ]}
        />
      </Modal>
    </div>
  );
}
