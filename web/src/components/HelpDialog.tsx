import { Modal } from "antd";
import { useT } from "../i18n";

export function HelpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { lang, t } = useT();
  return (
    <Modal title={t("使用帮助", "Help")} open={open} onCancel={onClose} footer={null} width={600}>
      {lang === "zh" ? (
        <div className="help">
          <h4>从资产到报告</h4>
          <ol>
            <li><b>资产管理</b>：导入 XOSC 与 XODR；带模型、目录等依赖时上传 ZIP。.sim 场景包会展开为多个资产。</li>
            <li><b>新建项目</b>：项目保存 PDF、场景修订和决策。资产库由所有项目共用。</li>
            <li><b>工作台</b>：导入规程 PDF，选择场景，核对原文和提取事实，再检索候选资产。</li>
            <li><b>播放仿真</b>：选择候选资产后直接播放。esmini 会自动查找，特殊安装位置可在设置 → 本机服务中选择。</li>
            <li><b>保存复用决策</b>：决策固定当前场景修订和资产版本，可在总览中重新下载。</li>
          </ol>
          <p>没有选择场景时，检索框按文本检索相似资产，结论标为“文本召回 · 待结构验证”，不作复用结论。模型解释需另行点击才会发送所列证据。</p>
          <p>候选排序：先看阻断差异，再看修改成本，最后看相似度。</p>
          <h4>退出</h4>
          <p>关闭标签页不会停止服务。使用桌面 <b>OpenX - Stop</b> 或托盘的 <b>关闭 OpenX</b>。</p>
        </div>
      ) : (
        <div className="help">
          <h4>From assets to reports</h4>
          <ol>
            <li><b>Asset management</b>: import paired XOSC/XODR files, or a ZIP with dependencies. A .sim package expands into several assets.</li>
            <li><b>Create a project</b> for PDFs, scene revisions and decisions. Assets are shared by all projects.</li>
            <li><b>Workbench</b>: import a protocol PDF, select a scene, review the source and extracted facts, then search for candidates.</li>
            <li><b>Play the simulation</b> of a selected candidate. esmini is detected automatically; choose a custom installation under Settings → Local service.</li>
            <li><b>Save the decision</b> to pin the scene revision and asset version. Download it again from Overview.</li>
          </ol>
          <p>Without a selected scene the search box finds similar assets by text only, marked “Text recall · verify structure”; it is not a reuse decision. Model explanations send the listed evidence only when you ask for them.</p>
          <p>Candidates are ranked by blocking differences, then change cost, then similarity.</p>
          <h4>Exit</h4>
          <p>Closing the tab leaves the service running. Use <b>OpenX - Stop</b> on the desktop or the tray's exit command.</p>
        </div>
      )}
    </Modal>
  );
}
