import { useEffect, useState } from "react";
import { Alert, Button, Modal, Radio, Upload, type UploadFile } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { api, type Job } from "../api";
import { useT } from "../i18n";
import { useJob } from "../jobs";
import { JobProgress } from "./JobProgress";

const SUFFIXES = [".sim", ".xosc", ".xodr", ".zip"];

/** Per-source outcome of an import: pairable cases and missing road references. */
export function ImportReports({ job }: { job: Job }) {
  const { t } = useT();
  const reports = job.reports ?? [];
  const cases = reports.reduce((n, r) => n + r.case_count, 0);
  const skipped = Math.max(0, cases - reports.reduce((n, r) => n + r.imported_count, 0));
  const missing = reports.flatMap((r) => r.missing_road_references);
  const roadMissing = reports.reduce((n, r) => n + (r.road_missing_count ?? 0), 0);
  return (
    <>
      <div className="muted job-note">
        {t(`已保存 / 复用 ${job.saved ?? 0} 个场景`, `${job.saved ?? 0} scenarios saved / reused`)}
        {cases > 0 && t(` · 来源 ${cases} 个场景 · 跳过 ${skipped}`, ` · ${cases} source cases · ${skipped} skipped`)}
        {(job.failed ?? 0) > 0 && t(` · ${job.failed} 个未能生成标签`, ` · ${job.failed} without labels`)}
      </div>
      {reports.map((r) => (
        <div key={r.source_name} className="muted job-note">
          {t(`${r.source_name}：${r.imported_count}/${r.case_count} 个场景可配对`, `${r.source_name}: ${r.imported_count}/${r.case_count} pairable cases`)}
        </div>
      ))}
      {skipped > 0 && (
        <Alert type="warning" showIcon title={t(`部分场景未入库：跳过 ${skipped} 个场景。`, `Partial import: ${skipped} cases skipped.`)} />
      )}
      {missing.length > 0 && (
        <Alert type="info" showIcon title={t(`${roadMissing} 个场景引用了包内没有的道路（仿真软件内置道路）：已入库并可参与匹配，道路类型由地图名推断，但无法预览。补充以下 XODR 文件后重新导入即可预览。`,
          `${roadMissing} cases reference roads not in the package (simulator built-in roads): imported and matchable, with the road type inferred from the map name, but not previewable. Add these XODR files and reimport to preview them.`)}
          description={<pre className="json-view">{missing.join("\n")}</pre>} />
      )}
    </>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  onFinished: () => void;
}

export function ImportAssetsDialog({ open, onClose, onFinished }: Props) {
  const { t } = useT();
  const [source, setSource] = useState<"upload" | "demo">("upload");
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [sent, setSent] = useState<File[] | null>(null);
  const [initial, setInitial] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { job, setJob, cancel } = useJob(initial, onFinished);

  useEffect(() => {
    if (!open) return;
    setError(null);
    api.jobs("asset_import").then((all) => {
      const running = all.find((j) => j.status === "running");
      if (running) setInitial(running);
    }).catch(() => undefined);
  }, [open]);

  const start = async (retry?: File[]) => {
    setStarting(true);
    setError(null);
    try {
      if (!retry && source === "demo") {
        setSent(null);
        setInitial(await api.importDemo());
      } else {
        const request = retry ?? files.map((f) => f.originFileObj as File);
        setSent(request);
        setInitial(await api.importAssets(request));
        setFiles([]);
      }
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
  const retryable = job && ["failed", "stopped", "interrupted"].includes(job.status) && sent;

  return (
    <Modal
      title={t("导入资产", "Import assets")}
      open={open}
      onCancel={onClose}
      width={640}
      footer={job ? (
        <>
          {retryable && <Button loading={starting} onClick={() => start(sent!)}>{t("重试导入", "Retry import")}</Button>}
          {!running && <Button onClick={reset}>{t("继续导入", "Import more")}</Button>}
          <Button type="primary" onClick={onClose}>{running ? t("在后台继续", "Continue in background") : t("完成", "Done")}</Button>
        </>
      ) : (
        <>
          <Button onClick={onClose}>{t("取消", "Cancel")}</Button>
          <Button type="primary" loading={starting} disabled={source === "upload" && !files.length} onClick={() => start()}>
            {source === "demo" ? t("下载并导入示例", "Download and import example") : t("开始导入", "Start import")}
          </Button>
        </>
      )}
    >
      {job ? (
        <div className="settings-form">
          <JobProgress job={job} onCancel={cancel} unit={["个场景", "scenarios"]} />
          <ImportReports job={job} />
          {job.status === "completed" && !(job.failed || job.error) && (
            <div className="muted job-note">{t("可配对资产已入库，可立即使用。", "Pairable assets are saved and ready to use.")}</div>
          )}
        </div>
      ) : (
        <div className="settings-form">
          <Radio.Group optionType="button" value={source} onChange={(e) => setSource(e.target.value)}
            options={[{ value: "upload", label: t("上传文件", "Upload files") }, { value: "demo", label: t("公开 esmini 示例", "Public esmini example") }]} />
          {source === "demo" ? (
            <Alert type="info" showIcon title={t("会从 esmini 的公开仓库下载 cut-in 示例（MPL-2.0）并导入。", "Downloads the cut-in example from the public esmini repository (MPL-2.0) and imports it.")} />
          ) : (
            <>
              <Upload.Dragger
                accept={SUFFIXES.join(",")}
                multiple
                fileList={files}
                beforeUpload={() => false}
                onChange={({ fileList }) => setFiles(fileList.filter((f) => SUFFIXES.some((s) => f.name.toLowerCase().endsWith(s))))}
              >
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p className="ant-upload-text">{t("点击或拖入 .sim、.xosc、.xodr 或 .zip 文件", "Click or drop .sim, .xosc, .xodr or .zip files")}</p>
                <p className="ant-upload-hint">{t("XOSC 需与其引用的 XODR 一起导入；ZIP 可包含目录、模型及纹理，并保留相对路径。",
                  "Import each XOSC with the XODR it references; ZIP packages may include catalogs, models and textures with relative paths.")}</p>
              </Upload.Dragger>
              <p className="muted settings-note">{t("入库时按规则从文件生成功能、道路和目标标签。重复内容不会产生新版本。",
                "On import, rules read the function, road and target labels from the files. Identical content does not create a new version.")}</p>
            </>
          )}
          {error && <Alert type="error" showIcon title={error} />}
        </div>
      )}
    </Modal>
  );
}
