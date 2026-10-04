import { useEffect, useState } from "react";
import { Alert, App, Button, Form, Input, Modal, Upload, type UploadFile } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { api, type Job } from "../api";
import { useT } from "../i18n";
import { useJob } from "../jobs";
import { JobProgress } from "./JobProgress";

interface Props {
  open: boolean;
  projectId: string;
  onClose: () => void;
  onImported: (documentIds: string[]) => void;
}

/** Upload protocol PDFs; extraction runs as a background job with live progress. */
export function ImportPdfDialog({ open, projectId, onClose, onImported }: Props) {
  const { t } = useT();
  const { message } = App.useApp();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [standard, setStandard] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initial, setInitial] = useState<Job | null>(null);
  const { job, setJob, cancel } = useJob(initial, (done) => {
    const ids = done.result.document_ids ?? [];
    if (ids.length) onImported(ids);
    if (done.status === "completed") message.success(t(`已导入 ${ids.length} 个 PDF`, `Imported ${ids.length} PDF(s)`));
  });

  // Reopening the dialog shows an extraction that is still running.
  useEffect(() => {
    if (!open) return;
    setError(null);
    api.jobs("pdf_import").then((all) => {
      const running = all.find((j) => j.status === "running");
      if (running) setInitial(running);
    }).catch(() => undefined);
  }, [open]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      setInitial(await api.importPdfs(projectId, files.map((f) => f.originFileObj as File), standard.trim()));
      setFiles([]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };
  const reset = () => {
    setInitial(null);
    setJob(null);
  };
  const running = job?.status === "running";

  return (
    <Modal
      title={t("导入 PDF", "Import PDFs")}
      open={open}
      onCancel={onClose}
      width={620}
      footer={
        job ? (
          <>
            {!running && <Button onClick={reset}>{t("继续导入", "Import more")}</Button>}
            <Button type="primary" onClick={onClose}>{running ? t("在后台继续", "Continue in background") : t("完成", "Done")}</Button>
          </>
        ) : (
          <>
            <Button onClick={onClose}>{t("取消", "Cancel")}</Button>
            <Button type="primary" disabled={!files.length} loading={starting} onClick={start}>{t("导入 PDF", "Import PDFs")}</Button>
          </>
        )
      }
    >
      {job ? (
        <JobProgress job={job} onCancel={cancel} unit={["个 PDF", "PDFs"]} />
      ) : (
        <Form layout="vertical">
          <Upload.Dragger
            accept=".pdf,application/pdf"
            multiple
            fileList={files}
            beforeUpload={() => false}
            onChange={({ fileList }) => setFiles(fileList.filter((f) => f.name.toLowerCase().endsWith(".pdf")))}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">{t("点击或拖入 PDF 文件", "Click or drop PDF files here")}</p>
            <p className="ant-upload-hint">{t("可一次选择多个文件", "Several files at once are fine")}</p>
          </Upload.Dragger>
          <Form.Item label={t("标准名称", "Standard name")} style={{ marginTop: 12 }} extra={t("例如 GB/T 或 Euro NCAP 规程名称，用于追溯。", "For example a GB/T or Euro NCAP protocol name, kept for traceability.")}>
            <Input value={standard} onChange={(e) => setStandard(e.target.value)} placeholder={t("可选", "Optional")} />
          </Form.Item>
          <Alert type="info" showIcon title={t("识别场景需求后，请对照原文证据复核再入库。导入时会向已配置的模型发送 PDF 文字。",
            "Scenes are extracted for you to review against the source before publishing. Import sends the PDF text to your configured model.")} />
          {error && <Alert type="error" showIcon title={error} style={{ marginTop: 10 }} />}
        </Form>
      )}
    </Modal>
  );
}
