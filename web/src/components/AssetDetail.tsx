import { useEffect, useState } from "react";
import { Alert, App, Button, Collapse, Descriptions, Form, Input, Popconfirm, Select, Spin, Table, Tabs, Tag, Tooltip } from "antd";
import { CloseOutlined, CodeOutlined, DeleteOutlined, DownloadOutlined, ExportOutlined, RobotOutlined, TagsOutlined } from "@ant-design/icons";
import { api, urls, type AssetDetail as Detail, type ClassificationLabels, type StandardExportResult, type VersionRef } from "../api";
import { dateTime, useT } from "../i18n";
import { PREVIEW_FAILED, roadFeatureLabel, valueLabel } from "../vocab";
import { SourceFilesDialog, StandardChecks } from "./AssessmentDialogs";
import { AssetClauses } from "./BindingViews";
import { PreviewPlayer } from "./PreviewPlayer";

interface Props {
  version: VersionRef;
  busy: boolean;
  esmini: boolean;
  onSettings: () => void;
  onSelect: (v: VersionRef) => void;
  onClose: () => void;
  onChanged: () => void;
  onDeleted: () => void;
  onModelClassify: (v: VersionRef) => void;
  /** Opens a bound requirement scene in the workbench; without it the bound clauses are only listed. */
  onOpenScene?: (projectId: string, documentId: string, sceneId: string) => void;
}

/** One immutable asset version: preview, labels, provenance and its sibling versions. */
export function AssetDetail({ version, busy, esmini, onSettings, onSelect, onClose, onChanged, onDeleted, onModelClassify, onOpenScene }: Props) {
  const { t, lang } = useT();
  const { message } = App.useApp();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState(false);
  const [clauses, setClauses] = useState<number | null>(null);
  const key = `${version.asset_id}/${version.version_id}`;

  const load = () => api.assetDetail(version).then(setDetail).catch((e: Error) => setError(e.message));
  useEffect(() => {
    setDetail(null);
    setError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const remove = async () => {
    try {
      await api.deleteVersion(version);
      message.success(t("版本已删除", "Version deleted"));
      onDeleted();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  if (error) return <Alert type="error" showIcon title={error} />;
  if (!detail) return <div className="center-pad"><Spin /></div>;
  const v = detail.version;
  const ref = { asset_id: v.asset_id, version_id: v.version_id, version_number: v.version_number, xosc: v.xosc_name, xodr: v.xodr_name };

  return (
    <div className="asset-detail">
      <div className="asset-detail-head">
        <div className="sel-name">
          <div className="name" title={v.title || v.xosc_name}>{v.title || v.xosc_name}</div>
          <div className="muted">
            {t(`版本 ${v.version_number}`, `Version ${v.version_number}`)} · <span className={`dot-status ${v.compatibility === "playable" ? "ok" : PREVIEW_FAILED.has(v.compatibility) ? "bad" : ""}`}>{valueLabel(v.compatibility, lang)}</span>
          </div>
        </div>
        <Popconfirm title={t("删除此版本？", "Delete this version?")} description={t("删除所选版本将移除它的本地记录与文件。", "Deleting removes this version's local record and files.")}
          onConfirm={remove} okText={t("删除", "Delete")} okButtonProps={{ danger: true }} cancelText={t("取消", "Cancel")}>
          <Tooltip title={detail.references.length ? t("被报告或需求绑定引用的版本不能删除", "Versions a report or a requirement binding refers to cannot be deleted") : busy ? t("导入结束后可删除", "Available after the import finishes") : t("删除此版本", "Delete this version")}>
            <Button type="text" danger icon={<DeleteOutlined />} disabled={busy || detail.references.length > 0} aria-label={t("删除此版本", "Delete this version")} />
          </Tooltip>
        </Popconfirm>
        <Button type="text" icon={<CloseOutlined />} onClick={onClose} aria-label={t("关闭", "Close")} />
      </div>
      {detail.references.length > 0 && (
        <Alert type="info" showIcon title={t(`此版本已被 ${detail.references.length} 条报告或需求绑定引用，无法删除。`, `This version is referenced by ${detail.references.length} reports or requirement bindings and cannot be deleted.`)} />
      )}
      <Tabs
        size="small"
        items={[
          {
            key: "overview",
            label: t("概览与预览", "Overview & preview"),
            children: detail.error ? <Alert type="error" showIcon title={t("无法读取此版本：", "Cannot read this version: ") + detail.error} /> : (
              <div className="settings-form">
                {detail.summary && (
                  <p className="muted">
                    {detail.summary.road_file_missing ? (() => {
                      const road = detail.summary.inferred_road_features.map((f) => roadFeatureLabel(f, lang)).join(", ") || t("未知", "unknown");
                      return t(`${detail.summary.entities} 个参与者 · 道路文件缺失（地图「${detail.summary.road_name ?? ""}」，按地图名推断为${road}）`,
                        `${detail.summary.entities} entities · road file missing (map "${detail.summary.road_name ?? ""}", inferred from its name as ${road})`);
                    })() : t(`${detail.summary.entities} 个参与者 · 道路总长 ${detail.summary.road_length_m.toFixed(0)} m · ${detail.summary.lane_count} 个车道记录 · ${detail.summary.junction_count} 个交叉口`,
                      `${detail.summary.entities} entities · ${detail.summary.road_length_m.toFixed(0)} m road · ${detail.summary.lane_count} lane entries · ${detail.summary.junction_count} junctions`)}
                    {detail.summary.description && <><br />{detail.summary.description}</>}
                  </p>
                )}
                <div className="asset-player"><PreviewPlayer cand={{ ...version, compatibility: v.compatibility, has_frame: detail.has_frame }} esmini={esmini} onSettings={onSettings} /></div>
                {detail.summary && !detail.summary.road_file_missing && (
                  <img className="road-drawing" src={urls.roadDrawing(version)} alt={t("道路俯视图与参与者起点", "The road from above with where the participants start")} loading="lazy" />
                )}
                {v.compatibility_detail && <pre className="json-view">{v.compatibility_detail}</pre>}
                <Collapse size="small" items={[{ key: "checks", label: t("文件标准检查", "File standard checks"), children: <StandardChecks checks={detail.validation ?? {}} /> }]} />
              </div>
            ),
          },
          {
            key: "classification",
            label: t("分类", "Classification"),
            children: <ClassificationTab key={detail.classification?.saved_at ?? "none"} detail={detail} busy={busy}
              onChanged={() => { load(); onChanged(); }} onModel={() => onModelClassify(version)} />,
          },
          {
            key: "source",
            label: t("来源", "Source"),
            children: (
              <div className="settings-form">
                <Descriptions size="small" column={1} bordered items={[
                  { key: "s", label: t("来源文件", "Source"), children: v.source_name },
                  { key: "i", label: t("导入时间", "Imported"), children: dateTime(v.created_at) },
                  { key: "a", label: "Asset ID", children: <span className="mono">{v.asset_id}</span> },
                  { key: "v", label: "Version ID", children: <span className="mono">{v.version_id}</span> },
                ]} />
                <Table size="small" pagination={false} rowKey="role" dataSource={v.files} columns={[
                  { title: t("角色", "Role"), dataIndex: "role", width: 90 },
                  { title: t("原始文件", "Original file"), dataIndex: "original_name", ellipsis: true },
                  { title: "SHA-256", dataIndex: "sha256", ellipsis: true, render: (s: string) => <span className="mono">{s}</span> },
                ]} />
                <div className="settings-actions">
                  <Button icon={<CodeOutlined />} onClick={() => setFiles(true)}>{t("查看源文件", "Inspect source files")}</Button>
                </div>
                {detail.standard_export && <StandardExport version={version} busy={busy} />}
                <Collapse size="small" ghost items={[{
                  key: "raw",
                  label: t("版本原始记录", "Raw version record"),
                  children: <pre className="json-view">{JSON.stringify({ version: v, classification: detail.classification }, null, 2)}</pre>,
                }]} />
              </div>
            ),
          },
          {
            key: "clauses",
            label: clauses === null ? t("对应需求", "Requirements") : t(`对应需求（${clauses}）`, `Requirements (${clauses})`),
            children: <AssetClauses assetId={v.asset_id} onOpen={onOpenScene} onCount={setClauses} />,
          },
          {
            key: "history",
            label: t(`版本历史（${detail.history.length}）`, `Versions (${detail.history.length})`),
            children: (
              <Table size="small" pagination={false} rowKey="version_id" dataSource={detail.history}
                rowClassName={(h) => (h.version_id === v.version_id ? "row-active" : "")}
                onRow={(h) => ({ onClick: () => onSelect({ asset_id: v.asset_id, version_id: h.version_id }) })}
                columns={[
                  { title: t("版本", "Version"), dataIndex: "version_number", width: 70, render: (n: number) => `v${n}` },
                  { title: t("导入时间", "Imported"), dataIndex: "created_at", render: dateTime },
                  { title: t("预览状态", "Preview"), dataIndex: "compatibility", render: (c: string) => valueLabel(c, lang) },
                  {
                    title: t("文件", "Files"), key: "f", width: 110, render: (_, h) => (
                      <span className="history-files" onClick={(e) => e.stopPropagation()}>
                        <a href={urls.file({ asset_id: v.asset_id, version_id: h.version_id }, "scenario")} download>XOSC</a>
                        <a href={urls.file({ asset_id: v.asset_id, version_id: h.version_id }, "road")} download>XODR</a>
                      </span>
                    ),
                  },
                ]} />
            ),
          },
        ]}
      />
      <SourceFilesDialog cand={ref} open={files} onClose={() => setFiles(false)} />
    </div>
  );
}

let schemaCache: ReturnType<typeof api.classificationSchema> | null = null;

function ClassificationTab({ detail, busy, onChanged, onModel }: { detail: Detail; busy: boolean; onChanged: () => void; onModel: () => void }) {
  const { t, lang } = useT();
  const { message } = App.useApp();
  const record = detail.classification;
  const v = { asset_id: detail.version.asset_id, version_id: detail.version.version_id };
  const [schema, setSchema] = useState<Record<string, string[]> | null>(null);
  const [labels, setLabels] = useState<ClassificationLabels | null>(record?.final ?? null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    (schemaCache ??= api.classificationSchema()).then(setSchema).catch(() => undefined);
  }, []);
  const options = (k: string) => (schema?.[k] ?? []).map((x) => ({ value: x, label: valueLabel(x, lang) }));

  const rules = () => api.classifyRules(v).then(onChanged).catch((e: Error) => message.error(e.message));
  const confirm = async () => {
    if (!labels) return;
    setSaving(true);
    try {
      await api.confirmClassification(v, labels);
      message.success(t("分类已确认，检索会使用这些标签。", "Classification confirmed; search uses these labels."));
      onChanged();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-form">
      {!record ? (
        <Alert type="info" showIcon title={t("此版本尚无分类记录。可先生成规则分类，或使用已配置的模型复核。", "This version has no classification. Generate rule labels or review with your configured model.")} />
      ) : (
        <div className="sec-head">
          <Tag className={`mtag ${record.status === "manual_confirmed" ? "direct" : record.status === "failed" ? "not" : "review"}`}>{valueLabel(record.status, lang)}</Tag>
          {record.needs_review && <span className="st warn">{t("分类待复核", "Classification needs review")}</span>}
          {record.model && <span className="muted">{record.model}</span>}
          <a className="small-link" href={urls.classification(v)}><DownloadOutlined /> {t("下载分类记录", "Download classification record")}</a>
        </div>
      )}
      {record?.error && <Alert type="error" showIcon title={record.error} />}
      {record?.llm && (
        <p className="muted">{t("模型置信度", "Model confidence")} {record.llm.confidence.toFixed(2)} · {record.llm.reason}</p>
      )}
      {labels && (
        <Form layout="vertical" className="fact-editor" disabled={busy}>
          <div className="editor-grid">
            <Form.Item label={t("功能", "Function")}><Select showSearch value={labels.function_type} options={options("function_type")} onChange={(x) => setLabels({ ...labels, function_type: x })} /></Form.Item>
            <Form.Item label={t("道路类型", "Road type")}><Select value={labels.label_road_type} options={options("label_road_type")} onChange={(x) => setLabels({ ...labels, label_road_type: x })} /></Form.Item>
          </div>
          <Form.Item label={t("目标参与者", "Targets")}><Select mode="multiple" value={labels.label_target_type} options={options("label_target_type")} onChange={(x) => setLabels({ ...labels, label_target_type: x })} /></Form.Item>
          <Form.Item label={t("动作标签", "Actions")}><Select mode="tags" open={false} tokenSeparators={[",", "，"]} value={labels.label_actions} onChange={(x) => setLabels({ ...labels, label_actions: x })} /></Form.Item>
          <Form.Item label={t("场景意图", "Intent")}><Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} value={labels.scenario_intent} onChange={(e) => setLabels({ ...labels, scenario_intent: e.target.value })} /></Form.Item>
        </Form>
      )}
      <div className="settings-actions">
        {labels && <Button type="primary" loading={saving} disabled={busy} onClick={confirm}>{t("保存并确认分类", "Save and confirm classification")}</Button>}
        {!record && <Button icon={<TagsOutlined />} disabled={busy} onClick={rules}>{t("生成规则分类", "Generate rule labels")}</Button>}
        <Button icon={<RobotOutlined />} disabled={busy} onClick={onModel}>{t("用模型分类", "Classify with model")}</Button>
      </div>
      <p className="muted settings-note">
        {busy ? t("导入结束后可修改分类。", "Classification can be edited after the import finishes.")
          : t("模型复核会将场景结构与描述发送给设置中的模型。", "Model review sends scenario structure and descriptions to the model in Settings.")}
      </p>
    </div>
  );
}

function StandardExport({ version, busy }: { version: VersionRef; busy: boolean }) {
  const { t } = useT();
  const [result, setResult] = useState<StandardExportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const labels: Record<string, [string, string]> = {
    valid: ["通过", "Passed"], invalid: ["未通过", "Failed"], unsupported: ["版本未支持", "Version unsupported"], unavailable: ["检查未完成", "Check unavailable"],
  };
  const prepare = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.standardExport(version));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="check-block">
      <div className="sec-title">{t("标准副本与兼容检查", "Standard copy & compatibility")}</div>
      <p className="muted settings-note">{t("保留原文件，单独转换并检查副本。标准检查通过不代表仿真行为已验证。", "Keeps originals and checks a separate converted copy. Passing standard checks does not verify simulation behavior.")}</p>
      {error && <Alert type="error" showIcon title={error} />}
      {result && (
        <>
          <Alert type={result.ready ? "success" : "warning"} showIcon title={result.ready
            ? t("副本已通过场景与道路标准检查，可下载。", "The copy passed scenario and road standard checks and is ready to download.")
            : t("副本仍需修复或复核，仅提供诊断包。原始资产可继续检索。", "The copy still needs repair or review. A diagnostic package is available; the original remains searchable.")} />
          {Object.entries(result.audit.validation).map(([role, record]) => (
            <div key={role}>
              <b>{role === "scenario" ? "OpenSCENARIO" : "OpenDRIVE"}</b> · {t(...(labels[record.status] ?? labels.unavailable))}
              {record.detail && <div className="muted">{record.detail}</div>}
              {(record.issues ?? []).map((issue, i) => <Alert key={i} type="warning" title={`${(issue as { path?: string }).path ?? ""}: ${issue.message}`} />)}
            </div>
          ))}
          {result.audit.external_dependencies.length > 0 && <Alert type="warning" showIcon title={t("还存在未打包的外部文件引用，请先补齐。", "External file references remain; provide those dependencies first.")} />}
          {result.audit.runtime_extension_points.length > 0 && <Alert type="warning" showIcon title={t("副本保留了自定义命令，目标仿真器需要支持这些命令；请单独验证运行行为。", "The copy retains custom commands. The target simulator must support them; verify execution separately.")} />}
          {(result.audit.parameter_issues.length > 0 || result.audit.unresolved.length > 0) && <Alert type="warning" showIcon title={t("参数或命令内容有歧义，需要复核。", "Parameters or command content need review.")} />}
          <Collapse size="small" ghost items={[{ key: "a", label: t("转换与校验记录", "Conversion and validation record"), children: <pre className="json-view">{JSON.stringify(result.audit, null, 2)}</pre> }]} />
        </>
      )}
      <div className="settings-actions">
        <Button icon={<ExportOutlined />} loading={loading} disabled={busy} onClick={prepare}>{t("准备标准导出", "Prepare standard export")}</Button>
        {result && (
          <Button icon={<DownloadOutlined />} href={urls.standardExport(version)}>
            {result.ready ? t("下载标准副本", "Download standard copy") : t("下载诊断包", "Download diagnostic package")}
          </Button>
        )}
      </div>
    </div>
  );
}
