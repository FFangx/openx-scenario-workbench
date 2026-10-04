import { useEffect, useState } from "react";
import { Alert, App, Button, Modal } from "antd";
import { DownloadOutlined, SaveOutlined, SearchOutlined } from "@ant-design/icons";
import { api, urls, type PdfDocument, type Trace } from "../api";
import { useT } from "../i18n";
import { BatchCounts, BatchTable, encoderName } from "./BatchTable";

interface Props {
  open: boolean;
  projectId: string;
  doc: PdfDocument;
  onClose: () => void;
}

/** Match every scene of one PDF against the current library, then download or save the summary. */
export function BatchDialog({ open, projectId, doc, onClose }: Props) {
  const { t, lang } = useT();
  const { message } = App.useApp();
  const [result, setResult] = useState<{ signature: string; trace: Trace } | null>(null);
  const [busy, setBusy] = useState<"match" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResult(null);
    setError(null);
  }, [open, doc.document_id]);

  const match = async () => {
    setBusy("match");
    setError(null);
    try {
      setResult(await api.batch(projectId, doc.document_id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const save = async () => {
    if (!result) return;
    setBusy("save");
    setError(null);
    try {
      await api.batchSave(projectId, doc.document_id, result.signature);
      message.success(t("汇总已保存，候选资产版本已固定。可在总览中查看。", "Summary saved with pinned candidate asset versions. Find it in Overview."));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Modal title={t("整份 PDF 匹配与汇总", "Match entire PDF and summarize")} open={open} onCancel={onClose} width={860} footer={null}>
      <div className="settings-form">
        <p className="muted">
          {t(`匹配 ${doc.filename} 的全部 ${doc.scene_count} 个场景，使用当前检索后端和资产库。`, `Match all ${doc.scene_count} scenes of ${doc.filename} using the current retrieval backend and asset library.`)}
        </p>
        {error && <Alert type="error" showIcon title={error} />}
        {result && (
          <>
            <div className="sec-head">
              <span className="sec-title">{t(`共 ${result.trace.scene_count} 个场景`, `${result.trace.scene_count} scenes`)}</span>
              <span className="muted">{encoderName(result.trace.encoder, lang)}</span>
            </div>
            <BatchTable trace={result.trace} height={320} />
            <p className="muted ov-note"><BatchCounts trace={result.trace} /></p>
          </>
        )}
        <div className="settings-actions">
          <Button type={result ? "default" : "primary"} icon={<SearchOutlined />} loading={busy === "match"} onClick={match}>
            {result ? t("重新匹配", "Match again") : t("批量匹配", "Match all scenes")}
          </Button>
          {result && (
            <>
              <Button icon={<DownloadOutlined />} href={urls.batch(projectId, doc.document_id, result.signature, "json", lang)}>{t("下载汇总 JSON", "Download summary JSON")}</Button>
              <Button icon={<DownloadOutlined />} href={urls.batch(projectId, doc.document_id, result.signature, "html", lang)}>{t("下载汇总 HTML", "Download summary HTML")}</Button>
              <Button type="primary" icon={<SaveOutlined />} loading={busy === "save"} onClick={save}>{t("保存汇总报告", "Save summary report")}</Button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
