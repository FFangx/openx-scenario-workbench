import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Checkbox, Dropdown, Empty, Input, Radio, Select, Spin, Table, Tag, Tooltip, type TableColumnsType } from "antd";
import { CheckCircleFilled, CheckOutlined, DownloadOutlined, DownOutlined, EllipsisOutlined, RobotOutlined, SearchOutlined } from "@ant-design/icons";
import { api, urls, type AssetDetail, type BindingDraft, type BindingStatus, type BindingSuggestion, type ConfirmedBinding, type GroupBindings,
  type Job, type PdfDocument, type Scene, type SceneBinding, type SceneRef, type SuggestedCandidate } from "../api";
import { dateTime, useT } from "../i18n";
import { useJob } from "../jobs";
import { BINDING_STATUS as STATUS, ConfirmedMark, StatusTag } from "./BindingViews";
import { ExtractionDialog } from "./ExtractionDialog";
import { ImportPdfDialog } from "./ImportPdfDialog";
import { JobProgress } from "./JobProgress";
import { PreviewPlayer } from "./PreviewPlayer";
import { Evidence } from "./RequirementsPanel";
import { StepBar } from "./TopBar";

// The model's verdicts (kept in its own words in the suggestions) on the four reuse levels a person also uses.
const VERDICT: Record<string, { zh: string; en: string; cls: string; order: number }> = {
  "同一测试": { zh: "直接复用", en: "Direct reuse", cls: "direct", order: 0 },
  "同一测试但要改": { zh: "修改复用", en: "Modify and reuse", cls: "modify", order: 1 },
  "拿不准": { zh: "无法判断", en: "Undetermined", cls: "review", order: 2 },
  "不是": { zh: "不适用", en: "Not applicable", cls: "not", order: 3 },
};
const STALE: Record<string, [string, string]> = {
  scene: ["条款的需求事实已修改", "the clause's facts were edited"],
  asset: ["素材有新版本", "an asset has a newer version"],
};

const VerdictTag = ({ verdict }: { verdict: string }) => {
  const { lang } = useT();
  return <Tag className={`mtag ${VERDICT[verdict]?.cls ?? "not"}`}>{(VERDICT[verdict]?.[lang] ?? verdict) || "—"}</Tag>;
};

/** A suggestion is usable while what the model judged is still there and it gave a reply that fits. */
const usable = (s: BindingSuggestion | null | undefined): s is BindingSuggestion => !!s && !s.failure && !s.outdated.length;

/** What the assessments that disagree recommended instead, by name. */
function othersText(s: BindingSuggestion, t: (zh: string, en: string) => string) {
  return s.other_preferred.map((id) => (id ? s.candidates.find((c) => c.id === id)?.title ?? id : t("无可复用素材", "no reusable asset"))).join(t("、", ", "));
}

/** Consistent: every independent assessment recommended the same asset. Inconsistent: they differ, a person reviews it. */
function Consistency({ s }: { s: BindingSuggestion }) {
  const { t } = useT();
  if (s.stable === null) return null;
  if (s.stable) {
    return (
      <Tooltip title={t(`独立评估 ${s.readings} 次，推荐结论一致。`, `${s.readings} independent assessments recommended the same asset.`)}>
        <Tag className="mtag steady">{t(`一致 ${s.agree}/${s.readings}`, `Consistent ${s.agree}/${s.readings}`)}</Tag>
      </Tooltip>
    );
  }
  return (
    <Tooltip title={t(`独立评估 ${s.readings} 次，${s.agree} 次推荐当前素材；其余推荐：${othersText(s, t)}。请人工复核。`,
      `${s.agree} of ${s.readings} independent assessments recommend this asset; the others: ${othersText(s, t)}. Please review.`)}>
      <Tag className="mtag unsettled">{t(`不一致 ${s.agree}/${s.readings}`, `Inconsistent ${s.agree}/${s.readings}`)}</Tag>
    </Tooltip>
  );
}

/** The suggestion as a binding: its group, the preferred asset and that asset's changes. */
function proposal(s: BindingSuggestion): BindingDraft {
  const chosen = s.candidates.filter((c) => s.binding.includes(c.id));
  if (!chosen.length) return { status: "none", assets: [], preferred: null, changes: "" };
  const preferred = chosen.find((c) => c.id === s.preferred) ?? chosen[0];
  return { status: preferred.verdict === "同一测试但要改" ? "modify" : "same", preferred: preferred.asset_id,
    assets: chosen.map((c) => ({ asset_id: c.asset_id, version_id: c.version_id })), changes: preferred.changes };
}

function fromBinding(b: ConfirmedBinding): BindingDraft {
  return { status: b.status, changes: b.changes, preferred: b.assets.find((a) => a.preferred)?.asset_id ?? null,
    assets: b.assets.map((a) => ({ asset_id: a.asset_id, version_id: a.version_id })) };
}

const sameDraft = (a: BindingDraft, b: BindingDraft) => a.status === b.status && a.preferred === b.preferred
  && a.assets.length === b.assets.length && a.assets.every((x) => b.assets.some((y) => y.asset_id === x.asset_id && y.version_id === x.version_id));

const staleText = (reasons: string[], t: (zh: string, en: string) => string) =>
  reasons.map((r) => t(...(STALE[r] ?? [r, r]))).join(t("；", "; "));

type Row = SceneBinding & { key: string };

const rowKey = (s: SceneRef) => `${s.document_id}/${s.scene_id}`;
const ref = (s: SceneRef): SceneRef => ({ document_id: s.document_id, scene_id: s.scene_id });
/** Offer "Adopt" while nothing is confirmed, or a confirmed conclusion needs reconfirming and the suggestion differs from it. */
const offers = (r: Row) => usable(r.suggestion) && (!r.binding || (r.binding.stale.length > 0 && !sameDraft(fromBinding(r.binding), proposal(r.suggestion))));

interface Props {
  projectId: string;
  /** Every PDF of the project. */
  docs: PdfDocument[];
  /** The PDFs shown together, in the project's order. */
  picked: string[];
  onPicked: (ids: string[]) => void;
  /** The row to select first, e.g. the scene just bound by hand. */
  focus: string | null;
  esmini: boolean;
  onSettings: () => void;
  onDocsChanged: (select?: string) => void;
  /** Find an asset for the scene by hand, in the rule-based search. */
  onManual: (documentId: string, sceneId: string) => void;
}

/** The main screen of a PDF: every clause with the assets the model suggests for it, confirmed by a person, exported as one table. */
export function BindingWorkspace({ projectId, docs, picked, onPicked, focus, esmini, onSettings, onDocsChanged, onManual }: Props) {
  const { t, lang } = useT();
  const shown = docs.filter((d) => picked.includes(d.document_id));
  const ids = (shown.length ? shown : docs.slice(0, 1)).map((d) => d.document_id);
  const idsKey = ids.join("|");
  const [view, setView] = useState<GroupBindings | null>(null);
  const [scenes, setScenes] = useState<Map<string, Scene>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(focus);
  const [initial, setInitial] = useState<Job | null>(null);
  const [dialog, setDialog] = useState<"import" | "extraction" | null>(null);
  const [find, setFind] = useState("");
  const reload = () => idsKey && api.bindings(projectId, idsKey.split("|")).then(setView).catch((e: Error) => setError(e.message));
  const { job, cancel } = useJob(initial, () => reload());

  useEffect(() => {
    setView(null);
    setError(null);
    if (!idsKey) return;
    const list = idsKey.split("|");
    api.bindings(projectId, list).then((v) => {
      setView(v);
      setInitial(v.job ?? null);  // a run still going, or how the last one ended
    }).catch((e: Error) => setError(e.message));
    Promise.all(list.map((d) => api.scenes(projectId, d)))
      .then((all) => setScenes(new Map(all.flat().map((s) => [rowKey(s), s]))))
      .catch((e: Error) => setError(e.message));
  }, [projectId, idsKey]);

  const rows: Row[] = useMemo(() => (view?.scenes ?? []).map((s) => ({ ...s, key: rowKey(s) })), [view]);
  const q = find.trim().toLocaleLowerCase();
  const listed = q ? rows.filter((r) => `${r.section_id} ${r.title}`.toLocaleLowerCase().includes(q)) : rows;
  useEffect(() => {
    if (rows.length && !rows.some((r) => r.key === selected)) setSelected(rows.some((r) => r.key === focus) ? focus : rows[0].key);
  }, [rows, selected, focus]);
  const row = rows.find((r) => r.key === selected) ?? null;

  const run = async <T,>(key: string, work: () => Promise<T>, done: (value: T) => void) => {
    setBusy(key);
    setError(null);
    try {
      done(await work());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  /** Every row of the PDFs shown. */
  const act = (key: string, work: () => Promise<GroupBindings>) => run(key, work, setView);
  /** One row: the reply replaces that row only. */
  const actRow = (key: string, work: () => Promise<SceneBinding>) => run(key, work, (r) =>
    setView((v) => v && { ...v, scenes: v.scenes.map((s) => (rowKey(s) === rowKey(r) ? r : s)) }));
  const suggest = () => {
    setError(null);
    return api.suggestBindings(projectId, ids).then(setInitial).catch((e: Error) => setError(e.message));
  };
  const running = job?.status === "running";
  const acceptable = rows.filter((r) => !r.binding && usable(r.suggestion) && r.suggestion.stable !== false
    && proposal(r.suggestion).status === "same").length;
  const look = rows.filter((r) => !r.binding && usable(r.suggestion) && r.suggestion.stable === false).length;
  const confirmed = rows.filter((r) => r.binding).length;
  const stale = rows.filter((r) => r.binding?.stale.length).length;
  const suggested = rows.filter((r) => r.suggestion).length;
  const failed = rows.filter((r) => r.suggestion?.failure).length;
  const step = !rows.length ? 0 : !suggested && !confirmed ? 1 : confirmed < rows.length ? 2 : 3;
  const single = shown.length === 1 ? shown[0] : null;

  const columns: TableColumnsType<Row> = [
    ...(ids.length > 1 ? [{ title: t("文档", "PDF"), key: "doc", width: "15%", ellipsis: true,
      render: (_: unknown, r: Row) => <span title={r.filename}>{r.filename}</span> }] : []),
    {
      title: t("需求条款", "Clause"), key: "scene", width: "40%", ellipsis: true,
      render: (_, r) => <span title={r.title}>{r.section_id && <span className="muted">{r.section_id} </span>}{r.title}</span>,
    },
    {
      title: t("复用素材（首选）", "Reused asset (preferred)"), key: "asset", ellipsis: true,
      render: (_, r) => {
        if (r.binding) {
          const preferred = r.binding.assets.find((a) => a.preferred);
          return (
            <div className="batch-cand">
              <StatusTag status={r.binding.status} />
              <ConfirmedMark source={r.binding.source} at={r.binding.confirmed_at} />
              {r.binding.stale.length > 0 && <Tooltip title={staleText(r.binding.stale, t)}><Tag className="mtag review">{t("待重新确认", "Reconfirm")}</Tag></Tooltip>}
              <span title={preferred?.title}>{preferred ? preferred.title : "—"}{r.binding.assets.length > 1 && <span className="muted"> +{r.binding.assets.length - 1}</span>}</span>
            </div>
          );
        }
        const s = r.suggestion;
        if (!s) return <span className="muted">{t("尚未生成建议", "No suggestion yet")}</span>;
        if (s.failure) return <Tooltip title={s.failure}><Tag className="mtag review">{t("模型未返回有效结果", "No valid model result")}</Tag></Tooltip>;
        const chosen = s.candidates.filter((c) => s.binding.includes(c.id));
        const preferred = chosen.find((c) => c.id === s.preferred) ?? chosen[0];
        return (
          <div className="batch-cand">
            {s.outdated.length > 0 && <Tooltip title={staleText(s.outdated, t)}><Tag className="mtag review">{t("建议已失效", "Suggestion outdated")}</Tag></Tooltip>}
            <VerdictTag verdict={preferred?.verdict ?? (s.candidates.some((c) => c.verdict === "拿不准") ? "拿不准" : "不是")} />
            <Consistency s={s} />
            <span className="muted" title={preferred?.title}>{preferred?.title}{chosen.length > 1 ? ` +${chosen.length - 1}` : ""}</span>
          </div>
        );
      },
    },
    {
      title: "", key: "act", width: 92,
      render: (_, r) => (
        <span className="bind-actions" onClick={(e) => e.stopPropagation()}>
          {offers(r) && (
            <Button size="small" loading={busy === `accept:${r.key}`}
              onClick={() => act(`accept:${r.key}`, () => api.acceptBindings(projectId, ids, [ref(r)]))}>
              {t("采纳", "Adopt")}
            </Button>
          )}
        </span>
      ),
    },
  ];

  const docMenu = {
    items: [
      { key: "import", label: t("导入 PDF…", "Import PDFs…") },
      { type: "divider" as const },
      { key: "open", label: t("打开 PDF", "Open PDF"), disabled: !single },
      { key: "extraction", label: t("解析与校验记录…", "Extraction record…"), disabled: !single },
    ],
    onClick: ({ key }: { key: string }) =>
      key === "open" ? single && window.open(urls.pdf(projectId, single.document_id), "_blank") : setDialog(key as "import" | "extraction"),
  };

  return (
    <>
      <StepBar active={step} projectId={projectId} docs={docs} current={ids} onDoc={(id) => onPicked([id])} />
      <main className="ox-main bind-main">
        <section className="panel bind-list">
          <div className="ph">
            <span className="n">1</span>{t("条款复用评估", "Clause reuse assessment")}
            {view && (
              <span className="meta bind-counts">
                {t(`已确认 ${confirmed} / ${rows.length}`, `${confirmed} / ${rows.length} confirmed`)}
                {look > 0 && t(` · 结论不一致 ${look}`, ` · ${look} inconsistent`)}
                {stale > 0 && t(` · 待重新确认 ${stale}`, ` · ${stale} to reconfirm`)}
              </span>
            )}
          </div>
          <div className="box pdfcard bind-docs">
            <span className="pdf" aria-hidden>PDF</span>
            <div className="pdf-meta">
              {docs.length > 1 ? (
                <Select mode="multiple" size="small" value={ids} maxTagCount="responsive" aria-label={t("一起看的 PDF", "PDFs shown together")}
                  onChange={(v: string[]) => v.length && onPicked(docs.filter((d) => v.includes(d.document_id)).map((d) => d.document_id))}
                  options={docs.map((d) => ({ value: d.document_id, label: d.filename }))} />
              ) : (
                <div className="t" title={single?.filename}>{single?.filename}</div>
              )}
              <div className="m">
                {t(`${rows.length} 个条款`, `${rows.length} clauses`)}
                {single && <><i>|</i>{t("导入于", "Imported")} {single.imported_at.slice(0, 10)}<i>|</i>{t(`${single.page_count} 页`, `${single.page_count} pages`)}</>}
              </div>
            </div>
            <Dropdown trigger={["click"]} menu={docMenu}>
              <Button className="more" type="text" icon={<EllipsisOutlined />} aria-label={t("文档操作", "Document actions")} />
            </Dropdown>
          </div>
          <p className="muted bind-lead">
            {t("模型对每个条款独立评估 3 次并推荐复用素材，经人工确认后生效；条款原文、需求事实和候选素材信息会发送至已配置的模型。",
              "The model assesses each clause 3 times; you confirm. Clause text, facts and candidate details go to your configured model.")}
          </p>
          {error && <Alert type="error" showIcon closable title={error} onClose={() => setError(null)} />}
          {job && (running || job.status !== "completed") && <JobProgress job={job} onCancel={cancel} unit={["个场景", "scenes"]} />}
          {failed > 0 && !running && (
            <Alert type="warning" showIcon title={t(`${failed} 个条款未得到有效的模型结果，可重新生成建议。`, `${failed} clauses got no valid model result; regenerate the suggestions.`)} />
          )}
          <div className="bind-toolbar">
            <Tooltip title={suggested ? t("条款和候选未变化时沿用上次结果，不重复调用模型。", "Unchanged clauses and candidates keep the last result without a new call.") : undefined}>
              <Button type={suggested ? "default" : "primary"} icon={<RobotOutlined />} onClick={suggest} disabled={running || !view}>
                {suggested ? t("重新生成建议", "Regenerate suggestions") : t("生成复用建议", "Generate suggestions")}
              </Button>
            </Tooltip>
            <Button icon={<CheckOutlined />} type={acceptable ? "primary" : "default"} disabled={!acceptable || running} loading={busy === "accept-all"}
              onClick={() => act("accept-all", () => api.acceptBindings(projectId, ids))}>
              {t(`采纳全部一致的“直接复用”建议（${acceptable}）`, `Adopt consistent direct reuse (${acceptable})`)}
            </Button>
            <Dropdown trigger={["click"]} disabled={!rows.length} menu={{
              items: [
                { key: "csv", label: <a href={urls.bindingsExport(projectId, ids, "csv", lang)} download>{t("表格（CSV，可用 Excel 打开）", "Spreadsheet (CSV, opens in Excel)")}</a> },
                { key: "html", label: <a href={urls.bindingsExport(projectId, ids, "html", lang)} download>{t("网页（HTML）", "Web page (HTML)")}</a> },
              ],
            }}>
              <Button className="bind-export" icon={<DownloadOutlined />} disabled={!rows.length}>{t("导出复用评估表", "Export assessment")} <DownOutlined /></Button>
            </Dropdown>
            <Input size="small" allowClear prefix={<SearchOutlined />} value={find} onChange={(e) => setFind(e.target.value)} className="bind-find"
              placeholder={t("条款号或标题", "Clause or title")} aria-label={t("查找条款", "Find a clause")} />
          </div>
          <div className="bind-legend">
            <span><CheckCircleFilled className="ic-ok" />{t("已人工确认", "Confirmed by a person")}</span>
            <span><Tag className="mtag steady">{t("一致 3/3", "Consistent 3/3")}</Tag>{t("模型 3 次评估推荐相同", "the model's 3 assessments agree")}</span>
            <span><Tag className="mtag unsettled">{t("不一致 2/3", "Inconsistent 2/3")}</Tag>{t("推荐不同，需人工复核", "they differ; please review")}</span>
          </div>
          {!view ? <div className="center-pad"><Spin /></div> : (
            <Table<Row>
              className="ov-table batch-table bind-table"
              size="small"
              columns={columns}
              dataSource={listed}
              pagination={false}
              tableLayout="fixed"
              scroll={{ y: "calc(100vh - 360px)" }}
              rowClassName={(r) => (r.key === selected ? "row-active" : "")}
              onRow={(r) => ({ onClick: () => setSelected(r.key) })}
              locale={{ emptyText: q ? t("没有符合的条款", "No matching clauses") : t("这份 PDF 没有识别到场景", "No scenes were extracted from this PDF") }}
            />
          )}
        </section>
        <section className="panel bind-detail">
          {row ? (
            <BindingDetail key={`${row.key}|${row.binding?.confirmed_at}|${row.suggestion?.created_at}`} projectId={projectId} row={row}
              scene={scenes.get(row.key) ?? null} busy={busy} esmini={esmini} onSettings={onSettings}
              onSave={(draft) => actRow(`save:${row.key}`, () => api.confirmBinding(projectId, ref(row), draft))}
              onRemove={() => actRow(`remove:${row.key}`, () => api.unbind(projectId, ref(row)))}
              onManual={() => onManual(row.document_id, row.scene_id)} />
          ) : (
            <div className="decide-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("请在左侧选择条款", "Select a clause on the left")} /></div>
          )}
        </section>
      </main>
      <ImportPdfDialog open={dialog === "import"} projectId={projectId} onClose={() => setDialog(null)}
        onImported={(created) => { onDocsChanged(created[created.length - 1]); if (created.length) onPicked([created[created.length - 1]]); }} />
      {single && (
        <ExtractionDialog open={dialog === "extraction"} projectId={projectId} doc={single} onClose={() => setDialog(null)}
          onReextracted={(created) => { onDocsChanged(created[0]); if (created.length) onPicked([created[0]]); }} />
      )}
    </>
  );
}

type Choice = Pick<SuggestedCandidate, "asset_id" | "version_id" | "version_number" | "title" | "verdict" | "reason" | "changes" | "latest"> & { rank: number | null };

interface DetailProps {
  projectId: string;
  row: Row;
  scene: Scene | null;
  busy: string | null;
  esmini: boolean;
  onSettings: () => void;
  onSave: (d: BindingDraft) => void;
  onRemove: () => void;
  onManual: () => void;
}

/** One clause: its source text, the preferred asset playing, and every candidate with the model's words; the person confirms. */
function BindingDetail({ projectId, row, scene, busy, esmini, onSettings, onSave, onRemove, onManual }: DetailProps) {
  const { t } = useT();
  const s = row.suggestion;
  const start = row.binding ? fromBinding(row.binding) : s && !s.failure ? proposal(s) : { status: "same" as BindingStatus, assets: [], preferred: null, changes: "" };
  const [draft, setDraft] = useState<BindingDraft>(start);
  const [all, setAll] = useState(false);
  const inGroup = (c: Choice) => draft.assets.some((a) => a.asset_id === c.asset_id && a.version_id === c.version_id);

  const choices: Choice[] = (s?.candidates ?? []).map((c) => ({ ...c }));
  for (const a of row.binding?.assets ?? []) {
    if (!choices.some((c) => c.asset_id === a.asset_id && c.version_id === a.version_id)) choices.push({ ...a, rank: null });
  }
  const order = (c: Choice) => (inGroup(c) ? -1 : VERDICT[c.verdict]?.order ?? 4);
  choices.sort((a, b) => order(a) - order(b) || (a.rank ?? 999) - (b.rank ?? 999));
  const visible = all ? choices : choices.filter((c) => inGroup(c) || (c.verdict && c.verdict !== "不是"));
  const hidden = choices.length - visible.length;
  const preferred = choices.find((c) => inGroup(c) && c.asset_id === draft.preferred) ?? null;

  const toggle = (c: Choice, on: boolean) => setDraft((d) => {
    const assets = on ? [...d.assets, { asset_id: c.asset_id, version_id: c.version_id }]
      : d.assets.filter((a) => !(a.asset_id === c.asset_id && a.version_id === c.version_id));
    const pick = assets.some((a) => a.asset_id === d.preferred) ? d.preferred : assets[0]?.asset_id ?? null;
    return { ...d, assets, preferred: pick, status: d.status === "none" && assets.length ? (c.verdict === "同一测试但要改" ? "modify" : "same") : d.status };
  });
  const none = draft.status === "none";
  const valid = none || draft.assets.length > 0;

  return (
    <div className="bind-pane">
      <div className="bind-head">
        <div className="bind-title" title={row.title}>{row.section_id && <span className="muted">{row.section_id} </span>}{row.title}</div>
        <Tooltip title={t("在资产库中自行检索并查看规则逐项比对，可将选定素材采用为本条款的复用素材。", "Search the library yourself with the rule-by-rule comparison; a candidate you pick can be adopted for this clause.")}>
          <Button size="small" icon={<SearchOutlined />} onClick={onManual}>{t("手动检索", "Search manually")}</Button>
        </Tooltip>
      </div>
      {scene ? <Evidence projectId={projectId} scene={scene} /> : <div className="center-pad"><Spin /></div>}
      {preferred && <AssetPreview version={preferred} esmini={esmini} onSettings={onSettings} />}

      <div className="bind-editor">
        <div className="sec-title">{t("候选素材", "Candidate assets")}</div>
        {s?.stable === false && (
          <div className="bind-note bind-unsettled">
            {t(`评估结论不一致：${s.agree}/${s.readings} 次推荐当前素材，其余推荐：${othersText(s, t)}。请人工复核。`,
              `Inconsistent assessments: ${s.agree} of ${s.readings} recommend this asset; the others: ${othersText(s, t)}. Please review.`)}
          </div>
        )}
        {s?.note && <div className="muted bind-note">{t("模型备注：", "Model note: ")}{s.note}</div>}
        {!choices.length && <div className="muted">{t("暂无候选：请先生成复用建议，或手动检索。", "No candidates yet: generate suggestions or search manually.")}</div>}
        <div className="bind-cands">
          {visible.map((c) => (
            <div key={`${c.asset_id}:${c.version_id}`} className={`bind-cand${inGroup(c) ? " on" : ""}`}>
              <Checkbox checked={inGroup(c)} disabled={none} onChange={(e) => toggle(c, e.target.checked)} aria-label={t("采用", "Adopt")} />
              <Tooltip title={t("首选", "Preferred")}>
                <Radio checked={draft.preferred === c.asset_id && inGroup(c)} disabled={none || !inGroup(c)}
                  onChange={() => setDraft((d) => ({ ...d, preferred: c.asset_id }))} />
              </Tooltip>
              <VerdictTag verdict={c.verdict} />
              <span className="name" title={c.title}>{c.title}</span>
              {!c.latest && <Tag className="mtag review">{t("有新版本", "Newer version")}</Tag>}
              <span className="muted rank">{c.rank ? `#${c.rank}` : ""} v{c.version_number}</span>
              {(c.reason || c.changes) && (
                <div className="why">{c.reason}{c.changes && <b>{t(" 修改内容：", " Changes: ")}{c.changes}</b>}</div>
              )}
            </div>
          ))}
        </div>
        {hidden > 0 && <Button size="small" type="link" onClick={() => setAll(true)}>{t(`显示其余 ${hidden} 个候选（模型判定不适用）`, `Show ${hidden} more candidates (judged not applicable)`)}</Button>}
        <div className="bind-form">
          <Radio.Group value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value, ...(e.target.value === "none" ? { assets: [], preferred: null } : {}) }))}
            options={(["same", "modify", "none"] as BindingStatus[]).map((value) => ({ value, label: t(STATUS[value].zh, STATUS[value].en) }))} />
          {draft.status === "modify" && (
            <Input.TextArea value={draft.changes} maxLength={2000} autoSize={{ minRows: 1, maxRows: 4 }} placeholder={t("修改内容", "Changes needed")}
              onChange={(e) => setDraft((d) => ({ ...d, changes: e.target.value }))} />
          )}
          <div className="settings-actions">
            <Button type="primary" disabled={!valid} loading={busy === `save:${row.key}`} onClick={() => onSave(draft)}>
              {row.binding ? t("更新结论", "Update") : t("确认结论", "Confirm")}
            </Button>
            {row.binding && (
              <Button loading={busy === `remove:${row.key}`} onClick={onRemove}>{t("撤销结论", "Withdraw")}</Button>
            )}
            {row.binding && (
              <span className="muted bind-confirmed-at"><ConfirmedMark source={row.binding.source} at={row.binding.confirmed_at} />
                {t(`已人工确认 · ${dateTime(row.binding.confirmed_at)}`, `Confirmed by a person · ${dateTime(row.binding.confirmed_at)}`)}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** The preferred asset: its saved esmini frame (or play it) next to its road drawn from above. */
function AssetPreview({ version, esmini, onSettings }: { version: Choice; esmini: boolean; onSettings: () => void }) {
  const { t } = useT();
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  useEffect(() => {
    setDetail(null);
    api.assetDetail(version).then(setDetail).catch(() => undefined);
  }, [version.asset_id, version.version_id]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="box bind-preview">
      <div className="card-h">{t("首选复用素材", "Preferred asset")}<span className="r" title={version.title}>{version.title}</span></div>
      {!detail ? <div className="center-pad"><Spin /></div> : (
        <div className="bind-preview-body">
          <PreviewPlayer cand={{ asset_id: version.asset_id, version_id: version.version_id, has_frame: detail.has_frame, compatibility: detail.version.compatibility }}
            esmini={esmini} onSettings={onSettings} />
          {detail.summary && !detail.summary.road_file_missing ? (
            <img className="road-drawing" src={urls.roadDrawing(version)} alt={t("道路俯视图与参与者起点", "The road from above with where the participants start")} loading="lazy" />
          ) : (
            <div className="img-empty"><b>{t("道路文件缺失", "Road file missing")}</b></div>
          )}
        </div>
      )}
    </div>
  );
}
