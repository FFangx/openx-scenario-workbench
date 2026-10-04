import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Collapse, Empty, Input, Select, Spin, Switch, Table, Tabs, Tag, type TableColumnsType } from "antd";
import { DownloadOutlined, FileTextOutlined, RobotOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import { api, urls, type AssetRow, type Job, type RequirementRecord, type VersionRef } from "../api";
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
  const [tab, setTab] = useState<"assets" | "requirements">("assets");
  const [rows, setRows] = useState<AssetRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<VersionRef | null>(null);
  const [requirement, setRequirement] = useState<RequirementRecord | null>(null);
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
  const { job, setJob, cancel } = useJob(lastJob, changed);

  useEffect(() => {
    load();
    api.jobs("asset_import").then((all) => setLastJob(all[0] ?? null)).catch(() => undefined);
  }, [load]);

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
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setImporting(true)}>{t("导入资产", "Import assets")}</Button>
        </div>
        {error && <Alert type="error" showIcon closable title={error} onClose={() => setError(null)} />}
        <Tabs
          className="assets-tabs"
          activeKey={tab}
          onChange={(k) => setTab(k as "assets" | "requirements")}
          items={[
            {
              key: "assets",
              label: t("仿真资产", "Simulation assets"),
              children: (
                <>
                  {job && (
                    <Collapse size="small" className="job-strip" defaultActiveKey={busy ? ["job"] : []} items={[{
                      key: "job",
                      label: <JobSummary job={job} />,
                      children: <div className="settings-form"><JobProgress job={job} onCancel={cancel} unit={["个场景", "scenarios"]} /><ImportReports job={job} /></div>,
                      extra: !busy && <Button size="small" type="text" onClick={(e) => { e.stopPropagation(); setJob(null); setLastJob(null); }}>{t("收起", "Dismiss")}</Button>,
                    }]} />
                  )}
                  {pending > 0 && !busy && (
                    <div className="pending-strip">
                      <span>{t(`${pending} 个版本待模型复核分类`, `Versions awaiting model classification: ${pending}`)}</span>
                      <Button size="small" icon={<RobotOutlined />} onClick={() => modelClassify()}>{t("继续模型分类", "Resume model classification")}</Button>
                    </div>
                  )}
                  {!rows ? <div className="center-pad"><Spin /></div> : (
                    <AssetTable rows={rows} selected={selected} onSelect={(v) => { setSelected(v); setRequirement(null); }} onImport={() => setImporting(true)} />
                  )}
                </>
              ),
            },
            {
              key: "requirements",
              label: t("PDF 需求场景库", "PDF requirement library"),
              children: <RequirementLibrary selected={requirement} onSelect={(r) => { setRequirement(r); setSelected(null); }} />,
            },
          ]}
        />
      </section>
      <section className="panel">
        {tab === "assets" && selected ? (
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
          />
        ) : tab === "requirements" && requirement ? (
          <RequirementDetail record={requirement} onOpen={() => onOpenScene(requirement.project_id, requirement.document_id, requirement.scene_id)} />
        ) : (
          <div className="ov-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={tab === "assets" ? t("在左侧选择一个版本查看详情、预览和分类。", "Select a version on the left to see its details, preview and labels.")
              : t("在左侧选择一条已入库的需求。", "Select a published requirement on the left.")} />
          </div>
        )}
      </section>
      <ImportAssetsDialog open={importing} onClose={() => { setImporting(false); api.jobs("asset_import").then((all) => setLastJob(all[0] ?? null)).catch(() => undefined); }} onFinished={changed} />
    </main>
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

function RequirementLibrary({ selected, onSelect }: { selected: RequirementRecord | null; onSelect: (r: RequirementRecord) => void }) {
  const { t } = useT();
  const [records, setRecords] = useState<RequirementRecord[] | null>(null);
  const [query, setQuery] = useState("");
  useEffect(() => {
    api.requirements().then(setRecords).catch(() => setRecords([]));
  }, []);
  if (!records) return <div className="center-pad"><Spin /></div>;
  if (!records.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("在工作台的“需求事实”中核对场景，点击确认入库。", "Review a scene under Requirement facts in the workbench and publish it.")} />;
  }
  const q = query.trim().toLocaleLowerCase();
  const visible = records.filter((r) => !q || `${r.title} ${r.preferred_text}`.toLocaleLowerCase().includes(q));
  return (
    <div className="asset-table">
      <div className="asset-filters">
        <Input size="small" allowClear prefix={<SearchOutlined />} value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder={t("名称或原文", "Name or source text")} aria-label={t("搜索需求", "Search requirements")} />
      </div>
      <div className="muted asset-count">{t(`${visible.length} 条需求`, `${visible.length} requirements`)}</div>
      <Table<RequirementRecord>
        className="ov-table ov-reports req-library"
        size="small"
        rowKey="library_id"
        pagination={false}
        tableLayout="fixed"
        dataSource={visible}
        rowClassName={(r) => (r.library_id === selected?.library_id ? "row-active" : "")}
        onRow={(r) => ({ onClick: () => onSelect(r) })}
        locale={{ emptyText: t("没有符合搜索条件的需求。", "No requirements match this search.") }}
        columns={[
          { title: t("需求场景", "Requirement"), dataIndex: "title", ellipsis: true },
          { title: t("修订", "Rev."), dataIndex: "revision", width: 60, render: (n: number) => `r${n}` },
          { title: t("功能", "Function"), key: "f", width: 90, render: (_, r) => String(r.classification.function ?? "—") },
          { title: t("确认时间", "Confirmed"), dataIndex: "reviewed_at", width: 130, render: dateTime },
        ]}
      />
    </div>
  );
}

function RequirementDetail({ record, onOpen }: { record: RequirementRecord; onOpen: () => void }) {
  const { t } = useT();
  return (
    <div className="asset-detail">
      <div className="asset-detail-head">
        <div className="sel-name">
          <div className="name">{record.title}</div>
          <div className="muted">{t(`已确认修订 ${record.revision} · ${dateTime(record.reviewed_at)}`, `Confirmed revision ${record.revision} · ${dateTime(record.reviewed_at)}`)}</div>
        </div>
        <Tag className="mtag direct">{t("已入库", "Published")}</Tag>
      </div>
      <p className="facts-text">{record.preferred_text}</p>
      <Collapse size="small" items={[{
        key: "s",
        label: t("分类与结构", "Classification and structure"),
        children: <pre className="json-view">{JSON.stringify({ classification: record.classification, structure: record.structure }, null, 2)}</pre>,
      }]} />
      <div className="settings-actions">
        <Button icon={<DownloadOutlined />} href={urls.requirement(record.library_id)}>{t("下载场景包", "Download scene package")}</Button>
        <Button icon={<FileTextOutlined />} onClick={onOpen}>{t("打开源文档", "Open source document")}</Button>
      </div>
    </div>
  );
}
