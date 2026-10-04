import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Dropdown, Empty, Input, Segmented, Select, Tabs, Tooltip } from "antd";
import { DownOutlined, EllipsisOutlined, ExportOutlined, FullscreenOutlined, SearchOutlined } from "@ant-design/icons";
import { urls, type PdfDocument, type Scene } from "../api";
import type { LeftTab, Scope } from "../App";
import { useT } from "../i18n";
import { BatchDialog } from "./BatchDialog";
import { ExtractionDialog } from "./ExtractionDialog";
import { FactsPanel } from "./FactsPanel";
import { ImportPdfDialog } from "./ImportPdfDialog";
import { PageViewer } from "./PageViewer";

interface Props {
  projectId: string | null;
  docs: PdfDocument[];
  doc: PdfDocument | null;
  onDoc: (id: string) => void;
  onDocsChanged: (select?: string) => void;
  scope: Scope;
  onScope: (s: Scope) => void;
  scenes: Scene[];
  scene: Scene | null;
  selectedKey: string | null;
  onPick: (key: string) => void;
  onQueue: (keys: string[]) => void;
  tab: LeftTab;
  onTab: (t: LeftTab) => void;
  onSceneChanged: (s: Scene) => void;
}

const keyOf = (s: Scene) => `${s.document_id}/${s.scene_id}`;
const pagesText = (p: Scene["pages"]) => (!p ? "—" : p[0] === p[1] ? `${p[0]}` : `${p[0]} – ${p[1]}`);
const sizeText = (b: number | null) => (b == null ? "—" : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1e3)} KB`);
const sectionKey = (s: Scene) => s.section_id.split(".").map((n) => n.padStart(4, "0")).join(".");
const ALL = "__all";

export function RequirementsPanel(p: Props) {
  const { t } = useT();
  const { projectId, doc, scene, scenes } = p;
  const [sort, setSort] = useState<"section" | "page">("section");
  const [find, setFind] = useState("");
  const [fn, setFn] = useState(ALL);
  const [dialog, setDialog] = useState<"import" | "extraction" | "batch" | "reextract" | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const docName = useMemo(() => new Map(p.docs.map((d) => [d.document_id, d.filename])), [p.docs]);

  const functions = useMemo(() => [...new Set(scenes.map((s) => String(s.classification.function ?? "未知")))].sort(), [scenes]);
  const ordered = useMemo(() => {
    const q = find.trim().toLocaleLowerCase();
    return scenes
      .filter((s) => fn === ALL || String(s.classification.function ?? "未知") === fn)
      .filter((s) => !q || `${s.title} ${s.evidence.map((e) => `${e.section_id} ${e.page_start} ${e.page_end}`).join(" ")}`.toLocaleLowerCase().includes(q))
      .sort((a, b) => (p.scope === "all" && a.document_id !== b.document_id ? 0
        : sort === "section" ? sectionKey(a).localeCompare(sectionKey(b)) : (a.pages?.[0] ?? 0) - (b.pages?.[0] ?? 0)));
  }, [scenes, sort, find, fn, p.scope]);
  const number = useMemo(() => new Map(scenes.map((s, i) => [keyOf(s), i + 1])), [scenes]);

  const { onQueue } = p;
  useEffect(() => onQueue(ordered.map(keyOf)), [ordered, onQueue]);
  useEffect(() => {
    setFind("");
    setFn(ALL);
  }, [projectId, p.scope]);
  useEffect(() => {
    listRef.current?.querySelector(".scene.sel")?.scrollIntoView({ block: "nearest" });
  }, [p.selectedKey]);

  const thumb = (s: Scene) =>
    projectId && s.source_region ? urls.page(projectId, s.document_id, s.source_region.page, 220, s.source_region.clip) : undefined;
  const status = (s: Scene) =>
    s.queue_status === "assessed" ? t("已保存评估", "Assessed") : s.queue_status === "confirmed" ? t("已确认", "Confirmed") : t("待核对", "To review");

  const filtersRow = scenes.length > 0 && (
    <div className="scene-tools">
      <Input size="small" allowClear prefix={<SearchOutlined />} value={find} onChange={(e) => setFind(e.target.value)}
        placeholder={t("标题、条款或页码", "Title, clause or page")} aria-label={t("查找场景", "Find a scene")} />
      <Select size="small" value={fn} onChange={setFn} popupMatchSelectWidth={false} aria-label={t("功能分类", "Function category")}
        options={[{ value: ALL, label: t("全部功能", "All functions") }, ...functions.map((f) => ({ value: f, label: f }))]} />
      <Select size="small" value={sort} onChange={setSort} popupMatchSelectWidth={false} aria-label={t("排序", "Sort")}
        options={[{ value: "section", label: t("按条款", "By section") }, { value: "page", label: t("按页码", "By page") }]} />
    </div>
  );
  const filtered = ordered.length !== scenes.length;

  const list = !p.docs.length ? (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("当前项目还没有 PDF", "No PDF in this project yet")}>
      {projectId && <Button type="primary" onClick={() => setDialog("import")}>{t("导入 PDF", "Import PDFs")}</Button>}
    </Empty>
  ) : !scenes.length ? (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("此文档没有识别到场景。可查看解析记录核查。", "No scenes were extracted from this document. Check the extraction record.")} />
  ) : (
    <>
      {filtersRow}
      {!ordered.length && <div className="muted scene-none">{t("没有符合筛选条件的场景。清空关键词或选择全部功能。", "No scenes match. Clear your search or choose all functions.")}</div>}
      <div className="scenes" role="listbox" aria-label={t("提取的场景", "Extracted scenes")} ref={listRef}>
        {ordered.map((s) => (
          <button
            key={keyOf(s)}
            role="option"
            aria-selected={keyOf(s) === p.selectedKey}
            className={`scene${keyOf(s) === p.selectedKey ? " sel" : ""}`}
            onClick={() => p.onPick(keyOf(s))}
          >
            <span className="num">{number.get(keyOf(s))}</span>
            {thumb(s) ? <img src={thumb(s)} alt="" loading="lazy" /> : <span className="thumb-empty" />}
            <span className="tx">
              <div className="t">{s.title}</div>
              <div className="d">
                {s.section_id && `${s.section_id} – `}
                {s.preferred_text}
              </div>
              <div className="p">
                {t("页码：", "Pages: ")}<b>{pagesText(s.pages)}</b> · v{s.revision}
                {p.scope === "all" && <span className="doc-name"> · {docName.get(s.document_id)}</span>}
              </div>
            </span>
            <span className={`c ${s.queue_status ?? "pending"}`}>{status(s)}</span>
          </button>
        ))}
      </div>
    </>
  );

  const docMenu = {
    items: [
      ...p.docs.map((d) => ({ key: d.document_id, label: `${d.filename} · ${t(`${d.scene_count} 个场景`, `${d.scene_count} scenes`)}` })),
      { type: "divider" as const },
      { key: ALL, label: t(`全部 PDF 的场景（${p.docs.length} 个 PDF）`, `Scenes of all PDFs (${p.docs.length})`) },
    ],
    selectedKeys: [p.scope === "all" ? ALL : doc?.document_id ?? ""],
    onClick: ({ key }: { key: string }) => (key === ALL ? p.onScope("all") : p.onDoc(key)),
  };

  const actions = {
    items: [
      { key: "import", label: t("导入 PDF…", "Import PDFs…") },
      { type: "divider" as const },
      { key: "open", label: t("打开 PDF", "Open PDF"), disabled: !doc },
      { key: "batch", label: t("整份 PDF 匹配与汇总…", "Match entire PDF…"), disabled: !doc || p.scope === "all" },
      { key: "extraction", label: t("解析与校验记录…", "Extraction record…"), disabled: !doc || p.scope === "all" },
    ],
    onClick: ({ key }: { key: string }) =>
      key === "open" ? projectId && doc && window.open(urls.pdf(projectId, doc.document_id), "_blank") : setDialog(key as "import" | "batch" | "extraction"),
  };

  return (
    <section className="panel req">
      <div className="ph">
        <span className="n">1</span>{t("需求与提取的场景", "Requirements and extracted scenes")}
      </div>

      <div className="box pdfcard">
        <span className="pdf" aria-hidden>PDF</span>
        <div className="pdf-meta">
          {p.scope === "all" ? (
            <>
              <Dropdown menu={docMenu} trigger={["click"]}>
                <button className="t doc-switch">{t(`全部 PDF 的场景（${p.docs.length} 个 PDF）`, `Scenes of all PDFs (${p.docs.length})`)} <DownOutlined /></button>
              </Dropdown>
              <div className="m">{t(`共 ${scenes.length} 个场景`, `${scenes.length} scenes`)}</div>
            </>
          ) : (
            <>
              {p.docs.length > 1 ? (
                <Dropdown menu={docMenu} trigger={["click"]}>
                  <button className="t doc-switch" title={doc?.filename}>{doc?.filename} <DownOutlined /></button>
                </Dropdown>
              ) : (
                <div className="t" title={doc?.filename}>{doc?.filename ?? t("尚无文档", "No document")}</div>
              )}
              <div className="m">
                {doc ? (
                  <>
                    {t("导入于", "Imported")} {doc.imported_at.slice(0, 10)}<i>|</i>{sizeText(doc.size_bytes)}<i>|</i>{t(`${doc.page_count} 页`, `${doc.page_count} pages`)}
                    {doc.source_standard && <><i>|</i>{doc.source_standard}</>}
                  </>
                ) : (
                  t("导入规程 PDF 后开始核对需求", "Import a protocol PDF to start reviewing requirements")
                )}
              </div>
            </>
          )}
        </div>
        <Dropdown trigger={["click"]} disabled={!projectId} menu={actions}>
          <Button className="more" type="text" icon={<EllipsisOutlined />} aria-label={t("文档操作", "Document actions")} />
        </Dropdown>
      </div>

      <Tabs
        className="left-tabs"
        size="small"
        activeKey={p.tab}
        onChange={(k) => p.onTab(k as LeftTab)}
        items={[
          {
            key: "scenes",
            label: filtered ? t(`场景（${ordered.length}/${scenes.length}）`, `Scenes (${ordered.length}/${scenes.length})`) : t(`场景（${scenes.length}）`, `Scenes (${scenes.length})`),
            children: list,
          },
          {
            key: "facts",
            label: t("需求事实", "Requirement facts"),
            children: projectId && scene ? <FactsPanel projectId={projectId} scene={scene} onChanged={p.onSceneChanged} />
              : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("请选择场景", "Select a scene")} />,
          },
          {
            key: "doc",
            label: t("文档视图", "Document view"),
            children:
              projectId && scene?.pages ? (
                <div className="docview">
                  <img src={urls.page(projectId, scene.document_id, scene.pages[0], 800)} alt={t(`第 ${scene.pages[0]} 页`, `Page ${scene.pages[0]}`)} />
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("请选择场景", "Select a scene")} />
              ),
          },
        ]}
      />

      <Evidence projectId={projectId} scene={scene} />

      {projectId && (
        <ImportPdfDialog open={dialog === "import"} projectId={projectId} onClose={() => setDialog(null)} onImported={(ids) => p.onDocsChanged(ids[ids.length - 1])} />
      )}
      {projectId && doc && (
        <>
          <ExtractionDialog open={dialog === "extraction"} projectId={projectId} doc={doc} onClose={() => setDialog(null)}
            onReextracted={(ids) => p.onDocsChanged(ids[0])} />
          <BatchDialog open={dialog === "batch"} projectId={projectId} doc={doc} onClose={() => setDialog(null)} />
        </>
      )}
    </section>
  );
}

/** The cited clause on its source page; multi-clause and multi-page evidence can be stepped through. */
function Evidence({ projectId, scene }: { projectId: string | null; scene: Scene | null }) {
  const { t } = useT();
  const [clause, setClause] = useState(0);
  const [page, setPage] = useState<number | null>(null);
  const [viewer, setViewer] = useState(false);
  const key = scene ? `${keyOf(scene)}@${scene.revision}` : "";
  useEffect(() => {
    setClause(0);
    setPage(null);
  }, [key]);

  const evidence = scene?.evidence[clause] ?? scene?.evidence[0];
  const current = page ?? evidence?.page_start ?? null;
  const pages = evidence ? Array.from({ length: evidence.page_end - evidence.page_start + 1 }, (_, i) => evidence.page_start + i) : [];

  return (
    <div className="box evi">
      <div className="hd">
        <b>{t("所选原文证据", "Selected source evidence")}</b>
        {projectId && scene && current && (
          <span className="hd-links">
            <Tooltip title={t("放大阅读", "Enlarge page")}>
              <Button type="text" size="small" icon={<FullscreenOutlined />} onClick={() => setViewer(true)} aria-label={t("放大阅读", "Enlarge page")} />
            </Tooltip>
            <a href={urls.pdf(projectId, scene.document_id, current)} target="_blank" rel="noreferrer">
              {t("在文档中打开", "Open in document")} <ExportOutlined />
            </a>
          </span>
        )}
      </div>
      <div className="pg">
        {scene && scene.evidence.length > 1 ? (
          <Select size="small" value={clause} onChange={(v) => { setClause(v); setPage(null); }} popupMatchSelectWidth={false}
            options={scene.evidence.map((e, i) => ({ value: i, label: `${e.section_id} · ${e.page_start}–${e.page_end}` }))} />
        ) : (
          <>{t("页码", "Pages")} <b>{pagesText(scene?.pages ?? null)}</b></>
        )}
        {pages.length > 1 && (
          <Segmented size="small" value={current ?? undefined} onChange={(v) => setPage(v as number)} options={pages.map((n) => ({ value: n, label: `P${n}` }))} />
        )}
      </div>
      <div className="bd">
        {projectId && scene && current ? <img src={urls.page(projectId, scene.document_id, current, 260)} alt={t(`第 ${current} 页`, `Page ${current}`)} onClick={() => setViewer(true)} /> : <span className="page-empty" />}
        <div className="x">
          {scene && evidence ? (
            <>
              <b>
                <i>{evidence.section_id}</i>
                {scene.title}
              </b>
              <p className="src">{evidence.source_text || t("此条款没有保存原文文字，请对照原页。", "No text was kept for this clause; compare with the page.")}</p>
            </>
          ) : scene ? (
            <span className="muted">{t("此需求尚未关联原文证据。", "No source evidence is linked to this requirement.")}</span>
          ) : (
            <span className="muted">{t("选择场景后显示引用的原文。", "Select a scene to see the cited source text.")}</span>
          )}
        </div>
      </div>
      {projectId && scene && current && (
        <PageViewer open={viewer} onClose={() => setViewer(false)} projectId={projectId} documentId={scene.document_id} page={current} pages={pages} onPage={setPage} />
      )}
    </div>
  );
}
