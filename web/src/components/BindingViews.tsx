import { useEffect, useState } from "react";
import { Alert, Collapse, Empty, Progress, Spin, Table, Tag, Tooltip, type TableColumnsType } from "antd";
import { api, type AssetBinding, type BindingCoverage, type BindingStatus } from "../api";
import { dateTime, useT } from "../i18n";

export const BINDING_STATUS: Record<BindingStatus | "unconfirmed", { zh: string; en: string; cls: string }> = {
  same: { zh: "直接用", en: "Use as is", cls: "direct" },
  modify: { zh: "要改", en: "Change first", cls: "modify" },
  none: { zh: "没有素材", en: "No asset", cls: "not" },
  unconfirmed: { zh: "未确认", en: "Not confirmed", cls: "not" },
};

export const StatusTag = ({ status }: { status: BindingStatus | "unconfirmed" }) => {
  const { lang } = useT();
  return <Tag className={`mtag ${BINDING_STATUS[status].cls}`}>{BINDING_STATUS[status][lang]}</Tag>;
};

/** The requirement clauses bound to any version of one asset, across projects. */
export function AssetClauses({ assetId, onOpen, onCount }: { assetId: string; onOpen?: (pid: string, did: string, sid: string) => void; onCount?: (n: number) => void }) {
  const { t } = useT();
  const [rows, setRows] = useState<AssetBinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setRows(null);
    api.assetBindings(assetId).then((r) => { setRows(r); onCount?.(r.length); }).catch((e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId]);

  const columns: TableColumnsType<AssetBinding> = [
    {
      title: t("需求条款", "Clause"), key: "c", ellipsis: true,
      render: (_, r) => <span title={r.title ?? ""}>{r.section_id && <span className="muted">{r.section_id} </span>}{r.title}</span>,
    },
    { title: t("文档", "Document"), dataIndex: "filename", ellipsis: true, width: "26%" },
    {
      title: t("对应表", "Binding"), key: "s", width: 150,
      render: (_, r) => (
        <span className="bind-status">
          <Tooltip title={r.changes || undefined}><span><StatusTag status={r.status} /></span></Tooltip>
          {r.preferred && r.group_size > 1 && <Tag className="mtag review">{t("首选", "Preferred")}</Tag>}
          {r.stale.length > 0 && <Tag className="mtag review">{t("待重核", "Recheck")}</Tag>}
        </span>
      ),
    },
    {
      title: t("绑定版本", "Bound version"), key: "v", width: 104,
      render: (_, r) => <>v{r.version_number}{!r.latest && <span className="muted">{t("（旧）", " (older)")}</span>}</>,
    },
    { title: t("确认时间", "Confirmed"), dataIndex: "confirmed_at", width: 132, render: dateTime },
  ];
  if (error) return <Alert type="error" showIcon title={error} />;
  if (!rows) return <div className="center-pad"><Spin /></div>;
  if (!rows.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("还没有需求条款绑定这个素材。在“整份 PDF 匹配”的“对应素材”里确认绑定。",
      "No requirement clause is bound to this asset yet. Confirm bindings under Bind assets in Match entire PDF.")} />;
  }
  return (
    <Table<AssetBinding> className={`ov-table${onOpen ? " bind-clauses" : ""}`} size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} tableLayout="fixed"
      onRow={(r) => (onOpen ? { onClick: () => r.project_id && r.document_id && r.scene_id && onOpen(r.project_id, r.document_id, r.scene_id),
        title: t("打开需求场景", "Open the requirement scene") } : {})} />
  );
}

/** Per PDF of the project: clauses with assets, without, and not confirmed yet; and the assets no clause uses. */
export function Coverage({ projectId, onOpenScene }: { projectId: string; onOpenScene: (d: string, s: string) => void }) {
  const { t } = useT();
  const [coverage, setCoverage] = useState<BindingCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setCoverage(null);
    api.coverage(projectId).then(setCoverage).catch((e: Error) => setError(e.message));
  }, [projectId]);

  if (error) return <Alert type="error" showIcon title={error} />;
  if (!coverage) return <div className="center-pad"><Spin /></div>;
  if (!coverage.documents.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("项目里还没有 PDF。", "The project has no PDFs yet.")} />;
  type Scene = BindingCoverage["documents"][number]["scenes"][number];
  const sceneColumns: TableColumnsType<Scene> = [
    { title: t("对应表", "Binding"), key: "s", width: 150, render: (_, r) => <span className="bind-status"><StatusTag status={r.status} />{r.stale && <Tag className="mtag review">{t("待重核", "Recheck")}</Tag>}</span> },
    { title: t("需求条款", "Clause"), key: "c", ellipsis: true, render: (_, r) => <span title={r.title}>{r.section_id && <span className="muted">{r.section_id} </span>}{r.title}</span> },
    { title: t("素材（首选在前）", "Assets (preferred first)"), key: "a", ellipsis: true, render: (_, r) => r.assets.join(" · ") || <span className="muted">—</span> },
  ];

  return (
    <div className="settings-form coverage-list">
      {coverage.documents.map((d) => {
        const total = d.scenes.length;
        const covered = d.same + d.modify;
        return (
          <Collapse key={d.document_id} size="small" items={[{
            key: d.document_id,
            label: (
              <div className="cov-head">
                <b title={d.filename}>{d.filename}</b>
                <Progress percent={total ? Math.round(((total - d.unconfirmed) / total) * 100) : 0} size="small" showInfo={false} />
                <span className="muted">
                  {t(`${total} 条 · 有素材 ${covered} · 没有素材 ${d.none} · 未确认 ${d.unconfirmed}`, `${total} clauses · ${covered} with assets · ${d.none} with none · ${d.unconfirmed} not confirmed`)}
                  {d.stale > 0 && t(` · 待重核 ${d.stale}`, ` · ${d.stale} to recheck`)}
                </span>
              </div>
            ),
            children: <Table<Scene> className="ov-table ov-reports" size="small" rowKey="scene_id" columns={sceneColumns} dataSource={d.scenes} pagination={false} tableLayout="fixed"
              scroll={{ y: 260 }} onRow={(r) => ({ onClick: () => onOpenScene(d.document_id, r.scene_id) })} />,
          }]} />
        );
      })}
      <Collapse size="small" items={[{
        key: "unused",
        label: t(`没被任何条款用到的素材：${coverage.unused_assets.length} / ${coverage.asset_count}（所有项目）`,
          `Assets no clause uses: ${coverage.unused_assets.length} / ${coverage.asset_count} (all projects)`),
        children: coverage.unused_assets.length ? (
          <Table className="ov-table" size="small" rowKey="asset_id" pagination={false} tableLayout="fixed" scroll={{ y: 220 }} dataSource={coverage.unused_assets}
            columns={[{ title: t("素材", "Asset"), dataIndex: "title", ellipsis: true }, { title: t("来源", "Source"), dataIndex: "source_name", ellipsis: true, width: "40%" }]} />
        ) : <span className="muted">{t("每个素材都有条款用到。", "Every asset is used by some clause.")}</span>,
      }]} />
    </div>
  );
}
