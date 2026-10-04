import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Collapse, Drawer, Form, Input, InputNumber, Select, Space, Spin, Table } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { api, type Participant, type Scene, type SceneSchema, type SceneStructure } from "../api";
import { useT } from "../i18n";
import { valueLabel } from "../vocab";

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: string;
  scene: Scene;
  onSaved: (s: Scene) => void;
}

let schemaCache: Promise<SceneSchema> | null = null;
const loadSchema = () => (schemaCache ??= api.sceneSchema());

const NUMERIC: [string, string, string][] = [
  ["ego_speed_kph", "主车速度（km/h）", "Ego speed (km/h)"],
  ["ttc_value", "碰撞时间 TTC（s）", "Time to collision (s)"],
  ["lane_count", "车道数量", "Lane count"],
  ["curve_radius_m", "弯道半径（m）", "Curve radius (m)"],
  ["fog_visibility_m", "能见度（m）", "Visibility (m)"],
];
const LEGACY: [keyof Scene, string, string][] = [
  ["entities", "参与者", "Participants"], ["actions", "动作", "Actions"], ["triggers", "触发条件", "Triggers"],
  ["road_types", "道路", "Road types"], ["weather", "天气", "Weather"], ["time_of_day", "时段", "Time of day"],
];
const EMPTY_ACTOR: Participant = { kind: "未知", bearing: "未知方位", facing: "未知", actions: [], age: "未知" };

/** Typed requirement facts; saving creates a new revision and matching uses it. Narrative never overrides the structure. */
export function FactEditor({ open, onClose, projectId, scene, onSaved }: Props) {
  const { t, lang } = useT();
  const structured = Object.keys(scene.structure ?? {}).length > 0;
  const [schema, setSchema] = useState<SceneSchema | null>(null);
  const [title, setTitle] = useState(scene.title);
  const [text, setText] = useState(scene.preferred_text);
  const [draft, setDraft] = useState<SceneStructure>(scene.structure as SceneStructure);
  const [useJson, setUseJson] = useState(false);
  const [json, setJson] = useState("");
  const [legacy, setLegacy] = useState<Record<string, string[]>>({});
  const [parameters, setParameters] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    loadSchema().then(setSchema).catch((e: Error) => setError(e.message));
    const copy = structuredClone(scene.structure) as SceneStructure;
    if (structured) copy.params = { ...(copy.params ?? {}) };
    setTitle(scene.title);
    setText(scene.preferred_text);
    setDraft(copy);
    setUseJson(false);
    setJson(JSON.stringify(scene.structure, null, 2));
    setLegacy(Object.fromEntries(LEGACY.map(([k]) => [k, [...(scene[k] as string[])]])));
    setParameters(JSON.stringify(scene.parameters));
    setError(null);
  }, [open, scene, structured]);

  const options = (key: keyof SceneSchema) => (schema?.[key] ?? []).map((v) => ({ value: v, label: valueLabel(v, lang) }));
  const set = (patch: Partial<SceneStructure>) => setDraft((d) => ({ ...d, ...patch }));
  const setParam = (key: string, value: unknown) => setDraft((d) => ({ ...d, params: { ...d.params, [key]: value } }));
  const actors = draft?.participants ?? [];
  const setActor = (i: number, patch: Partial<Participant>) => set({ participants: actors.map((a, j) => (j === i ? { ...a, ...patch } : a)) });

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const edits: Record<string, unknown> = { title, preferred_text: text };
      if (structured) {
        edits.structure = useJson ? JSON.parse(json) : draft;
      } else {
        Object.assign(edits, legacy);
        edits.parameters = JSON.parse(parameters || "{}");
      }
      onSaved(await api.revise(projectId, scene.document_id, scene.scene_id, edits));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const actorColumns = [
    { key: "kind", title: t("类型", "Type"), width: 108, render: (_: unknown, a: Participant, i: number) => <Select size="small" value={a.kind} options={options("participant_kind")} onChange={(v) => setActor(i, { kind: v })} style={{ width: "100%" }} /> },
    { key: "bearing", title: t("相对方位", "Bearing"), width: 112, render: (_: unknown, a: Participant, i: number) => <Select size="small" value={a.bearing} options={options("bearing")} onChange={(v) => setActor(i, { bearing: v })} style={{ width: "100%" }} /> },
    { key: "facing", title: t("朝向", "Facing"), width: 86, render: (_: unknown, a: Participant, i: number) => <Select size="small" value={a.facing} options={options("facing")} onChange={(v) => setActor(i, { facing: v })} style={{ width: "100%" }} /> },
    { key: "actions", title: t("动作", "Actions"), render: (_: unknown, a: Participant, i: number) => <Select size="small" mode="multiple" value={a.actions} options={options("participant_actions")} onChange={(v) => setActor(i, { actions: v })} style={{ width: "100%" }} /> },
    { key: "age", title: t("年龄", "Age"), width: 80, render: (_: unknown, a: Participant, i: number) => <Select size="small" value={a.age ?? "未知"} options={options("age")} onChange={(v) => setActor(i, { age: v })} style={{ width: "100%" }} /> },
    { key: "x", width: 36, render: (_: unknown, __: Participant, i: number) => <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label={t("删除参与者", "Remove participant")} onClick={() => set({ participants: actors.filter((_, j) => j !== i) })} /> },
  ];

  return (
    <Drawer
      title={t(`编辑事实 · ${scene.title}`, `Edit facts · ${scene.title}`)}
      open={open}
      onClose={onClose}
      size={structured ? 760 : 560}
      destroyOnHidden
      extra={<Space><Button onClick={onClose}>{t("取消", "Cancel")}</Button><Button type="primary" loading={saving} onClick={save}>{t("保存事实修订", "Save fact revision")}</Button></Space>}
    >
      {!schema && structured ? <div className="center-pad"><Spin /></div> : (
        <Form layout="vertical" className="fact-editor">
          <p className="muted">{t("编辑后保存为新的事实修订；匹配会使用已保存的事实。原文证据不会改变。", "Saving creates a new fact revision that matching then uses. The source evidence is unchanged.")}</p>
          {error && (
            <Alert type="error" showIcon title={t("修订未保存。请检查数值和结构格式；你的输入仍保留在表单中。", "Revision was not saved. Check values and structure; your inputs remain in the form.")} description={error} />
          )}
          <Form.Item label={t("场景标题", "Scene title")} required>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Form.Item>
          <Form.Item label={t("场景说明", "Interpretation")}>
            <Input.TextArea value={text} onChange={(e) => setText(e.target.value)} autoSize={{ minRows: 2, maxRows: 6 }} />
          </Form.Item>
          {structured ? (
            <>
              <fieldset disabled={useJson} className="editor-fields">
                <div className="editor-grid">
                  <Form.Item label={t("道路类型", "Road type")}><Select value={draft.road_class} options={options("road_class")} onChange={(v) => set({ road_class: v })} disabled={useJson} /></Form.Item>
                  <Form.Item label={t("试验目的", "Test intent")}><Select value={draft.test_intent} options={options("test_intent")} onChange={(v) => set({ test_intent: v })} disabled={useJson} /></Form.Item>
                  <Form.Item label={t("被测功能", "Tested function")}><Select showSearch value={draft.tested_function} options={options("tested_function")} onChange={(v) => set({ tested_function: v })} disabled={useJson} /></Form.Item>
                  <Form.Item label={t("天气", "Weather")}><Select value={(draft.params.weather as string) ?? "未知"} options={options("weather")} onChange={(v) => setParam("weather", v)} disabled={useJson} /></Form.Item>
                  <Form.Item label={t("主车动作", "Ego actions")}><Select mode="multiple" value={draft.ego_actions} options={options("ego_actions")} onChange={(v) => set({ ego_actions: v })} disabled={useJson} /></Form.Item>
                  <Form.Item label={t("时段", "Time of day")}><Select value={(draft.params.time_of_day as string) ?? "未知"} options={options("time_of_day")} onChange={(v) => setParam("time_of_day", v)} disabled={useJson} /></Form.Item>
                </div>
                <p className="muted">{t("空白表示原文未明确；只有下面的数值字段参与匹配。文字说明不会自动转换为参数。", "Blank means unspecified. Matching uses these numeric fields; narrative does not update them.")}</p>
                <div className="editor-grid">
                  {NUMERIC.map(([key, zh, en]) => (
                    <Form.Item key={key} label={t(zh, en)}>
                      <InputNumber min={0} style={{ width: "100%" }} value={(draft.params[key] as number | null) ?? null} onChange={(v) => setParam(key, v ?? null)} disabled={useJson} />
                    </Form.Item>
                  ))}
                  <Form.Item label={t("结束条件", "End condition")}>
                    <Input value={(draft.params.end_condition as string) ?? ""} onChange={(e) => setParam("end_condition", e.target.value || null)} disabled={useJson} />
                  </Form.Item>
                </div>
                <Form.Item label={t("触发条件类型", "Trigger types")}>
                  <Select mode="multiple" value={draft.semantic_triggers} options={options("semantic_triggers")} onChange={(v) => set({ semantic_triggers: v })} disabled={useJson} />
                </Form.Item>
                <div className="sec-head">
                  <span className="sec-title">{t("其他参与者", "Other participants")}</span>
                  <Button size="small" icon={<PlusOutlined />} onClick={() => set({ participants: [...actors, { ...EMPTY_ACTOR }] })} disabled={useJson}>{t("添加参与者", "Add participant")}</Button>
                </div>
                <p className="muted">{t("原文未说明的字段请保留未知。", "Keep facts the source does not state as unknown.")}</p>
                <Table<Participant> size="small" pagination={false} rowKey={(_, i) => String(i)} dataSource={actors} columns={actorColumns} className="actor-editor"
                  locale={{ emptyText: t("没有其他参与者", "No other participants") }} />
              </fieldset>
              <Collapse size="small" className="editor-advanced" items={[{
                key: "json",
                label: t("高级结构编辑", "Advanced structure editor"),
                children: (
                  <>
                    <p className="muted">{t("参与者关系、目标速度等专门字段会保留。勾选后以 JSON 替换完整结构。", "Relations, target speeds and specialized fields are preserved. Enable JSON to replace the entire structure.")}</p>
                    <Checkbox checked={useJson} onChange={(e) => setUseJson(e.target.checked)}>{t("使用 JSON 编辑结果", "Use JSON edits")}</Checkbox>
                    <Input.TextArea className="mono" value={json} onChange={(e) => setJson(e.target.value)} autoSize={{ minRows: 8, maxRows: 22 }} disabled={!useJson} />
                  </>
                ),
              }]} />
            </>
          ) : (
            <>
              <div className="editor-grid">
                {LEGACY.map(([key, zh, en]) => (
                  <Form.Item key={key} label={t(zh, en)}>
                    <Select mode="tags" value={legacy[key] ?? []} onChange={(v) => setLegacy((l) => ({ ...l, [key]: v }))} tokenSeparators={[",", "，"]} open={false} />
                  </Form.Item>
                ))}
              </div>
              <Form.Item label={t("高级参数（JSON）", "Advanced parameters (JSON)")} extra={t("仅限数值，例如 {\"ego_speed_kph\": 60}", "Numbers only, for example {\"ego_speed_kph\": 60}")}>
                <Input className="mono" value={parameters} onChange={(e) => setParameters(e.target.value)} />
              </Form.Item>
            </>
          )}
        </Form>
      )}
    </Drawer>
  );
}
