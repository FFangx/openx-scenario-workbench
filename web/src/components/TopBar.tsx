import { Fragment, useEffect, useState } from "react";
import { App, Button, Dropdown, Empty, Form, Input, Modal, Popover, Tooltip, type MenuProps } from "antd";
import {
  CheckOutlined,
  DownloadOutlined,
  DownOutlined,
  FolderOutlined,
  HistoryOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { api, levelLabel, urls, type Lang, type PdfDocument, type Project, type Report } from "../api";
import { dateTime, useT } from "../i18n";

export type Page = "workbench" | "overview" | "assets";

interface TopBarProps {
  page: Page;
  onPage: (p: Page) => void;
  onLang: (l: Lang) => void;
  projects: Project[];
  projectId: string | null;
  onProject: (id: string) => void;
  onCreated: (p: Project) => void;
  onHelp: () => void;
  onSettings: () => void;
  /** Back to the workbench start page. */
  onHome: () => void;
}

const check = (on: boolean) => (on ? <CheckOutlined /> : <span style={{ width: 14 }} />);

export function TopBar({ page, onPage, onLang, projects, projectId, onProject, onCreated, onHelp, onSettings, onHome }: TopBarProps) {
  const { t, lang } = useT();
  const [creating, setCreating] = useState(false);
  const project = projects.find((p) => p.project_id === projectId);

  const projectMenu: MenuProps = {
    items: [
      ...projects.map((p) => ({ key: p.project_id, label: p.name, icon: check(p.project_id === projectId) })),
      ...(projects.length ? [{ type: "divider" as const }] : []),
      { key: "__new", label: t("新建项目…", "New project…"), icon: <PlusOutlined /> },
    ],
    onClick: ({ key }) => (key === "__new" ? setCreating(true) : onProject(key)),
  };

  const pages: [Page, string][] = [
    ["workbench", t("工作台", "Workbench")],
    ["overview", t("总览", "Overview")],
    ["assets", t("资产管理", "Asset management")],
  ];

  return (
    <header className="ox-top">
      <button className="ox-home" onClick={onHome} aria-label={t("回到起始页", "Back to start")}>
        <span className="ox-brand" translate="no">
          Open<b>X</b>
        </span>
        <span className="ox-app">{t("场景工作台", "Scenario Workbench")}</span>
      </button>
      <span className="ox-sep" />
      <nav className="ox-nav" aria-label={t("页面", "Pages")}>
        {pages.map(([key, label]) => (
          <button key={key} className={page === key ? "on" : ""} aria-current={page === key ? "page" : undefined} onClick={() => onPage(key)}>
            {label}
          </button>
        ))}
      </nav>
      <div className="right">
        <Dropdown menu={projectMenu} trigger={["click"]}>
          <button className="hbtn">
            {t("项目", "Project")} <b>{project?.name ?? t("尚无项目", "None yet")}</b> <DownOutlined />
          </button>
        </Dropdown>
        <span className="ox-sep" />
        <Tooltip title={t("数据只保存在本机", "Data is stored on this computer")}>
          <span className="hbtn">
            {t("工作区", "Workspace")} <b>{t("本机", "Local")}</b>
          </span>
        </Tooltip>
        <span className="ox-sep" />
        <Tooltip title={t("使用帮助", "Help")}>
          <button className="hicon" aria-label={t("使用帮助", "Help")} onClick={onHelp}>
            <QuestionCircleOutlined />
          </button>
        </Tooltip>
        <Tooltip title={t("设置", "Settings")}>
          <button className="hicon" aria-label={t("设置", "Settings")} onClick={onSettings}>
            <SettingOutlined />
          </button>
        </Tooltip>
        <span className="ox-sep" />
        <span className="lang">
          <button className={lang === "en" ? "on" : ""} onClick={() => onLang("en")}>EN</button>
          <button className={lang === "zh" ? "on" : ""} onClick={() => onLang("zh")}>中文</button>
        </span>
      </div>
      <NewProject open={creating} onClose={() => setCreating(false)} onCreated={onCreated} />
    </header>
  );
}

function NewProject({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (p: Project) => void }) {
  const { t } = useT();
  const { message } = App.useApp();
  const [form] = Form.useForm<{ name: string }>();
  const [busy, setBusy] = useState(false);

  const submit = async ({ name }: { name: string }) => {
    setBusy(true);
    try {
      const project = await api.createProject(name.trim());
      form.resetFields();
      onCreated(project);
      onClose();
      message.success(t(`已创建项目“${project.name}”`, `Created project “${project.name}”`));
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("新建项目", "New project")}
      open={open}
      onCancel={onClose}
      okText={t("创建项目", "Create project")}
      onOk={() => form.submit()}
      confirmLoading={busy}
      destroyOnHidden
    >
      <p className="muted">{t("项目保存 PDF、场景修订和复用决策；资产库由所有项目共用。", "A project keeps PDFs, scene revisions and reuse decisions. The asset library is shared by all projects.")}</p>
      <Form form={form} layout="vertical" onFinish={submit} preserve={false}>
        <Form.Item
          name="name"
          label={t("项目名称", "Project name")}
          rules={[{ required: true, whitespace: true, message: t("请输入项目名称", "Enter a project name") }, { max: 120 }]}
        >
          <Input autoFocus maxLength={120} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

interface StepBarProps {
  active: number;
  projectId: string | null;
  docs: PdfDocument[];
  docId: string | null;
  onDoc: (id: string) => void;
  onAllDecisions: () => void;
}

export function StepBar({ active, projectId, docs, docId, onDoc, onAllDecisions }: StepBarProps) {
  const { t, lang } = useT();
  const [reports, setReports] = useState<Report[] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  // Links start empty and fill up to the active step after the first paint, so entering the workflow animates them.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  const steps = [t("从 PDF 提取", "Extract from PDF"), t("检索资产库", "Search asset library"), t("评估复用", "Assess reuse"), t("导出与追溯", "Export & trace")];

  const openHistory = (open: boolean) => {
    setHistoryOpen(open);
    if (open && projectId) api.reports(projectId).then(setReports).catch(() => setReports([]));
  };

  const files = docs.length ? (
    <div className="pop-list">
      {docs.map((d) => (
        <div key={d.document_id} className={`file-row${d.document_id === docId ? " on" : ""}`}>
          <button onClick={() => onDoc(d.document_id)}>
            <b>{d.filename}</b>
            <span>
              {t(`${d.page_count} 页 · ${d.scene_count} 个场景 · 导入于 ${d.imported_at.slice(0, 10)}`,
                `${d.page_count} pages · ${d.scene_count} scenes · imported ${d.imported_at.slice(0, 10)}`)}
            </span>
          </button>
          {projectId && (
            <Tooltip title={t("下载 PDF", "Download PDF")}>
              <Button type="text" size="small" icon={<DownloadOutlined />} href={urls.pdf(projectId, d.document_id)} download={d.filename}
                aria-label={t("下载 PDF", "Download PDF")} />
            </Tooltip>
          )}
        </div>
      ))}
    </div>
  ) : (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("当前项目还没有 PDF", "No PDFs in this project yet")} />
  );

  const activity = (
    <div className="pop-history">
      {reports === null ? (
        <div className="muted">{t("加载中…", "Loading…")}</div>
      ) : reports.length ? (
        <div className="pop-list">
          {reports.slice(0, 5).map((r) => (
            <div key={r.report_id} className="row">
              <b>{r.scene.title ?? t("整份 PDF 汇总", "Document summary")}</b>
              <span>{r.level ? levelLabel(r.level, lang) : "—"} · {t("保存于", "saved")} {dateTime(r.saved_at)}</span>
            </div>
          ))}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("尚无已保存的决策", "No saved decisions yet")} />
      )}
      <Button type="link" size="small" onClick={() => { setHistoryOpen(false); onAllDecisions(); }}>
        {t("查看全部决策", "View all decisions")}
      </Button>
    </div>
  );

  return (
    <nav className="ox-steps">
      {steps.map((s, i) => (
        <Fragment key={i}>
          {i > 0 && <span className={`ox-step-link${i <= active && filled ? " done" : ""}`} style={{ "--i": i } as React.CSSProperties}><i /></span>}
          <span className={`ox-step${i === active ? " on" : i < active ? " done" : ""}`}>
            <span className="n">{i < active ? <CheckOutlined /> : i + 1}</span>
            {s}
          </span>
        </Fragment>
      ))}
      <div className="tools">
        <Popover title={t("项目文件", "Project files")} content={files} trigger="click" placement="bottomRight">
          <button>
            <FolderOutlined /> {t("项目文件", "Project files")}
          </button>
        </Popover>
        <i />
        <Popover title={t("最近的复用决策", "Recent reuse decisions")} content={activity} trigger="click" placement="bottomRight"
          open={historyOpen} onOpenChange={openHistory}>
          <button>
            <HistoryOutlined /> {t("最近记录", "Recent activity")}
          </button>
        </Popover>
      </div>
    </nav>
  );
}
