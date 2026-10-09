import { useState } from "react";
import { Button, Empty, Input, Tooltip } from "antd";
import { FilePdfOutlined, LoadingOutlined, PlusOutlined, RightOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import type { Library, LibraryStatus, PdfDocument } from "../api";
import { useT } from "../i18n";
import { ImportPdfDialog } from "./ImportPdfDialog";

interface Props {
  projectId: string | null;
  /** The project list has arrived: no `projectId` then means there is no project. */
  projectsLoaded: boolean;
  docs: PdfDocument[];
  /** The project's PDFs are still on the way. */
  docsLoading: boolean;
  library: Library | null;
  /** How far the library and the search model are loaded, while the service starts. */
  status: LibraryStatus | null;
  /** `from` is where the search box sits, so the results page can grow out of it. */
  onSearch: (text: string, from: DOMRect | null) => void;
  onOpenDoc: (documentId: string) => void;
  onImported: (documentIds: string[]) => void;
  onNewProject: () => void;
}

/** First screen: describe a scenario to search the library, or start the PDF requirement workflow. */
export function StartPage({ projectId, projectsLoaded, docs, docsLoading, library, status, onSearch, onOpenDoc, onImported, onNewProject }: Props) {
  const { t } = useT();
  const [text, setText] = useState("");
  const [importing, setImporting] = useState(false);
  const modelLoading = status?.encoder.state === "loading";
  const ready = !!library && !modelLoading;
  const submit = () => {
    if (!text.trim() || !ready || !projectId) return;
    onSearch(text.trim(), document.querySelector(".start-search")?.getBoundingClientRect() ?? null);
  };
  const waiting = !library ? t("资产库准备好后即可检索", "Search opens once the library is ready")
    : modelLoading ? t("检索模型加载好后即可检索", "Search opens once the search model has loaded") : null;

  return (
    <main className="start">
      <div className="start-hero">
        <h1>{t("从需求找到可复用的仿真场景", "Find reusable simulation scenarios for a requirement")}</h1>
        <p className="muted">
          {t("用一句话描述场景检索资产库，或导入测试规程 PDF：模型为每个条款推荐可复用素材，经人工确认形成复用评估。",
            "Describe a scenario to search the library, or import a test protocol PDF: the model recommends reusable assets for every clause, and your confirmation makes the reuse assessment.")}
        </p>
        <div className="start-search">
          <Input size="large" allowClear value={text} onChange={(e) => setText(e.target.value)} onPressEnter={submit}
            prefix={<SearchOutlined />} aria-label={t("描述场景", "Describe a scenario")}
            placeholder={t("例如：夜间行人从右侧横穿，主车 40 km/h", "e.g. a pedestrian crossing from the right at night, ego at 40 km/h")} />
          <Tooltip title={waiting}>
            <Button size="large" type="primary" disabled={!text.trim() || !projectId || !ready} onClick={submit}>{t("检索", "Search")}</Button>
          </Tooltip>
        </div>
        <div className="start-meta muted">
          <LibraryLine library={library} status={status} />
          <span className="dot" />
          {t("文本检索仅返回相似资产；条款级复用评估需从 PDF 开始。", "Text search returns similar assets only; clause-level reuse assessment starts from a PDF.")}
        </div>
      </div>

      <section className="start-pdfs">
        <div className="start-pdfs-head">
          <span className="sec-title">{t("PDF 需求工作流", "PDF requirement workflow")}</span>
          <Button icon={<UploadOutlined />} disabled={!projectId} onClick={() => setImporting(true)}>{t("导入 PDF", "Import PDF")}</Button>
        </div>
        {docsLoading ? (
          <div className="start-docs" aria-busy="true" aria-label={t("正在加载项目的 PDF", "Loading the project's PDFs")}>
            {[0, 1].map((i) => (
              <div key={i} className="start-skel" style={{ "--i": i } as React.CSSProperties}><i /><span><i /><i /></span></div>
            ))}
          </div>
        ) : docs.length ? (
          <div className="start-docs">
            {docs.map((d, i) => (
              <button key={d.document_id} className="start-doc" style={{ "--i": i } as React.CSSProperties} onClick={() => onOpenDoc(d.document_id)}>
                <FilePdfOutlined className="pdf-ic" />
                <span className="txt">
                  <b title={d.filename}>{d.filename}</b>
                  <span className="muted">{t(`${d.scene_count} 个场景 · 导入于 ${d.imported_at.slice(0, 10)}`, `${d.scene_count} scenes · imported ${d.imported_at.slice(0, 10)}`)}</span>
                </span>
                <RightOutlined className="go" />
              </button>
            ))}
          </div>
        ) : projectsLoaded && !projectId ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("还没有项目。项目是本机上的一个文件夹，新建后即可导入 PDF。",
            "No project yet. A project is a folder on this computer; create one to import PDFs.")}>
            <Button type="primary" icon={<PlusOutlined />} onClick={onNewProject}>{t("新建项目", "New project")}</Button>
          </Empty>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("当前项目还没有 PDF。导入后会提取其中的测试场景。", "No PDFs in this project yet. Importing one extracts its test scenarios.")} />
        )}
      </section>
      {projectId && (
        <ImportPdfDialog open={importing} projectId={projectId} onClose={() => setImporting(false)}
          onImported={(ids) => { setImporting(false); onImported(ids); }} />
      )}
    </main>
  );
}

/** The library's size once loaded; while the service starts, what it is loading and how far it is. */
function LibraryLine({ library, status }: { library: Library | null; status: LibraryStatus | null }) {
  const { t } = useT();
  const catalog = status?.catalog;
  if (library) {
    const count = t(`资产库共 ${library.asset_count} 个资产`, `${library.asset_count} assets in the library`);
    if (status?.encoder.state !== "loading") return <span>{count}</span>;
    return <span className="start-load">{count} · <LoadingOutlined /> {t("正在加载检索模型…", "Loading the search model…")}</span>;
  }
  if (catalog?.state === "failed") return <span className="start-load failed">{t(`资产库加载失败：${catalog.error}`, `The library failed to load: ${catalog.error}`)}</span>;
  const counted = catalog?.state === "loading" && catalog.total > 0 && catalog.stage !== "checking";
  const text = catalog?.state !== "loading" ? t("正在连接资产库…", "Connecting to the library…")
    : catalog.stage === "checking" ? t(`正在检查 ${catalog.total} 个资产的文件标准…`, `Checking the file standards of ${catalog.total} assets…`)
      : catalog.stage === "parsing" ? t(`正在解析有变化的资产 ${catalog.done} / ${catalog.total}`, `Parsing changed assets ${catalog.done} / ${catalog.total}`)
        : t(`正在读取资产库 ${catalog.done} / ${catalog.total}`, `Reading the library ${catalog.done} / ${catalog.total}`);
  return (
    <span className="start-load" role="status">
      <span className={`start-bar${counted ? "" : " busy"}`} aria-hidden>
        <i style={counted ? { width: `${Math.round((100 * catalog.done) / catalog.total)}%` } : undefined} />
      </span>
      {text}
    </span>
  );
}
