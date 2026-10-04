import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Collapse, Input, Modal, Spin, Tabs, Tag } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { api, basename, urls, type Candidate, type DecisionReq, type Explanation, type ReviewItem, type StandardCheck } from "../api";
import { useT } from "../i18n";

/** Read-only stored files of the candidate version; edits are imported as a new version. */
type FileRef = Pick<Candidate, "asset_id" | "version_id" | "version_number" | "xosc" | "xodr">;

export function SourceFilesDialog({ cand, open, onClose }: { cand: FileRef; open: boolean; onClose: () => void }) {
  const { t } = useT();
  const [texts, setTexts] = useState<Record<string, string | null>>({});
  useEffect(() => {
    if (!open) return;
    setTexts({});
    (["scenario", "road"] as const).forEach((role) =>
      fetch(urls.file(cand, role)).then(async (r) => {
        const size = Number(r.headers.get("content-length") ?? 0);
        const body = size > 1_000_000 ? null : await r.text();
        setTexts((all) => ({ ...all, [role]: body !== null && body.length > 1_000_000 ? null : body }));
      }).catch(() => setTexts((all) => ({ ...all, [role]: null }))));
  }, [open, cand]);

  const tab = (role: "scenario" | "road", name: string) => (
    <div className="source-file">
      <Button size="small" icon={<DownloadOutlined />} href={urls.file(cand, role)} download={basename(name)}>{t(`下载 ${basename(name)}`, `Download ${basename(name)}`)}</Button>
      {!(role in texts) ? <div className="center-pad"><Spin /></div>
        : texts[role] === null ? <Alert type="info" showIcon title={t("文件较大，请下载查看。", "Download this large file to inspect it.")} />
        : <pre className="code-view">{texts[role]}</pre>}
    </div>
  );
  return (
    <Modal title={t("源文件", "Source files")} open={open} onCancel={onClose} footer={null} width={900}>
      <p className="muted">{cand.asset_id} · v{cand.version_number} · {cand.version_id} · {t("只读查看保存的版本。修改文件后，可在资产管理导入新版本。", "Read-only stored version. Import edited files in Asset management to create a new version.")}</p>
      <Tabs items={[{ key: "x", label: "OpenSCENARIO", children: tab("scenario", cand.xosc) }, { key: "r", label: "OpenDRIVE", children: tab("road", cand.xodr) }]} />
    </Modal>
  );
}

/** XSD structure checks per file, issues grouped by message with their line numbers. */
export function StandardChecksDialog({ cand, open, onClose }: { cand: Candidate; open: boolean; onClose: () => void }) {
  const { t } = useT();
  return (
    <Modal title={t("文件标准检查", "File standard checks")} open={open} onCancel={onClose} footer={null} width={720}>
      <StandardChecks checks={cand.standard_checks.checks ?? {}} />
    </Modal>
  );
}

/** Check status → [Chinese, English, verdict tag class]. */
export const CHECK_LABELS: Record<string, [string, string, string]> = {
  valid: ["通过", "Passed", "direct"], invalid: ["未通过", "Failed", "not"],
  unsupported: ["此版本未支持", "Version unsupported", "review"], unavailable: ["未完成检查", "Check unavailable", "review"],
};

export function StandardChecks({ checks }: { checks: Record<string, StandardCheck> }) {
  const { t } = useT();
  const labels = CHECK_LABELS;
  const missing = Object.values(checks).some((record) => record.detail === "No local XSD registry installed");
  return (
    <>
      <p className="muted">{t("按文件声明的版本检查 XML 结构；仿真可运行性需另行预览验证。", "Checks XML structure against the declared version. Verify execution separately with preview.")}</p>
      {missing && <Alert type="info" showIcon title={t("尚未安装文件标准规范。可在“工作区设置 › 文件标准”中下载安装。", "No schema registry is installed. Install one under Workspace settings › File standards.")} />}
      {Object.entries(checks).map(([role, record]) => {
        const grouped = new Map<string, (number | null | undefined)[]>();
        (record.issues ?? []).forEach((i) => grouped.set(i.message, [...(grouped.get(i.message) ?? []), i.line]));
        const count = [...grouped.values()].reduce((n, lines) => n + lines.length, 0);
        const [zh, en, cls] = labels[record.status] ?? labels.unavailable;
        return (
          <div key={role} className="check-block">
            <div className="sec-head">
              <span className="sec-title">{role === "scenario" ? "OpenSCENARIO" : "OpenDRIVE"} {record.version ?? ""}</span>
              <Tag className={`mtag ${cls}`}>{t(zh, en)}</Tag>
            </div>
            {record.detail && <p className="muted">{record.detail}</p>}
            {grouped.size > 0 && (
              <>
                <Alert type="warning" showIcon title={t(`发现 ${count} 处问题，归为 ${grouped.size} 类。请修复源文件后重新导入；也可先下载评估快照。`,
                  `${count} issues in ${grouped.size} groups. Fix the source files and reimport, or download an assessment snapshot.`)} />
                <Collapse size="small" ghost items={[{
                  key: "d",
                  label: t("原始诊断与行号", "Original diagnostics and line numbers"),
                  children: [...grouped.entries()].map(([msg, lines]) => (
                    <div key={msg} className="check-issue">
                      <div className="muted">{t("行 ", "Lines ")}{[...new Set(lines.filter((l) => l != null))].join(", ") || "—"}</div>
                      <pre className="json-view">{msg}</pre>
                    </div>
                  )),
                }]} />
              </>
            )}
          </div>
        );
      })}
    </>
  );
}

/** Evidence that would be cited, a structural explanation, or a model explanation that must cite it. */
export function ExplanationDialog({ request, open, onClose, onExplained }: {
  request: DecisionReq; open: boolean; onClose: () => void; onExplained: (id: string) => void;
}) {
  const { t } = useT();
  const [data, setData] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState<"structural" | "model" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasKey, setHasKey] = useState(false);
  const key = JSON.stringify(request);

  useEffect(() => {
    if (!open) return;
    setData(null);
    setError(null);
    api.explanation({ ...request, mode: "evidence" }).then(setData).catch((e: Error) => setError(e.message));
    api.settings().then((s) => setHasKey(s.model.has_key)).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, key]);

  const explain = async (mode: "structural" | "model") => {
    setBusy(mode);
    setError(null);
    try {
      const result = await api.explanation({ ...request, mode });
      setData(result);
      if (result.explanation_id) onExplained(result.explanation_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const blocked = !data || data.insufficient.length > 0;

  return (
    <Modal title={t("证据解释", "Evidence explanation")} open={open} onCancel={onClose} footer={null} width={720}>
      {!data && !error ? <div className="center-pad"><Spin /></div> : (
        <div className="settings-form">
          {data && (
            <>
              <div className="sec-title">{t("引用的证据", "Cited evidence")}</div>
              <ul className="evidence-list">
                {data.evidence.map((e) => <li key={e.evidence_id}><b>[{e.evidence_id}]</b> {e.location}</li>)}
              </ul>
              <Collapse size="small" ghost items={[{
                key: "payload",
                label: t("查看发送内容", "Review evidence payload"),
                children: <pre className="json-view">{JSON.stringify(data.evidence, null, 2)}</pre>,
              }]} />
              {data.insufficient.map((r, i) => <Alert key={i} type="warning" showIcon title={r} />)}
            </>
          )}
          {error && <Alert type="error" showIcon title={error} />}
          <div className="settings-actions">
            <Button loading={busy === "structural"} disabled={blocked} onClick={() => explain("structural")}>{t("结构依据", "Explain from structure")}</Button>
            <Button type="primary" loading={busy === "model"} disabled={blocked || !hasKey} onClick={() => explain("model")}>{t("发送证据并生成解释", "Send evidence to model")}</Button>
          </div>
          <p className="muted settings-note">
            {hasKey ? t("模型解释会把上面列出的 PDF 原文和资产事实发送到已配置的模型服务；结论由代码固定，模型不能改变。",
              "A model explanation sends the evidence listed above to the configured model service; the verdict is fixed by code and the model cannot change it.")
              : t("在设置中配置模型后才能生成模型解释。", "Configure a model in Settings to request a model explanation.")}
          </p>
          {data?.explanation && (
            <div className="explanation">
              <div className="sec-head">
                <span className="sec-title">{data.explanation.method === "structural" ? t("结构依据", "Structural explanation") : t("模型解释", "Model explanation")}</span>
                <span className="muted">{data.explanation.method}</span>
              </div>
              <ul>
                {data.explanation.observations.map((o, i) => <li key={i}>{o.text} <span className="muted">[{o.citations.join(", ")}]</span></li>)}
              </ul>
              <p className="muted">{t("这份解释会随本次评估一起导出和保存。", "This explanation is included when you export or save this assessment.")}</p>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/** Each open review item is confirmed with a reason; the reasons are saved with the decision. */
export function ReviewSignoffDialog({ cand, open, busy, describe, onClose, onConfirm }: {
  cand: Candidate; open: boolean; busy: boolean; describe: (item: ReviewItem) => string;
  onClose: () => void; onConfirm: (confirmations: { item: string; reason: string }[]) => void;
}) {
  const { t } = useT();
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!open) return;
    setChecked({});
    setReasons({});
  }, [open, cand]);
  const items = cand.review_items;
  const ready = items.length > 0 && items.every((item) => checked[item.id] && reasons[item.id]?.trim());
  return (
    <Modal title={t("逐项复核后保存", "Review each item, then save")} open={open} onCancel={onClose} width={680}
      okText={t("确认并保存决策", "Confirm and save decision")} cancelText={t("取消", "Cancel")}
      okButtonProps={{ disabled: !ready, loading: busy }}
      onOk={() => onConfirm(items.map((item) => ({ item: item.id, reason: reasons[item.id].trim() })))}>
      <p className="muted">{t("确认每一项已核对，并写明理由。复用结论不变，理由会写入追溯记录和报告。",
        "Confirm that you checked each item and give a reason. The verdict stays as assessed; the reasons are kept in the trace and report.")}</p>
      <ol className="signoff-list">
        {items.map((item) => (
          <li key={item.id}>
            <Checkbox checked={!!checked[item.id]} onChange={(e) => setChecked((all) => ({ ...all, [item.id]: e.target.checked }))}>
              {describe(item)}
            </Checkbox>
            <Input.TextArea value={reasons[item.id] ?? ""} maxLength={2000} autoSize={{ minRows: 1, maxRows: 4 }}
              placeholder={t("理由，例如：已对照原文与 XOSC 核对", "Reason, e.g. checked against the source and the XOSC")}
              aria-label={t("确认理由", "Reason")} onChange={(e) => setReasons((all) => ({ ...all, [item.id]: e.target.value }))} />
          </li>
        ))}
      </ol>
    </Modal>
  );
}
