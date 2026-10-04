import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Empty, Input, Progress, Spin, Table, Tag, Tooltip, type TableColumnsType } from "antd";
import { DownloadOutlined, FileTextOutlined, FormOutlined, InboxOutlined, SearchOutlined } from "@ant-design/icons";
import { api, urls, verdictClass, verdictLabel, type Overview, type Report, type ReportDetail, type TraceSource } from "../api";
import { dateTime, useT } from "../i18n";
import { PREVIEW_FAILED, valueLabel } from "../vocab";
import { BatchCounts, BatchTable, encoderName } from "./BatchTable";
import type { Page } from "./TopBar";

interface Props {
  projectId: string | null;
  onNavigate: (page: Page) => void;
  onOpenScene: (documentId: string, sceneId: string) => void;
}

type Recent = Overview["recent"][number];

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}
const csvCell = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;

export function OverviewPage({ projectId, onNavigate, onOpenScene }: Props) {
  const { t } = useT();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.overview().then(setOverview).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="ox-page overview">
      <section className="panel ov-library">
        <div className="ph">{t("资产库概况", "Asset library")}</div>
        {error && <Alert type="error" showIcon title={error} />}
        {!overview ? <div className="center-pad"><Spin /></div> : <Library overview={overview} onNavigate={onNavigate} />}
      </section>
      <section className="panel ov-decisions">
        <Decisions projectId={projectId} onOpenScene={onOpenScene} />
      </section>
    </main>
  );
}

function Library({ overview, onNavigate }: { overview: Overview; onNavigate: (page: Page) => void }) {
  const { t, lang } = useT();
  const [find, setFind] = useState("");
  const tested = overview.assets - overview.untested;

  const rows = useMemo(() => {
    const q = find.trim().toLocaleLowerCase();
    return overview.recent.filter((r) => !q || [r.title, r.source_name, valueLabel(r.compatibility, lang)].some((v) => v.toLocaleLowerCase().includes(q)));
  }, [overview.recent, find, lang]);

  const headings = [t("资产", "Asset"), t("来源", "Source"), t("版本", "Version"), t("预览状态", "Preview"), t("导入时间", "Imported")];
  const exportCsv = () => {
    const lines = [headings, ...overview.recent.map((r) => [r.title, r.source_name, r.version_number, valueLabel(r.compatibility, lang), dateTime(r.created_at)])];
    download("openx-recent-imports.csv", "﻿" + lines.map((l) => l.map(csvCell).join(",")).join("\n"), "text/csv");
  };

  const columns: TableColumnsType<Recent> = [
    { title: headings[0], dataIndex: "title", ellipsis: true, sorter: (a, b) => a.title.localeCompare(b.title) },
    { title: headings[1], dataIndex: "source_name", ellipsis: true, width: "22%", sorter: (a, b) => a.source_name.localeCompare(b.source_name) },
    { title: headings[2], dataIndex: "version_number", width: 70, align: "right", render: (v: number) => `v${v}`, sorter: (a, b) => a.version_number - b.version_number },
    {
      title: headings[3], dataIndex: "compatibility", width: 110,
      render: (v: string) => <span className={`dot-status ${v === "playable" ? "ok" : PREVIEW_FAILED.has(v) ? "bad" : ""}`}>{valueLabel(v, lang)}</span>,
    },
    { title: headings[4], dataIndex: "created_at", width: 140, render: dateTime, defaultSortOrder: "descend", sorter: (a, b) => a.created_at.localeCompare(b.created_at) },
  ];

  if (!overview.assets) {
    return (
      <div className="ov-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("资产库还是空的。导入 XOSC/XODR、ZIP 或 .sim 场景后，可在工作台检索复用。", "The asset library is empty. Import XOSC/XODR, ZIP or .sim scenarios to search them in the workbench.")}>
          <Button type="primary" icon={<InboxOutlined />} onClick={() => onNavigate("assets")}>{t("前往资产管理", "Go to asset management")}</Button>
        </Empty>
      </div>
    );
  }

  const metrics: [string, number, string?][] = [
    [t("资产", "Assets"), overview.assets],
    [t("版本", "Versions"), overview.versions],
    [t("可播放", "Playable"), overview.playable, overview.playable ? "ok" : undefined],
    [t("未检测", "Not tested"), overview.untested],
  ];

  return (
    <>
      <div className="metrics">
        {metrics.map(([label, value, cls]) => (
          <div key={label} className="metric">
            <span>{label}</span>
            <b className={cls}>{value}</b>
          </div>
        ))}
      </div>
      <div className="coverage">
        <div>
          <span className="muted">{t("预览检测覆盖率", "Preview test coverage")}</span>
          <Progress percent={Math.round((tested / overview.assets) * 100)} size="small" />
          <span className="cap">{t(`已检测 ${tested}/${overview.assets} 个资产`, `${tested}/${overview.assets} assets tested`)}</span>
        </div>
        <div>
          <span className="muted">{t("已检测资产的可播放比例", "Playable among tested assets")}</span>
          {tested ? (
            <>
              <Progress percent={Math.round((overview.playable / tested) * 100)} size="small" status="success" />
              <span className="cap">{t(`${overview.playable}/${tested} 可播放`, `${overview.playable}/${tested} playable`)}</span>
            </>
          ) : (
            <span className="cap">{t("尚未检测", "No assets tested yet")}</span>
          )}
        </div>
      </div>
      <p className="muted ov-note">
        {t(`预览失败 ${overview.unavailable} 个 · 状态仅代表已检测的版本。`, `Preview failures: ${overview.unavailable} · Status reflects tested versions only.`)}
      </p>
      <div className="sec-head">
        <span className="sec-title">{t("最近导入", "Recent imports")}</span>
        <span className="muted">{t(`${rows.length} / ${overview.recent.length} 条记录`, `${rows.length} / ${overview.recent.length} records`)}</span>
        <Input allowClear size="small" prefix={<SearchOutlined />} placeholder={t("查找导入记录", "Find imports")} value={find} onChange={(e) => setFind(e.target.value)} style={{ width: 200 }} />
        <Button size="small" icon={<DownloadOutlined />} onClick={exportCsv}>{t("导出 CSV", "Export CSV")}</Button>
      </div>
      <Table<Recent>
        className="ov-table"
        size="small"
        rowKey="version_id"
        columns={columns}
        dataSource={rows}
        pagination={false}
        tableLayout="fixed"
        locale={{ emptyText: t("没有符合条件的导入记录", "No matching imports") }}
      />
    </>
  );
}

function Decisions({ projectId, onOpenScene }: { projectId: string | null; onOpenScene: (d: string, s: string) => void }) {
  const { t, lang } = useT();
  const [reports, setReports] = useState<Report[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReports(null);
    setSelected(null);
    if (!projectId) return;
    api.reports(projectId).then((r) => {
      setReports(r);
      setSelected(r[0]?.report_id ?? null);
    }).catch((e: Error) => setError(e.message));
  }, [projectId]);

  useEffect(() => {
    setDetail(null);
    if (projectId && selected) api.report(projectId, selected).then(setDetail).catch((e: Error) => setError(e.message));
  }, [projectId, selected]);

  const columns: TableColumnsType<Report> = [
    { title: t("保存时间", "Saved"), dataIndex: "saved_at", width: 132, render: dateTime },
    {
      title: t("需求 / 文档", "Requirement / document"), key: "title", ellipsis: true,
      render: (_, r) => (
        <span>
          {r.kind === "batch" && <FileTextOutlined className="muted" style={{ marginRight: 6 }} />}
          {r.scene.title ?? "—"}
        </span>
      ),
    },
    {
      title: t("结论", "Verdict"), key: "level", width: 150,
      render: (_, r) =>
        r.kind === "batch" ? (
          <Tag className="mtag review">{t(`整份 PDF · ${r.scene_count ?? 0} 个场景`, `Whole PDF · ${r.scene_count ?? 0} scenes`)}</Tag>
        ) : r.level ? (
          <Tag className={`mtag ${verdictClass(r.level)}`}>{verdictLabel(r.level, r.review_kind, lang)}</Tag>
        ) : "—",
    },
  ];

  return (
    <>
      <div className="ph">
        {t("项目决策记录", "Saved project decisions")}
        {reports && <span className="meta">{t(`${reports.length} 条`, `${reports.length} saved`)}</span>}
      </div>
      {error && <Alert type="error" showIcon title={error} />}
      {!projectId ? (
        <div className="ov-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("请先在顶栏创建或选择项目。", "Create or select a project in the header first.")} /></div>
      ) : reports === null ? (
        <div className="center-pad"><Spin /></div>
      ) : !reports.length ? (
        <div className="ov-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("在工作台保存复用决策后，可在这里重新查看和下载。", "Save a reuse decision in the workbench to reopen and download it here.")} />
        </div>
      ) : (
        <>
          <Table<Report>
            className="ov-table ov-reports"
            size="small"
            rowKey="report_id"
            columns={columns}
            dataSource={reports}
            pagination={false}
            tableLayout="fixed"
            scroll={{ y: 220 }}
            rowClassName={(r) => (r.report_id === selected ? "row-active" : "")}
            onRow={(r) => ({ onClick: () => setSelected(r.report_id) })}
          />
          {!detail ? (
            <div className="center-pad"><Spin /></div>
          ) : detail.trace.kind === "batch_match" ? (
            <BatchDetail key={detail.report_id} projectId={projectId} detail={detail} onOpenScene={onOpenScene} />
          ) : (
            <DecisionDetail projectId={projectId} detail={detail} onOpenScene={onOpenScene} />
          )}
        </>
      )}
    </>
  );
}

function Downloads({ projectId, reportId }: { projectId: string; reportId: string }) {
  const { t, lang } = useT();
  return (
    <>
      <Button icon={<DownloadOutlined />} href={urls.report(projectId, reportId, "json", lang)}>{t("下载已保存 JSON", "Download saved JSON")}</Button>
      <Button icon={<DownloadOutlined />} href={urls.report(projectId, reportId, "html", lang)}>{t("下载已保存 HTML", "Download saved HTML")}</Button>
    </>
  );
}

function ContinueReview({ detail, source, onOpenScene }: { detail: ReportDetail; source: TraceSource | undefined; onOpenScene: (d: string, s: string) => void }) {
  const { t } = useT();
  const open = !!source && detail.reopenable.some((r) => r.document_id === source.document_id && r.scene_id === source.scene_id);
  return (
    <Tooltip title={open ? t("将打开最新事实修订；本报告仍保留保存时的快照。", "Opens the latest fact revision. This report keeps its saved snapshot.")
      : t("原需求场景已不在当前项目中。", "The source scene is no longer in this project.")}>
      <Button icon={<FormOutlined />} disabled={!open} onClick={() => source && onOpenScene(source.document_id!, source.scene_id!)}>
        {t("打开需求继续复核", "Continue reviewing requirement")}
      </Button>
    </Tooltip>
  );
}

function DecisionDetail({ projectId, detail, onOpenScene }: { projectId: string; detail: ReportDetail; onOpenScene: (d: string, s: string) => void }) {
  const { t, lang } = useT();
  const { source, candidate, reuse } = detail.trace;
  const level = reuse?.level ?? "review";
  return (
    <div className="ov-detail">
      <div className={`decision ${verdictClass(level)}`}>
        <div className="big">{verdictLabel(level, reuse?.review_kind, lang)}</div>
        <div className="sub">{t("保存时的快照；后续事实修订和资产更新不会改变这份报告。", "Saved snapshot. Later fact revisions and asset updates do not change this report.")}</div>
      </div>
      <div className="box flush">
        <div className="kvt">
          <span>{t("来源需求", "Source requirement")}</span>
          <span>{source?.title ?? "—"} · {t("修订", "Revision")} {source?.revision ?? "—"}</span>
          <span>{t("原文证据", "Source evidence")}</span>
          <span>
            {source?.evidence?.length
              ? source.evidence.map((e, i) => <div key={i}>{e.source_pdf} · {e.section_id} · {t("页", "pages")} {e.page_start}–{e.page_end}</div>)
              : "—"}
          </span>
          <span>{t("候选资产", "Candidate asset")}</span>
          <span>{candidate ? `${candidate.xosc} + ${candidate.xodr} · v${candidate.version_number ?? "—"}` : "—"}</span>
          <span>{t("资产版本标识", "Version ID")}</span>
          <span className="mono">{detail.version_id ?? candidate?.version_id ?? "—"}</span>
          <span>{t("保存时间", "Saved")}</span>
          <span>{dateTime(detail.saved_at)}</span>
        </div>
      </div>
      <div className="ov-actions">
        <Downloads projectId={projectId} reportId={detail.report_id} />
        <ContinueReview detail={detail} source={source} onOpenScene={onOpenScene} />
      </div>
    </div>
  );
}

function BatchDetail({ projectId, detail, onOpenScene }: { projectId: string; detail: ReportDetail; onOpenScene: (d: string, s: string) => void }) {
  const { t, lang } = useT();
  const trace = detail.trace;
  const entries = trace.entries ?? [];
  const [target, setTarget] = useState(0);
  return (
    <div className="ov-detail">
      <div className="sec-head">
        <span className="sec-title">{trace.source?.title}</span>
        <span className="muted">{t(`共 ${trace.scene_count ?? entries.length} 个场景`, `${trace.scene_count ?? entries.length} scenes`)} · {encoderName(trace.encoder, lang)}</span>
      </div>
      <BatchTable trace={trace} target={target} onTarget={setTarget} />
      <p className="muted ov-note">
        <BatchCounts trace={trace} />
        {" · "}{t("保存时的快照，含待复核和无法判断项。", "Saved assessment snapshot, including review and undecidable cases.")}
      </p>
      <div className="ov-actions">
        <Downloads projectId={projectId} reportId={detail.report_id} />
        <ContinueReview detail={detail} source={entries[target]?.source} onOpenScene={onOpenScene} />
      </div>
    </div>
  );
}
