import { Modal, Segmented, Spin } from "antd";
import { useState } from "react";
import { urls } from "../api";
import { useT } from "../i18n";

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: string;
  documentId: string;
  page: number;
  pages: number[];
  onPage: (n: number) => void;
}

/** The immutable source page at a legible width. Appearance never recolours the original PDF. */
export function PageViewer({ open, onClose, projectId, documentId, page, pages, onPage }: Props) {
  const { t } = useT();
  const [loaded, setLoaded] = useState<string | null>(null);
  const src = urls.page(projectId, documentId, page, 1400);
  return (
    <Modal open={open} onCancel={onClose} footer={null} width={940} title={t(`PDF 原文 · 第 ${page} 页 · 只读`, `Source PDF · page ${page} · read-only`)}>
      {pages.length > 1 && (
        <Segmented className="viewer-pages" value={page} onChange={(v) => onPage(v as number)} options={pages.map((n) => ({ value: n, label: `P${n}` }))} />
      )}
      <div className="viewer-page">
        {loaded !== src && <div className="center-pad"><Spin /></div>}
        <img src={src} alt={t(`第 ${page} 页`, `Page ${page}`)} onLoad={() => setLoaded(src)} style={loaded === src ? undefined : { display: "none" }} />
      </div>
    </Modal>
  );
}
