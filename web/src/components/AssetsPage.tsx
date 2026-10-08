import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Collapse, Empty, Input, Select, Spin, Switch, Table, type TableColumnsType } from "antd";
import { PictureOutlined, RobotOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import { api, type AssetRow, type Job, type VersionRef } from "../api";
import { dateTime, useT } from "../i18n";
import { useJob } from "../jobs";
import { PREVIEW_FAILED, valueLabel } from "../vocab";
import { AssetDetail } from "./AssetDetail";
import { ImportAssetsDialog, ImportReports } from "./ImportAssetsDialog";
import { JobProgress } from "./JobProgress";

interface Props {
  esmini: boolean;
  onSettings: () => void;
  onLibraryChanged: () => void;
  onOpenScene: (projectId: string, documentId: string, sceneId: string) => void;
}

type Sort = "newest" | "name" | "function" | "road" | "classification" | "compatibility";
const ALL = "__all";
const keyOf = (v: VersionRef) => `${v.asset_id}:${v.version_id}`;

export function AssetsPage({ esmini, onSettings, onLibraryChanged, onOpenScene }: Props) {
  const { t } = useT();
  const [rows, setRows] = useState<AssetRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<VersionRef | null>(null);
  const [importing, setImporting] = useState(false);
  const [pending, setPending] = useState(0);
  const [lastJob, setLastJob] = useState<Job | null>(null);

  const load = useCallback(() => {
    api.assets().then(setRows).catch((e: Error) => setError(e.message));
    api.pendingClassification().then((p) => setPending(p.count)).catch(() => undefined);
  }, []);
  const changed = useCallback(() => {
    load();
    onLibraryChanged();
  }, [load, onLibraryChanged]);
  const [previewJob, setPreviewJob] = useState<Job | null>(null);
  const { job, setJob, cancel } = useJob(lastJob, (finished) => {
    changed();
    // An import may have started the previews (a setting).
    if (finished.kind === "asset_import") api.jobs("preview_batch").then((all) => setPreviewJob(all[0] ?? null)).catch(() => undefined);
  });
  const previews = useJob(previewJob, load);

  useEffect(() => {
    load();
    api.jobs("asset_import").then((all) => setLastJob(all[0] ?? null)).catch(() => undefined);
    api.jobs("preview_batch").then((all) => setPreviewJob(all[0] ?? null)).catch(() => undefined);
  }, [load]);
  const makePreviews = () => api.startPreviews().then(setPreviewJob).catch((e: Error) => setError(e.message));
  const previewing = previews.job?.status === "running";

  const busy = job?.status === "running";
  const modelClassify = async (versions?: VersionRef[]) => {
    try {
      setLastJob(await api.classify(versions?.map((v) => ({ asset_id: v.asset_id, version_id: v.version_id! })), !!versions));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <main className="ox-page assets-page">
      <section className="panel">
        <div className="ph">
          {t("资产管理", "Asset management")}
          {rows && <span className="meta">{t(`${rows.filter((r) => r.latest).length} 个资产 · ${rows.length} 个版本`, `${rows.filter((r) => r.latest).length} assets · ${rows.length} versions`)}</span>}
          <Button icon={<PictureOutlined />} disabled={previewing} onClick={makePreviews}
            title={t("为还没有画面的每个版本跑 esmini 截一张图，并画出道路俯视图", "Run esmini on each version without a frame to save one, and draw each road from above")}>
            {t("生成预览", "Make previews")}
          </Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setImporting(true)}>{t("导入资产", "Import assets")}</Button>
        </div>
        {error && <Alert type="error" showIcon closable title={error} onClose={() => setError(null)} />}
        <>
          {job && (
            <Collapse size="small" className="job-strip" defaultActiveKey={busy ? ["job"] : []} items={[{
              key: "job",
              label: <JobSummary job={job} />,
              children: <div className="settings-form"><JobProgress job={job} onCancel={cancel} unit={["个场景", "scenarios"]} /><ImportReports job={job} /></div>,
              extra: !busy && <Button size="small" type="text" onClick={(e) => { e.stopPropagation(); setJob(null); setLastJob(null); }}>{t("收起", "Dismiss")}</Button>,
            }]} />
          )}
          {previews.job && (
            <Collapse size="small" className="job-strip preview-strip" defaultActiveKey={previewing ? ["job"] : []} items={[{
              key: "job",
              label: <PreviewSummary job={previews.job} />,
              children: <div className="settings-form"><JobProgress job={previews.job} onCancel={previews.cancel} unit={["个版本", "versions"]} /></div>,
              extra: !previewing && <Button size="small" type="text" onClick={(e) => { e.stopPropagation(); previews.setJob(null); setPreviewJob(null); }}>{t("收起", "Dismiss")}</Button>,
            }]} />
          )}
          {pending > 0 && !busy && (
            <div className="pending-strip">
              <span>{t(`${pending} 个版本待模型复核分类`, `Versions awaiting model classification: ${pending}`)}</span>
              <Button size="small" icon={<RobotOutlined />} onClick={() => modelClassify()}>{t("继续模型分类", "Resume model classification")}</Button>
            </div>
          )}
          {!rows ? <div className="center-pad"><Spin /></div> : (
            <AssetTable rows={rows} selected={selected} onSelect={setSelected} onImport={() => setImporting(true)} />
          )}
        </>
      </section>
      <section className="panel">
        {selected ? (
          <AssetDetail
            version={selected}
            busy={busy}
            esmini={esmini}
            onSettings={onSettings}
            onSelect={setSelected}
            onClose={() => setSelected(null)}
            onChanged={changed}
            onDeleted={() => { setSelected(null); changed(); }}
            onModelClassify={(v) => modelClassify([v])}
            onOpenScene={onOpenScene}
          />
        ) : (
          <div className="ov-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("在左侧选择一个版本，查看预览、关联条款和来源。", "Select a version on the left to see its preview, the clauses that adopt it and its source.")} />
          </div>
        )}
      </section>
      <ImportAssetsDialog open={importing} onClose={() => { setImporting(false); api.jobs("asset_import").then((all) => setLastJob(all[0] ?? null)).catch(() => undefined); }} onFinished={changed} />
    </main>
  );
}

function PreviewSummary({ job }: { job: Job }) {
  const { t } = useT();
  const counts = (job.result ?? {}) as Partial<Record<"frames" | "failed" | "kept" | "road_missing" | "drawings", number>>;
  const states: Record<string, string> = {
    running: t(`正在生成预览 ${job.done}/${job.total}`, `Making previews ${job.done}/${job.total}`), completed: t("预览已生成", "Previews made"),
    stopped: t("预览已停止", "Previews stopped"), failed: t("预览任务失败", "Previews failed"),
  };
  return (
    <span className="job-summary">
      <b>{states[job.status] ?? job.status}</b>
      <span className="muted">
        {t(`新画面 ${counts.frames ?? 0} · 播放失败 ${counts.failed ?? 0} · 已有 ${counts.kept ?? 0} · 道路缺失 ${counts.road_missing ?? 0}`,
          `${counts.frames ?? 0} new frames · ${counts.failed ?? 0} failed · ${counts.kept ?? 0} kept · ${counts.road_missing ?? 0} without road`)}
      </span>
    </span>
  );
}

function JobSummary({ job }: { job: Job }) {
  const { t } = useT();
  const states: Record<string, string> = {
    running: t("导入任务进行中", "Import running"), completed: t("导入完成", "Import completed"), stopped: t("任务已停止", "Import stopped"),
    interrupted: t("任务已中断", "Import interrupted"), failed: t("任务失败", "Import failed"),
  };
  return (
    <span className="job-summary">
      <b>{states[job.status]}</b>
      <span className="muted">
        {t(`已保存 / 复用 ${job.saved ?? 0} 个场景`, `${job.saved ?? 0} scenarios saved / reused`)}
        {job.stage === "classifying" && job.total ? t(` · 分类 ${job.done}/${job.total}`, ` · Classification ${job.done}/${job.total}`) : ""}
        {(job.error || job.failed) ? t(" · 有需要处理的问题", " · needs attention") : ""}
      </span>
    </span>
  );
}

function AssetTable({ rows, selected, onSelect, onImport }: { rows: AssetRow[]; selected: VersionRef | null; onSelect: (v: VersionRef) => void; onImport: () => void }) {
  const { t, lang } = useT();
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<Sort>("newest");
  const [latestOnly, setLatestOnly] = useState(true);
  const facet = (key: keyof AssetRow) => [...new Set(rows.map((r) => String(r[key])))].sort();

  const visible = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    const kept = rows.filter((r) => (!latestOnly || r.latest)
      && Object.entries(filters).every(([k, v]) => v === ALL || String(r[k as keyof AssetRow]) === v)
      && (!q || `${r.name} ${r.xosc_name} ${r.source_name}`.toLocaleLowerCase().includes(q)));
    const value = (r: AssetRow) => (sort === "name" ? r.name : valueLabel(String(r[sort as keyof AssetRow]), lang)).toLocaleLowerCase();
    return kept.sort((a, b) => (sort === "newest" ? b.created_at.localeCompare(a.created_at) : value(a).localeCompare(value(b))));
  }, [rows, query, filters, sort, latestOnly, lang]);

  const filterSelect = (key: keyof AssetRow, label: string) => (
    <Select size="small" value={filters[key] ?? ALL} popupMatchSelectWidth={false} aria-label={label}
      onChange={(v) => setFilters((f) => ({ ...f, [key]: v }))}
      options={[{ value: ALL, label: `${label}: ${t("全部", "All")}` }, ...facet(key).map((v) => ({ value: v, label: valueLabel(v, lang) }))]} />
  );

  const columns: TableColumnsType<AssetRow> = [
    { title: t("名称", "Name"), dataIndex: "name", ellipsis: true, render: (n: string, r) => <span title={r.xosc_name}>{n}</span> },
    ...(latestOnly ? [] : [{ title: t("版本", "Version"), dataIndex: "version_number", width: 64, render: (n: number) => `v${n}` }]),
    { title: t("功能", "Function"), dataIndex: "function", width: 90, render: (v: string) => valueLabel(v, lang) },
    { title: t("道路", "Road"), dataIndex: "road", width: 90, render: (v: string) => valueLabel(v, lang) },
    {
      title: t("分类状态", "Classification"), dataIndex: "classification", width: 150,
      render: (v: string, r) => <>{valueLabel(v, lang)}{r.needs_review && <span className="st warn"> · {t("待复核", "review")}</span>}</>,
    },
    {
      title: t("预览状态", "Preview"), dataIndex: "compatibility", width: 100,
      render: (v: string) => <span className={`dot-status ${v === "playable" ? "ok" : PREVIEW_FAILED.has(v) ? "bad" : ""}`}>{valueLabel(v, lang)}</span>,
    },
    { title: t("导入时间", "Imported"), dataIndex: "created_at", width: 130, render: dateTime },
  ];

  return (
    <div className="asset-table">
      <div className="asset-filters">
        <Input size="small" allowClear prefix={<SearchOutlined />} value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder={t("搜索名称、文件或来源", "Search names, files or sources")} aria-label={t("搜索资产", "Search assets")} />
        {filterSelect("function", t("功能", "Function"))}
        {filterSelect("road", t("道路", "Road"))}
        {filterSelect("classification", t("分类", "Classification"))}
        {filterSelect("compatibility", t("预览", "Preview"))}
        <Select size="small" value={sort} onChange={setSort} popupMatchSelectWidth={false} aria-label={t("排序", "Sort")} options={[
          { value: "newest", label: t("最近导入", "Newest first") }, { value: "name", label: t("名称", "Name") },
          { value: "function", label: t("功能", "Function") }, { value: "road", label: t("道路", "Road") },
          { value: "classification", label: t("分类状态", "Classification") }, { value: "compatibility", label: t("预览状态", "Preview") },
        ]} />
        <label className="latest-only"><Switch size="small" checked={latestOnly} onChange={setLatestOnly} /> {t("仅最新版本", "Latest only")}</label>
      </div>
      <div className="muted asset-count">{t(`显示 ${visible.length} 个版本 · 点击一行查看详情`, `Showing ${visible.length} versions · select a row to inspect`)}</div>
      <Table<AssetRow>
        className="ov-table ov-reports"
        size="small"
        rowKey={(r) => keyOf(r)}
        columns={columns}
        dataSource={visible}
        pagination={visible.length > 200 ? { pageSize: 200, showSizeChanger: false } : false}
        tableLayout="fixed"
        rowClassName={(r) => (selected && keyOf(r) === keyOf(selected) ? "row-active" : "")}
        onRow={(r) => ({ onClick: () => onSelect({ asset_id: r.asset_id, version_id: r.version_id }) })}
        locale={{
          emptyText: rows.length ? t("没有符合筛选条件的资产。调整筛选或搜索后重试。", "No assets match these filters. Adjust the filters or search.") : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("资产库为空。上传成对的 XOSC/XODR、SIM 或 ZIP。", "Your library is empty. Add paired XOSC/XODR, SIM or ZIP files.")}>
              <Button type="primary" icon={<UploadOutlined />} onClick={onImport}>{t("导入资产", "Import assets")}</Button>
            </Empty>
          ),
        }}
      />
    </div>
  );
}
