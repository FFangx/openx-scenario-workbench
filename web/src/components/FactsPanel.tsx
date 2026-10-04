import { useState } from "react";
import { Alert, App, Button, Collapse, Modal, Popconfirm, Table, Tag } from "antd";
import { CheckCircleOutlined, EditOutlined, HistoryOutlined } from "@ant-design/icons";
import { api, type Revision, type Scene, type SceneStructure } from "../api";
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
  target_speeds_kph: ["目标速度（km/h）", "Target speeds (km/h)"],
  lateral_direction: ["横向方向", "Lateral direction"],
  lane_direction: ["车道方向", "Lane direction"],
  weather: ["天气", "Weather"],
  time_of_day: ["时段", "Time of day"],
  end_condition: ["结束条件", "End condition"],
};

const isStructured = (s: Scene): s is Scene & { structure: SceneStructure } => Object.keys(s.structure ?? {}).length > 0;

/** Saved facts exactly as stored: zero stays zero and missing stays "not specified"; nothing is inferred. */
export function FactsPanel({ projectId, scene, onChanged }: { projectId: string; scene: Scene; onChanged: (s: Scene) => void }) {
  const { t, lang } = useT();
  const { message } = App.useApp();
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState<Revision[] | null>(null);
  const [busy, setBusy] = useState(false);

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

  const rows: [string, unknown][] = [];
  let params: Record<string, unknown>;
  let primary: string[];
  if (isStructured(scene)) {
    const s = scene.structure;
    rows.push([t("道路类型", "Road type"), s.road_class], [t("被测功能", "Tested function"), s.tested_function],
      [t("试验目的", "Test intent"), s.test_intent], [t("主车动作", "Ego actions"), s.ego_actions], [t("触发条件", "Trigger types"), s.semantic_triggers]);
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

  const publish = async () => {
    setBusy(true);
    try {
      await api.publish(projectId, scene.document_id, scene.scene_id, scene.revision);
      message.success(t("已保存到全局需求场景库，可在资产管理中查看。", "Saved to the shared requirement library in Asset management."));
      onChanged({ ...scene, published: true, queue_status: scene.queue_status === "assessed" ? "assessed" : "confirmed" });
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const openHistory = () => api.revisions(projectId, scene.document_id, scene.scene_id).then(setHistory).catch((e: Error) => message.error(e.message));

  return (
    <div className="facts">
      <div className="facts-head">
        <span className="sec-title">{t("已保存的需求事实", "Saved requirement facts")}</span>
        <span className="muted">{t(`修订 ${scene.revision}`, `Revision ${scene.revision}`)}</span>
        <Tag className={`mtag ${scene.published ? "direct" : "review"}`}>{scene.published ? t("已确认入库", "Published") : t("待确认", "Not published")}</Tag>
      </div>
      {scene.preferred_text && <p className="facts-text">{scene.preferred_text}</p>}
      <table className="fact-sheet">
        <tbody>
          {rows.map(([name, item], i) => (
            <tr key={i}><th scope="row">{name}</th><td>{value(item)}</td></tr>
          ))}
        </tbody>
      </table>
      {participants.length > 0 && (
        <>
          <div className="sec-title facts-sub">{t("其他参与者", "Other participants")}</div>
          <table className="fact-sheet actors">
            <thead>
              <tr>{[t("参与者类型", "Participant"), t("方位", "Bearing"), t("朝向", "Facing"), t("动作", "Actions")].map((h) => <th key={h} scope="col">{h}</th>)}</tr>
            </thead>
            <tbody>
              {participants.map((a, i) => (
                <tr key={i}>{(["kind", "bearing", "facing", "actions"] as const).map((k) => <td key={k}>{value(a[k])}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {scene.issues.map((issue, i) => <Alert key={i} type="warning" showIcon title={issue} className="facts-alert" />)}
      {scene.ocr && <p className="muted facts-note">{t("包含本机 OCR 识别的证据，请对照原文复核。", "Includes locally recognized OCR evidence; review against the source.")}</p>}

      <div className="facts-actions">
        <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>{t("编辑事实", "Edit facts")}</Button>
        <Popconfirm
          title={t("确认此修订并入库？", "Confirm and publish this revision?")}
          description={t("入库的是已保存的修订；未保存的编辑不会包含在内。", "The saved revision is published; unsaved edits are not included.")}
          onConfirm={publish} okText={t("确认入库", "Publish")} cancelText={t("取消", "Cancel")} disabled={scene.published}
        >
          <Button icon={<CheckCircleOutlined />} disabled={scene.published} loading={busy}>
            {scene.published ? t("当前修订已入库", "Revision published") : t("确认并入库", "Confirm and publish")}
          </Button>
        </Popconfirm>
        {scene.revision > 1 && <Button icon={<HistoryOutlined />} onClick={openHistory}>{t("修订历史", "Revision history")}</Button>}
      </div>
      <p className="muted facts-note">
        {scene.published ? t("当前修订已确认入库。", "The current revision is published.")
          : t("保存事实和确认入库是两个步骤；检索和匹配使用已保存的事实。", "Saving facts and publishing are separate steps; matching uses the saved facts.")}
      </p>
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
