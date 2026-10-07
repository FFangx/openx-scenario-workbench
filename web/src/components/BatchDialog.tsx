import { useEffect, useState } from "react";
import { Alert, App, Button, Modal, Select, Tabs } from "antd";
import { DownloadOutlined, SaveOutlined, SearchOutlined } from "@ant-design/icons";
import { api, urls, type PdfDocument, type Trace } from "../api";
import { useT } from "../i18n";
import { BatchCounts, BatchTable, encoderName } from "./BatchTable";
import { BindingPanel } from "./BindingPanel";

interface Props {
  open: boolean;
  projectId: string;
  /** Every PDF of the project; the person picks which to match together. */
  docs: PdfDocument[];
  /** The PDFs selected when the dialog opens. */
  initial: string[];
  onClose: () => void;
}

/** Match every scene of one or more PDFs against the current library in one table, then download or save the
 *  summary; and bind each scene to the assets that build its test, as the model suggests and a person confirms. */
export function BatchDialog({ open, projectId, docs, initial, onClose }: Props) {
  const { t, lang } = useT();
  const { message } = App.useApp();
  const [picked, setPicked] = useState<string[]>(initial);
  const [result, setResult] = useState<{ signature: string; trace: Trace } | null>(null);
  const [busy, setBusy] = useState<"match" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("match");
  const initialKey = initial.join("|");

  useEffect(() => {
    if (open) setPicked(initialKey ? initialKey.split("|") : []);
  }, [open, initialKey]);
  // The project's order, whatever order they were picked in.
  const selected = docs.filter((d) => picked.includes(d.document_id));
  const selectedKey = selected.map((d) => d.document_id).join("|");
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [open, selectedKey]);

  const scenes = selected.reduce((n, d) => n + d.scene_count, 0);
  const match = async () => {
    setBusy("match");
    setError(null);
    try {
      setResult(await api.batch(projectId, selected.map((d) => d.document_id)));
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
      await api.batchSave(projectId, result.signature);
      message.success(t("汇总已保存，候选资产版本已固定。可在总览中查看。", "Summary saved with pinned candidate asset versions. Find it in Overview."));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const matching = (
    <div className="settings-form">
      <p className="muted">
        {selected.length === 1
          ? t(`匹配 ${selected[0].filename} 的全部 ${scenes} 个场景，使用当前检索后端和资产库。`, `Match all ${scenes} scenes of ${selected[0].filename} using the current retrieval backend and asset library.`)
          : t(`匹配所选 ${selected.length} 份 PDF 的全部 ${scenes} 个场景，汇总在一张表里，使用当前检索后端和资产库。`, `Match all ${scenes} scenes of the ${selected.length} selected PDFs in one table, using the current retrieval backend and asset library.`)}
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
        <Button type={result ? "default" : "primary"} icon={<SearchOutlined />} loading={busy === "match"} disabled={!selected.length} onClick={match}>
          {result ? t("重新匹配", "Match again") : t("批量匹配", "Match all scenes")}
        </Button>
        {result && (
          <>
            <Button icon={<DownloadOutlined />} href={urls.batch(projectId, result.signature, "json", lang)}>{t("下载汇总 JSON", "Download summary JSON")}</Button>
            <Button icon={<DownloadOutlined />} href={urls.batch(projectId, result.signature, "html", lang)}>{t("下载汇总 HTML", "Download summary HTML")}</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={busy === "save"} onClick={save}>{t("保存汇总报告", "Save summary report")}</Button>
          </>
        )}
      </div>
    </div>
  );

  return (
    <Modal title={t("PDF 匹配与汇总", "Match PDFs and summarize")} open={open} onCancel={onClose} width={1040} footer={null}>
      {docs.length > 1 && (
        <div className="batch-docs">
          <span className="muted">{t("一起匹配的 PDF", "PDFs matched together")}</span>
          <Select mode="multiple" size="small" value={picked} onChange={setPicked} maxTagCount="responsive" aria-label={t("一起匹配的 PDF", "PDFs matched together")}
            options={docs.map((d) => ({ value: d.document_id, label: d.filename }))} placeholder={t("选择 PDF", "Select PDFs")} />
        </div>
      )}
      <Tabs className="batch-tabs" activeKey={tab} onChange={setTab} items={[
        { key: "match", label: t("匹配结论", "Reuse verdicts"), children: matching },
        { key: "bind", label: t("对应素材", "Bind assets"), children: <BindingPanel projectId={projectId} docs={selected} open={open && tab === "bind"} /> },
      ]} />
    </Modal>
  );
}
