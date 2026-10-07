import { useState } from "react";
import { Button, Empty, Input } from "antd";
import { FilePdfOutlined, RightOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import type { Library, PdfDocument } from "../api";
import { useT } from "../i18n";
import { ImportPdfDialog } from "./ImportPdfDialog";

interface Props {
  projectId: string | null;
  docs: PdfDocument[];
  library: Library | null;
  /** `from` is where the search box sits, so the results page can grow out of it. */
  onSearch: (text: string, from: DOMRect | null) => void;
  onOpenDoc: (documentId: string) => void;
  onImported: (documentIds: string[]) => void;
}

/** First screen: describe a scenario to search the library, or start the PDF requirement workflow. */
export function StartPage({ projectId, docs, library, onSearch, onOpenDoc, onImported }: Props) {
  const { t } = useT();
  const [text, setText] = useState("");
  const [importing, setImporting] = useState(false);
  const submit = () => {
    if (!text.trim()) return;
    onSearch(text.trim(), document.querySelector(".start-search")?.getBoundingClientRect() ?? null);
  };

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
          <Button size="large" type="primary" disabled={!text.trim() || !projectId} onClick={submit}>{t("检索", "Search")}</Button>
        </div>
        <div className="start-meta muted">
          {library ? t(`资产库共 ${library.asset_count} 个资产`, `${library.asset_count} assets in the library`) : t("正在连接资产库…", "Connecting to the library…")}
          <span className="dot" />
          {t("文本检索仅返回相似资产；条款级复用评估需从 PDF 开始。", "Text search returns similar assets only; clause-level reuse assessment starts from a PDF.")}
        </div>
      </div>

      <section className="start-pdfs">
        <div className="start-pdfs-head">
          <span className="sec-title">{t("PDF 需求工作流", "PDF requirement workflow")}</span>
          <Button icon={<UploadOutlined />} disabled={!projectId} onClick={() => setImporting(true)}>{t("导入 PDF", "Import PDF")}</Button>
        </div>
        {docs.length ? (
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
