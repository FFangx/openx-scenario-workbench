import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Popconfirm, Space, Table, Tag } from "antd";
import { CloudDownloadOutlined, RollbackOutlined, SwapOutlined, SyncOutlined } from "@ant-design/icons";
import { api, type SchemaCheck, type SchemaStatus, type SchemaVerdictChange } from "../api";
import { useT } from "../i18n";
import { useJob } from "../jobs";
import { CHECK_LABELS } from "./AssessmentDialogs";
import { JobProgress } from "./JobProgress";

const short = (revision: string) => revision.slice(0, 7);
const day = (iso?: string | null) => (iso ? iso.slice(0, 10) : "");
const moment = (iso: string) => iso.replace("T", " ").slice(0, 16);

/** "OpenSCENARIO:1.0", "OpenSCENARIO:1.1" … → "OpenSCENARIO 1.0 / 1.1 · OpenDRIVE …" */
function versionList(keys: string[]) {
  const grouped = new Map<string, string[]>();
  keys.forEach((key) => {
    const [standard, version] = key.split(":");
    grouped.set(standard, [...(grouped.get(standard) ?? []), version]);
  });
  return [...grouped.entries()].map(([standard, versions]) => `${standard} ${versions.join(" / ")}`).join(" · ");
}

/** Manual updates of the XSD registry: check esmini, stage and preview the library impact, switch, roll back. */
export function SchemaTab() {
  const { t } = useT();
  const [status, setStatus] = useState<SchemaStatus | null>(null);
  const [check, setCheck] = useState<SchemaCheck | null>(null);
  const [busy, setBusy] = useState<"check" | "preview" | "apply" | "rollback" | "discard" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => api.schemaStatus().then(setStatus).catch((e: Error) => setError(e.message)), []);
  useEffect(() => { reload(); }, [reload]);
  const { job, setJob, cancel } = useJob(status?.job ?? null, () => reload());

  const act = async <T,>(kind: NonNullable<typeof busy>, work: () => Promise<T>, done: (r: T) => void) => {
    setBusy(kind);
    setError(null);
    try {
      done(await work());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (!status) return error ? <Alert type="error" showIcon title={error} /> : null;
  const { active, previous, staged } = status;
  const preview = staged?.preview;
  const running = job?.status === "running";

  return (
    <div className="settings-form">
      <p className="muted">{t("文件标准检查使用 esmini 收录的 ASAM 官方 XSD，按文件声明的版本逐一检查。平时检查完全离线。",
        "Standard checks use the ASAM XSDs mirrored by esmini, matched to each file's declared version. Checking runs offline.")}</p>

      <h4 className="settings-h">{t("当前规范", "Installed schemas")}</h4>
      {active ? (
        <Alert type="success" showIcon title={t(`已安装 esmini ${short(active.revision)}`, `esmini ${short(active.revision)} installed`)}
          description={<>
            <div>{versionList(active.versions)}</div>
            <div className="muted">{t("安装于 ", "Installed ")}{moment(active.installed_at)}
              {active.commit_date ? t(` · 提交日期 ${day(active.commit_date)}`, ` · committed ${day(active.commit_date)}`) : ""}</div>
            {Object.keys(active.skipped).length > 0 && (
              <div className="muted">{t("未收录：", "Left out: ")}{Object.keys(active.skipped).join("、")}</div>
            )}
          </>} />
      ) : (
        <Alert type="warning" showIcon title={t("尚未安装文件标准规范，标准检查无法进行。", "No schema registry is installed, so standard checks cannot run.")} />
      )}

      <div className="settings-actions">
        <Button icon={<SyncOutlined />} loading={busy === "check"} disabled={running}
          onClick={() => act("check", api.schemaCheck, setCheck)}>{t("检查更新", "Check for updates")}</Button>
        {previous && (
          <Popconfirm title={t(`回退到 esmini ${short(previous.revision)}？当前规范会保留为可回退版本。`,
            `Roll back to esmini ${short(previous.revision)}? The current registry is kept for rolling forward.`)}
            okText={t("回退", "Roll back")} cancelText={t("取消", "Cancel")}
            onConfirm={() => act("rollback", api.schemaRollback, setStatus)}>
            <Button type="text" icon={<RollbackOutlined />} loading={busy === "rollback"} disabled={running}>
              {t(`回退到 ${short(previous.revision)}`, `Roll back to ${short(previous.revision)}`)}
            </Button>
          </Popconfirm>
        )}
      </div>
      <p className="muted settings-note">{t("检查更新会访问 GitHub 上的 esmini 仓库；下载的新规范先单独存放，确认后才启用。",
        "Checking contacts the esmini repository on GitHub. A new registry is kept aside until you switch to it.")}</p>

      {error && <Alert type="error" showIcon title={error} />}
      {check && <CheckResult check={check} busy={busy === "preview"} disabled={running}
        onPreview={() => act("preview", () => api.schemaPreview(check.revision), (j) => { setJob(j); setCheck(null); })} />}

      {job && (running || job.status === "failed" || job.status === "stopped") && (
        <JobProgress job={job} onCancel={cancel} unit={["个素材", "assets"]} />
      )}

      {staged && !preview && !running && (
        <Alert type="info" showIcon title={t("上次预览没有完成。", "The last preview did not finish.")}
          action={<Button size="small" loading={busy === "discard"} onClick={() => act("discard", api.schemaDiscard, setStatus)}>{t("清除", "Clear")}</Button>} />
      )}

      {staged && preview && !running && (
        <>
          <h4 className="settings-h">{t("预览结果（尚未启用）", "Preview (not yet in use)")}</h4>
          <p className="muted">
            {t(`esmini ${short(staged.revision)}（${day(preview.date)}）· ${preview.message}`, `esmini ${short(staged.revision)} (${day(preview.date)}) · ${preview.message}`)}
            <br />{versionList(staged.versions)}
          </p>
          {preview.changes.length === 0 ? (
            <Alert type="success" showIcon title={t(`已对比 ${preview.compared} 个素材，检查结论都不变。`, `${preview.compared} assets compared; no verdict changes.`)} />
          ) : (
            <>
              <Alert type="warning" showIcon title={t(`已对比 ${preview.compared} 个素材，有 ${preview.changes.length} 项检查结论会改变。`,
                `${preview.compared} assets compared; ${preview.changes.length} verdicts would change.`)} />
              <ChangeTable changes={preview.changes} />
            </>
          )}
          <div className="settings-actions">
            <Popconfirm title={preview.changes.length
              ? t("切换后，以上素材的标准检查结论会立即按新规范更新。继续？", "After switching, the verdicts above update at once. Continue?")
              : t("切换到新规范？", "Switch to the new registry?")}
              okText={t("切换", "Switch")} cancelText={t("取消", "Cancel")}
              onConfirm={() => act("apply", () => api.schemaApply(staged.revision), setStatus)}>
              <Button type="primary" icon={<SwapOutlined />} loading={busy === "apply"}>{t("切换到新规范", "Switch to new registry")}</Button>
            </Popconfirm>
            <Button type="text" loading={busy === "discard"} onClick={() => act("discard", api.schemaDiscard, setStatus)}>{t("放弃", "Discard")}</Button>
          </div>
          <p className="muted settings-note">{t("已保存的报告仍记录当时使用的规范版本。", "Saved reports keep the registry revision they were checked with.")}</p>
        </>
      )}
    </div>
  );
}

function CheckResult({ check, busy, disabled, onPreview }: { check: SchemaCheck; busy: boolean; disabled: boolean; onPreview: () => void }) {
  const { t } = useT();
  const unmapped = Object.keys(check.unmapped);
  if (check.up_to_date) {
    return <Alert type="success" showIcon title={t(`已是最新：与 esmini 最近一次规范更新 ${short(check.revision)}（${day(check.date)}）一致。`,
      `Up to date with esmini's latest schema change ${short(check.revision)} (${day(check.date)}).`)} />;
  }
  const facts = [
    check.new_versions.length > 0 && t(`新增版本：${versionList(check.new_versions)}`, `New versions: ${versionList(check.new_versions)}`),
    check.dropped_versions.length > 0 && t(`不再提供：${versionList(check.dropped_versions)}`, `No longer provided: ${versionList(check.dropped_versions)}`),
    check.changed.length > 0 && t(`${check.changed.length} 个文件有修改`, `${check.changed.length} files changed`),
    check.added.length > 0 && t(`${check.added.length} 个新文件`, `${check.added.length} new files`),
    check.removed.length > 0 && t(`${check.removed.length} 个文件被移除`, `${check.removed.length} files removed`),
  ].filter(Boolean);
  return (
    <Alert type="info" showIcon
      title={check.installed
        ? t(`有新的规范：esmini ${short(check.revision)}（${day(check.date)}）`, `Update available: esmini ${short(check.revision)} (${day(check.date)})`)
        : t(`可安装 esmini ${short(check.revision)}（${day(check.date)}）`, `esmini ${short(check.revision)} (${day(check.date)}) can be installed`)}
      description={<>
        <div className="muted">{check.message}</div>
        {facts.length > 0 && <div>{facts.join(" · ")}</div>}
        {unmapped.length > 0 && <div>{t(`无法自动识别入口文件，暂不收录：${unmapped.join("、")}`, `Entry schema unclear, left out: ${unmapped.join(", ")}`)}</div>}
        <Space className="settings-result">
          <Button type="primary" icon={<CloudDownloadOutlined />} loading={busy} disabled={disabled} onClick={onPreview}>
            {t("下载并预览影响", "Download and preview impact")}
          </Button>
        </Space>
      </>} />
  );
}

function ChangeTable({ changes }: { changes: SchemaVerdictChange[] }) {
  const { t } = useT();
  const verdict = (v: SchemaVerdictChange["before"]) => {
    const [zh, en, cls] = CHECK_LABELS[v.status] ?? CHECK_LABELS.unavailable;
    return <Tag className={`mtag ${cls}`}>{t(zh, en)}{v.issues ? ` · ${v.issues}` : ""}</Tag>;
  };
  return (
    <Table size="small" pagination={changes.length > 8 ? { pageSize: 8, size: "small" } : false}
      rowKey={(c) => `${c.asset_id}:${c.version_id}:${c.role}`} dataSource={changes}
      columns={[
        { title: t("素材", "Asset"), dataIndex: "title", ellipsis: true },
        { title: t("文件", "File"), key: "file", width: 150,
          render: (_, c) => `${c.standard ?? (c.role === "scenario" ? "OpenSCENARIO" : "OpenDRIVE")} ${c.version ?? ""}` },
        { title: t("现在", "Now"), key: "before", width: 120, render: (_, c) => verdict(c.before) },
        { title: t("切换后", "After"), key: "after", width: 120, render: (_, c) => verdict(c.after) },
      ]} />
  );
}
