import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Input, Radio, Table, Tag, Tooltip, type TableColumnsType } from "antd";
import { CheckOutlined, RobotOutlined } from "@ant-design/icons";
import { api, type BindingDraft, type BindingStatus, type BindingSuggestion, type ConfirmedBinding, type GroupBindings,
  type Job, type Lang, type PdfDocument, type SceneBinding, type SceneRef, type SuggestedCandidate } from "../api";
import { dateTime, useT } from "../i18n";
import { useJob } from "../jobs";
import { BINDING_STATUS as STATUS } from "./BindingViews";
import { JobProgress } from "./JobProgress";

const VERDICT: Record<string, { en: string; cls: string; order: number }> = {
  "同一测试": { en: "Same test", cls: "direct", order: 0 },
  "同一测试但要改": { en: "Same test after changes", cls: "modify", order: 1 },
  "拿不准": { en: "Unsure", cls: "review", order: 2 },
  "不是": { en: "Different test", cls: "not", order: 3 },
};
const STALE: Record<string, [string, string]> = {
  scene: ["需求场景的事实改过", "the scene's facts changed"],
  asset: ["素材有新版本", "an asset has a newer version"],
};

const verdictLabel = (verdict: string, lang: Lang) => (lang === "zh" ? verdict : VERDICT[verdict]?.en ?? verdict) || "—";
const VerdictTag = ({ verdict }: { verdict: string }) => {
  const { lang } = useT();
  return <Tag className={`mtag ${VERDICT[verdict]?.cls ?? "not"}`}>{verdictLabel(verdict, lang)}</Tag>;
};

/** A suggestion is usable while what the model judged is still there and it gave a reply that fits. */
const usable = (s: BindingSuggestion | null | undefined): s is BindingSuggestion => !!s && !s.failure && !s.outdated.length;

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

interface Props { projectId: string; docs: PdfDocument[]; open: boolean }

/** Requirement ↔ asset bindings of the PDFs shown together: the model suggests a group of assets per scene, a person confirms. */
export function BindingPanel({ projectId, docs, open }: Props) {
  const { t, lang } = useT();
  const [view, setView] = useState<GroupBindings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [initial, setInitial] = useState<Job | null>(null);
  const idsKey = docs.map((d) => d.document_id).join("|");
  const ids = idsKey ? idsKey.split("|") : [];
  const reload = () => ids.length && api.bindings(projectId, ids).then(setView).catch((e: Error) => setError(e.message));
  const { job, cancel } = useJob(initial, () => reload());

  useEffect(() => {
    if (!open) return;
    setView(null);
    setError(null);
    setExpanded([]);
    if (!idsKey) return;
    api.bindings(projectId, idsKey.split("|")).then((v) => {
      setView(v);
      setInitial(v.job ?? null);  // a run still going, or how the last one ended
    }).catch((e: Error) => setError(e.message));
  }, [open, projectId, idsKey]);

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
  const actRow = (key: string, work: () => Promise<SceneBinding>) => run(key, work, (row) =>
    setView((v) => v && { ...v, scenes: v.scenes.map((s) => (rowKey(s) === rowKey(row) ? row : s)) }));
  const suggest = () => api.suggestBindings(projectId, ids).then(setInitial).catch((e: Error) => setError(e.message));
  const running = job?.status === "running";
  const rows: Row[] = (view?.scenes ?? []).map((s) => ({ ...s, key: rowKey(s) }));
  const acceptable = rows.filter((r) => !r.binding && usable(r.suggestion) && proposal(r.suggestion).status === "same").length;
  const confirmed = rows.filter((r) => r.binding).length;
  const stale = rows.filter((r) => r.binding?.stale.length).length;
  const suggested = rows.filter((r) => r.suggestion).length;
  const failed = rows.filter((r) => r.suggestion?.failure).length;

  const columns: TableColumnsType<Row> = [
    ...(docs.length > 1 ? [{ title: t("文档", "PDF"), key: "doc", width: "14%", ellipsis: true,
      render: (_: unknown, r: Row) => <span title={r.filename}>{r.filename}</span> }] : []),
    {
      title: t("对应表", "Binding"), key: "status", width: 150,
      render: (_, r) => r.binding ? (
        <span className="bind-status">
          <Tooltip title={r.binding.source === "suggestion" ? t("按模型建议确认", "Confirmed as the model suggested") : t("人工选定", "Chosen by a person")}>
            <Tag className={`mtag ${STATUS[r.binding.status].cls}`}>{STATUS[r.binding.status][lang]}</Tag>
          </Tooltip>
          {r.binding.stale.length > 0 && (
            <Tooltip title={staleText(r.binding.stale, t)}><Tag className="mtag review">{t("待重核", "Recheck")}</Tag></Tooltip>
          )}
        </span>
      ) : <span className="muted">{t("未确认", "Not confirmed")}</span>,
    },
    {
      title: t("需求场景", "Scene"), key: "scene", width: "34%", ellipsis: true,
      render: (_, r) => <span title={r.title}>{r.section_id && <span className="muted">{r.section_id} </span>}{r.title}</span>,
    },
    {
      title: t("素材（首选）", "Asset (preferred)"), key: "asset", ellipsis: true,
      render: (_, r) => {
        if (r.binding) {
          const preferred = r.binding.assets.find((a) => a.preferred);
          return preferred ? <span title={preferred.title}>{preferred.title}{r.binding.assets.length > 1 && <span className="muted"> +{r.binding.assets.length - 1}</span>}</span>
            : <span className="muted">—</span>;
        }
        const s = r.suggestion;
        if (!s) return <span className="muted">—</span>;
        if (s.failure) return <Tooltip title={s.failure}><Tag className="mtag review">{t("模型没有可用回复", "No usable reply")}</Tag></Tooltip>;
        const chosen = s.candidates.filter((c) => s.binding.includes(c.id));
        const preferred = chosen.find((c) => c.id === s.preferred) ?? chosen[0];
        return (
          <div className="batch-cand">
            {s.outdated.length > 0 && <Tooltip title={staleText(s.outdated, t)}><Tag className="mtag review">{t("建议已过期", "Outdated")}</Tag></Tooltip>}
            {preferred ? <VerdictTag verdict={preferred.verdict} /> : <Tag className="mtag not">{t("没有合适的", "None fits")}</Tag>}
            {preferred && <span className="muted" title={preferred.title}>{preferred.title}{chosen.length > 1 ? ` +${chosen.length - 1}` : ""}</span>}
          </div>
        );
      },
    },
    {
      title: "", key: "act", width: 172,
      render: (_, r) => {
        const offer = usable(r.suggestion) && !(r.binding && !r.binding.stale.length && sameDraft(fromBinding(r.binding), proposal(r.suggestion)));
        return (
          <span className="bind-actions" onClick={(e) => e.stopPropagation()}>
            {offer && (
              <Button size="small" loading={busy === `accept:${r.key}`}
                onClick={() => act(`accept:${r.key}`, () => api.acceptBindings(projectId, ids, [ref(r)]))}>
                {t("接受建议", "Accept")}
              </Button>
            )}
            {r.binding?.status !== "none" && (
              <Button size="small" type="text" loading={busy === `none:${r.key}`}
                onClick={() => actRow(`none:${r.key}`, () => api.confirmBinding(projectId, ref(r), { status: "none", assets: [], preferred: null, changes: "" }))}>
                {t("没有素材", "No asset")}
              </Button>
            )}
          </span>
        );
      },
    },
  ];

  return (
    <div className="settings-form">
      <p className="muted">
        {t("模型从候选素材里挑出与每个需求场景做同一测试的一组素材（只差数值的变体算一组）。你确认后才存进对应表，所有项目共用。会把场景原文、抽取的事实和候选素材的名字、故事、差异发给已配置的模型。",
          "The model picks, for every scene, the group of candidate assets that build the same test (variants that differ only in values belong together). A row enters the binding table, shared by all projects, only when you confirm it. The scenes' source text and facts, and the candidates' names, stories and differences, go to your configured model.")}
      </p>
      {!docs.length && <Alert type="info" showIcon title={t("先在上面选择 PDF。", "Select PDFs above first.")} />}
      {error && <Alert type="error" showIcon title={error} />}
      {job && (running || job.status !== "completed") && <JobProgress job={job} onCancel={cancel} unit={["个场景", "scenes"]} />}
      {failed > 0 && !running && (
        <Alert type="warning" showIcon title={t(`${failed} 个场景模型没有给出可用回复，可以再建议一次。`, `The model gave no usable reply for ${failed} scenes; ask again.`)} />
      )}
      <div className="settings-actions">
        <Tooltip title={suggested ? t("没变的场景和候选直接用上次的回复，不再调用模型。", "Scenes and candidates that did not change reuse the last reply without a new call.") : undefined}>
          <Button type={suggested ? "default" : "primary"} icon={<RobotOutlined />} onClick={suggest} disabled={running || !view}>
            {suggested ? t("重新建议", "Suggest again") : t("让模型建议绑定", "Suggest bindings")}
          </Button>
        </Tooltip>
        <Button icon={<CheckOutlined />} disabled={!acceptable || running} loading={busy === "accept-all"}
          onClick={() => act("accept-all", () => api.acceptBindings(projectId, ids))}>
          {t(`接受全部“同一测试”的建议（${acceptable}）`, `Accept every "same test" suggestion (${acceptable})`)}
        </Button>
        {view && (
          <span className="muted bind-counts">
            {t(`已确认 ${confirmed} / ${rows.length}`, `${confirmed} / ${rows.length} confirmed`)}
            {stale > 0 && t(` · 待重核 ${stale}`, ` · ${stale} to recheck`)}
          </span>
        )}
      </div>
      {view && (
        <Table<Row>
          className="ov-table batch-table bind-table"
          size="small"
          columns={columns}
          dataSource={rows}
          pagination={false}
          tableLayout="fixed"
          scroll={{ y: 380 }}
          expandable={{
            expandedRowKeys: expanded,
            onExpandedRowsChange: (keys) => setExpanded(keys as string[]),
            expandRowByClick: true,
            expandedRowRender: (r) => (
              <BindingEditor key={`${r.binding?.confirmed_at}|${r.suggestion?.created_at}`} row={r} busy={busy} onSave={(draft) => actRow(`save:${r.key}`, () => api.confirmBinding(projectId, ref(r), draft))}
                onRemove={() => actRow(`remove:${r.key}`, () => api.unbind(projectId, ref(r)))} />
            ),
          }}
        />
      )}
    </div>
  );
}

type Choice = Pick<SuggestedCandidate, "asset_id" | "version_id" | "version_number" | "title" | "verdict" | "reason" | "changes" | "latest"> & { rank: number | null };

/** Every candidate with the model's verdict and reasons; the person picks the group, the preferred one and the status. */
function BindingEditor({ row, busy, onSave, onRemove }: { row: Row; busy: string | null; onSave: (d: BindingDraft) => void; onRemove: () => void }) {
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
  const shown = all ? choices : choices.filter((c) => inGroup(c) || (c.verdict && c.verdict !== "不是"));
  const hidden = choices.length - shown.length;

  const toggle = (c: Choice, on: boolean) => setDraft((d) => {
    const assets = on ? [...d.assets, { asset_id: c.asset_id, version_id: c.version_id }]
      : d.assets.filter((a) => !(a.asset_id === c.asset_id && a.version_id === c.version_id));
    const preferred = assets.some((a) => a.asset_id === d.preferred) ? d.preferred : assets[0]?.asset_id ?? null;
    return { ...d, assets, preferred, status: d.status === "none" && assets.length ? (c.verdict === "同一测试但要改" ? "modify" : "same") : d.status };
  });
  const none = draft.status === "none";
  const valid = none || draft.assets.length > 0;

  return (
    <div className="bind-editor">
      {s?.note && <div className="muted bind-note">{t("模型备注：", "Model note: ")}{s.note}</div>}
      {!choices.length && <div className="muted">{t("还没有候选：先让模型建议。", "No candidates yet: ask the model first.")}</div>}
      <div className="bind-cands">
        {shown.map((c) => (
          <div key={`${c.asset_id}:${c.version_id}`} className={`bind-cand${inGroup(c) ? " on" : ""}`}>
            <Checkbox checked={inGroup(c)} disabled={none} onChange={(e) => toggle(c, e.target.checked)} aria-label={t("绑定", "Bind")} />
            <Tooltip title={t("首选", "Preferred")}>
              <Radio checked={draft.preferred === c.asset_id && inGroup(c)} disabled={none || !inGroup(c)}
                onChange={() => setDraft((d) => ({ ...d, preferred: c.asset_id }))} />
            </Tooltip>
            <VerdictTag verdict={c.verdict} />
            <span className="name" title={c.title}>{c.title}</span>
            {!c.latest && <Tag className="mtag review">{t("有新版本", "Newer version")}</Tag>}
            <span className="muted rank">{c.rank ? `#${c.rank}` : ""} v{c.version_number}</span>
            {(c.reason || c.changes) && (
              <div className="why">{c.reason}{c.changes && <b>{t(" 要改：", " Change: ")}{c.changes}</b>}</div>
            )}
          </div>
        ))}
      </div>
      {hidden > 0 && <Button size="small" type="link" onClick={() => setAll(true)}>{t(`显示其余 ${hidden} 个候选（模型判“不是”）`, `Show ${hidden} more candidates (judged a different test)`)}</Button>}
      <div className="bind-form">
        <Radio.Group value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value, ...(e.target.value === "none" ? { assets: [], preferred: null } : {}) }))}
          options={(["same", "modify", "none"] as BindingStatus[]).map((value) => ({ value, label: t(STATUS[value].zh, STATUS[value].en) }))} />
        {draft.status === "modify" && (
          <Input.TextArea value={draft.changes} maxLength={2000} autoSize={{ minRows: 1, maxRows: 4 }} placeholder={t("要改什么", "What to change")}
            onChange={(e) => setDraft((d) => ({ ...d, changes: e.target.value }))} />
        )}
        <div className="settings-actions">
          <Button type="primary" size="small" disabled={!valid} loading={busy === `save:${row.key}`} onClick={() => onSave(draft)}>
            {row.binding ? t("更新绑定", "Update binding") : t("确认绑定", "Confirm binding")}
          </Button>
          {row.binding && (
            <Button size="small" loading={busy === `remove:${row.key}`} onClick={onRemove}>{t("撤销绑定", "Remove binding")}</Button>
          )}
          {row.binding && (
            <span className="muted">{t(`确认于 ${dateTime(row.binding.confirmed_at)}`, `Confirmed ${dateTime(row.binding.confirmed_at)}`)}</span>
          )}
        </div>
      </div>
    </div>
  );
}
