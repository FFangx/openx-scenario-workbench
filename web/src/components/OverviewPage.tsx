import { useEffect, useState } from "react";
import { Alert, Button, Empty, Spin } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { api, type Overview } from "../api";
import { useT } from "../i18n";
import { Coverage } from "./BindingViews";
import type { Page } from "./TopBar";

interface Props {
  projectId: string | null;
  onNavigate: (page: Page) => void;
  onOpenScene: (documentId: string, sceneId: string) => void;
}

/** How far the project's PDFs are covered by confirmed assets, and the library in a few numbers. */
export function OverviewPage({ projectId, onNavigate, onOpenScene }: Props) {
  const { t } = useT();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.overview().then(setOverview).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="ox-page overview">
      <section className="panel ov-coverage">
        <div className="ph">
          {t("条款复用覆盖", "Clause reuse coverage")}
          <span className="meta">{t("已确认的复用结论，各项目共用", "Confirmed reuse conclusions, shared by all projects")}</span>
        </div>
        {projectId ? <Coverage projectId={projectId} onOpenScene={onOpenScene} />
          : <div className="ov-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("请先在顶栏创建或选择项目。", "Create or select a project in the header first.")} /></div>}
      </section>
      <section className="panel ov-library">
        <div className="ph">{t("资产库", "Asset library")}</div>
        {error && <Alert type="error" showIcon title={error} />}
        {!overview ? <div className="center-pad"><Spin /></div> : <Library overview={overview} onNavigate={onNavigate} />}
      </section>
    </main>
  );
}

function Library({ overview, onNavigate }: { overview: Overview; onNavigate: (page: Page) => void }) {
  const { t } = useT();
  if (!overview.assets) {
    return (
      <div className="ov-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("资产库还是空的。导入 XOSC/XODR、ZIP 或 .sim 场景后即可进行复用评估。", "The asset library is empty. Import XOSC/XODR, ZIP or .sim scenarios to assess their reuse.")}>
          <Button type="primary" icon={<InboxOutlined />} onClick={() => onNavigate("assets")}>{t("前往资产管理", "Go to asset management")}</Button>
        </Empty>
      </div>
    );
  }
  // Versions only once an asset has an older one: until then they equal the assets.
  const metrics: [string, number, string?][] = [
    [t("资产", "Assets"), overview.assets],
    ...(overview.versions > overview.assets ? [[t("版本", "Versions"), overview.versions] as [string, number]] : []),
    [t("可播放", "Playable"), overview.playable, overview.playable ? "ok" : undefined],
    [t("未检测", "Not tested"), overview.untested],
    [t("缺道路", "No road"), overview.road_missing],
    [t("播放失败", "Failed"), overview.failed, overview.failed ? "bad" : undefined],
  ];
  return (
    <>
      <div className="metrics">
        {metrics.map(([label, value, cls]) => (
          <div key={label} className="metric">
            <span>{label}</span>
            <b className={cls}>{value}</b>
          </div>
        ))}
      </div>
      <p className="muted ov-note">
        {t("导入记录和每个素材的预览在资产管理里。", "Imports and each asset's preview are in Asset management.")}
        {" "}<a onClick={() => onNavigate("assets")}>{t("前往资产管理", "Go to asset management")}</a>
      </p>
    </>
  );
}
