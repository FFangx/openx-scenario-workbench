import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Modal, Spin } from "antd";
import { DownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import { api, urls, type ExtractionRecord, type Job, type PdfDocument } from "../api";
import { useT } from "../i18n";
import { useJob } from "../jobs";
import { JobProgress } from "./JobProgress";

interface Props {
  open: boolean;
  projectId: string;
  doc: PdfDocument;
  onClose: () => void;
  onReextracted: (documentIds: string[]) => void;
}

/** What the extraction run recorded, its warnings, and a re-run when the extraction engine has changed. */
export function ExtractionDialog({ open, projectId, doc, onClose, onReextracted }: Props) {
  const { t } = useT();
  const [record, setRecord] = useState<ExtractionRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [initial, setInitial] = useState<Job | null>(null);
  const { job, cancel } = useJob(initial, (done) => done.result.document_ids?.length && onReextracted(done.result.document_ids));

  useEffect(() => {
    if (!open) return;
    setRecord(null);
    setError(null);
    setInitial(null);
    api.extraction(projectId, doc.document_id).then(setRecord).catch((e: Error) => setError(e.message));
  }, [open, projectId, doc.document_id]);

  const reextract = () => api.reextract(projectId, doc.document_id).then(setInitial).catch((e: Error) => setError(e.message));

  return (
    <Modal title={t("解析与校验记录", "Extraction and validation")} open={open} onCancel={onClose} footer={null} width={640}>
      {error && <Alert type="error" showIcon title={error} />}
      {!record ? !error && <div className="center-pad"><Spin /></div> : (
        <div className="settings-form">
          <Descriptions size="small" column={1} bordered items={[
            { key: "doc", label: "PDF", children: doc.filename },
            { key: "engine", label: t("识别引擎", "Extraction engine"), children: record.engine },
            { key: "model", label: t("使用模型", "Model"), children: record.model ?? t("未使用模型（规则提取）", "No model (rule-based extraction)") },
            { key: "scenes", label: t("场景数", "Scenes"), children: doc.scene_count },
          ]} />
          {record.outdated && (
            <Alert type="info" showIcon title={t(`识别引擎已更新为 ${record.current_engine}。重新识别会按当前引擎和模型设置生成一份新的文档记录，原记录保留。`,
              `The extraction engine is now ${record.current_engine}. Extracting again creates a new document record with the current engine and model settings; the old one is kept.`)} />
          )}
          {record.ocr && <Alert type="warning" showIcon title={t("扫描页已在本机识别；请对照原文复核文字与表格。", "Scanned pages were recognized locally. Review text and tables against the source.")} />}
          {[...record.issues, ...record.flags].map((issue, i) => <Alert key={i} type="warning" showIcon title={issue} />)}
          {record.has_record && !doc.scene_count && (
            <Alert type="info" showIcon title={t("模型已完成提取，此文档没有识别到场景。可下载解析记录核查。", "Extraction completed with no scenes. Download the record to inspect the result.")} />
          )}
          {job && <JobProgress job={job} onCancel={cancel} unit={["个 PDF", "PDFs"]} />}
          <div className="settings-actions">
            {record.has_record && (
              <Button icon={<DownloadOutlined />} href={urls.extraction(projectId, doc.document_id)}>{t("下载解析记录", "Download extraction record")}</Button>
            )}
            {record.outdated && (
              <Button icon={<ReloadOutlined />} onClick={reextract} disabled={job?.status === "running"}>{t("重新识别场景", "Extract scenes again")}</Button>
            )}
          </div>
          {record.outdated && <p className="muted settings-note">{t("重新识别会向已配置的模型发送 PDF 文字。", "Extracting again sends the PDF text to your configured model.")}</p>}
        </div>
      )}
    </Modal>
  );
}
