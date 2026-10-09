import { useState } from "react";
import { App, Button, Form, Input, Modal, Popconfirm, Tag, Tooltip } from "antd";
import { DeleteOutlined, EditOutlined, FolderAddOutlined, FolderOpenOutlined, FolderOutlined, PlusOutlined, WarningOutlined } from "@ant-design/icons";
import { api, type MissingProject, type Project } from "../api";
import { useT } from "../i18n";

/** Where a project's folder goes: the location, then its name as a folder name. */
const joinPath = (folder: string, name: string) => `${folder.replace(/[\\/]+$/, "")}\\${name.replace(/[<>:"/\\|?*]/g, "_").trim()}`;

interface NewProjectProps {
  open: boolean;
  /** The folder new projects are created in. */
  location: string;
  onLocation: (location: string) => void;
  onClose: () => void;
  onCreated: (p: Project) => void;
}

/** A new project is a new folder in the location shown, which can be changed here. */
export function NewProjectDialog({ open, location, onLocation, onClose, onCreated }: NewProjectProps) {
  const { t } = useT();
  const { message } = App.useApp();
  const [form] = Form.useForm<{ name: string }>();
  const name = Form.useWatch("name", form) ?? "";
  const [busy, setBusy] = useState<"create" | "browse" | null>(null);

  const submit = async ({ name }: { name: string }) => {
    setBusy("create");
    try {
      const project = await api.createProject(name.trim());
      form.resetFields();
      onCreated(project);
      onClose();
      message.success(t(`已创建项目“${project.name}”`, `Created project “${project.name}”`));
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const browse = () => {
    setBusy("browse");
    api.chooseProjectLocation()
      .then((r) => !r.cancelled && onLocation(r.location))
      .catch((e: Error) => message.error(e.message))
      .finally(() => setBusy(null));
  };

  return (
    <Modal
      title={t("新建项目", "New project")}
      open={open}
      onCancel={onClose}
      okText={t("创建项目", "Create project")}
      onOk={() => form.submit()}
      confirmLoading={busy === "create"}
      destroyOnHidden
    >
      <p className="muted">{t("项目是本机上的一个文件夹，保存导入的 PDF、需求事实修订和导出的评估表；资产库与复用评估结论由所有项目共用。",
        "A project is a folder on this computer holding its PDFs, fact revisions and exported assessments. The asset library and the reuse conclusions are shared by all projects.")}</p>
      <Form form={form} layout="vertical" onFinish={submit} preserve={false}>
        <Form.Item
          name="name"
          label={t("项目名称", "Project name")}
          rules={[{ required: true, whitespace: true, message: t("请输入项目名称", "Enter a project name") }, { max: 120 }]}
        >
          <Input autoFocus maxLength={120} />
        </Form.Item>
      </Form>
      <div className="proj-where">
        <span className="muted">{t("项目文件夹", "Project folder")}</span>
        <Button size="small" type="link" icon={<FolderOpenOutlined />} loading={busy === "browse"} onClick={browse}>{t("更改位置…", "Change location…")}</Button>
        <code>{name.trim() ? joinPath(location, name) : location}</code>
      </div>
    </Modal>
  );
}

interface ProjectsProps {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  missing: MissingProject[];
  currentId: string | null;
  /** Reload the list, showing `select` when given. */
  onChanged: (select?: string) => void;
  onRenamed: (p: Project) => void;
  onNew: () => void;
}

/** Rename, delete and open the projects' folders; add a project folder moved or restored by hand. */
export function ProjectsDialog({ open, onClose, projects, missing, currentId, onChanged, onRenamed, onNew }: ProjectsProps) {
  const { t } = useT();
  const { message } = App.useApp();
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const run = (key: string, work: () => Promise<unknown>) => {
    setBusy(key);
    work().catch((e: Error) => message.error(e.message)).finally(() => setBusy(null));
  };
  const rename = () => {
    if (!editing || !editing.name.trim()) return;
    const { id, name } = editing;
    run(`rename:${id}`, () => api.renameProject(id, name.trim()).then((p) => {
      setEditing(null);
      onRenamed(p);
    }));
  };
  const remove = (p: Project) => run(`delete:${p.project_id}`, () => api.deleteProject(p.project_id).then(() => {
    message.success(t(`已删除项目“${p.name}”，文件夹已移到回收站`, `Deleted “${p.name}”; its folder is in the Recycle Bin`));
    onChanged();
  }));
  const forget = (m: MissingProject) => run(`delete:${m.project_id}`, () => api.deleteProject(m.project_id).then(() => onChanged()));
  const add = () => run("add", () => api.addProject().then((r) => {
    if (!r.project) return;
    message.success(t(`已添加项目“${r.project.name}”`, `Added project “${r.project.name}”`));
    onChanged(r.project.project_id);
  }));

  return (
    <Modal
      title={t("管理项目", "Manage projects")}
      open={open}
      onCancel={() => { setEditing(null); onClose(); }}
      width={720}
      destroyOnHidden
      footer={[
        <Button key="add" icon={<FolderAddOutlined />} loading={busy === "add"} onClick={add}>{t("打开已有项目…", "Open existing project…")}</Button>,
        <Button key="new" type="primary" icon={<PlusOutlined />} onClick={onNew}>{t("新建项目…", "New project…")}</Button>,
      ]}
    >
      <div className="proj-list">
        {projects.map((p) => {
          const isEditing = editing?.id === p.project_id;
          return (
            <div key={p.project_id} className={`proj-row${p.project_id === currentId ? " on" : ""}`}>
              <FolderOutlined className="proj-ic" />
              <div className="proj-txt">
                {isEditing ? (
                  <Input size="small" autoFocus maxLength={120} value={editing.name} aria-label={t("项目名称", "Project name")}
                    onChange={(e) => setEditing({ id: p.project_id, name: e.target.value })}
                    onPressEnter={rename} onKeyDown={(e) => e.key === "Escape" && (e.stopPropagation(), setEditing(null))} />
                ) : (
                  <b>{p.name}{p.project_id === currentId && <Tag className="proj-tag">{t("当前", "Current")}</Tag>}</b>
                )}
                <span className="muted">
                  {t(`${p.pdf_count} 个 PDF · 创建于 ${p.created_at.slice(0, 10)}`, `${p.pdf_count} PDF${p.pdf_count === 1 ? "" : "s"} · created ${p.created_at.slice(0, 10)}`)}
                </span>
                <button className="proj-path" title={t(`打开文件夹：${p.folder}`, `Open folder: ${p.folder}`)}
                  onClick={() => run(`open:${p.project_id}`, () => api.openProjectFolder(p.project_id))}>{p.folder}</button>
              </div>
              <div className="proj-acts">
                {isEditing ? (<>
                  <Button size="small" type="primary" loading={busy === `rename:${p.project_id}`} disabled={!editing.name.trim()} onClick={rename}>{t("保存", "Save")}</Button>
                  <Button size="small" onClick={() => setEditing(null)}>{t("取消", "Cancel")}</Button>
                </>) : (<>
                  <Tooltip title={t("打开文件夹", "Open folder")}>
                    <Button size="small" type="text" icon={<FolderOpenOutlined />} aria-label={t("打开文件夹", "Open folder")}
                      onClick={() => run(`open:${p.project_id}`, () => api.openProjectFolder(p.project_id))} />
                  </Tooltip>
                  <Tooltip title={t("重命名", "Rename")}>
                    <Button size="small" type="text" icon={<EditOutlined />} aria-label={t("重命名", "Rename")}
                      onClick={() => setEditing({ id: p.project_id, name: p.name })} />
                  </Tooltip>
                  <Popconfirm
                    title={t(`删除项目“${p.name}”？`, `Delete “${p.name}”?`)}
                    description={<span className="proj-confirm">{t("项目文件夹会移到回收站，需要时可以从回收站还原。资产库和复用评估结论由所有项目共用，不受影响。",
                      "The project folder moves to the Recycle Bin, where you can restore it. The asset library and the reuse conclusions are shared by all projects and stay.")}</span>}
                    okText={t("删除", "Delete")} cancelText={t("取消", "Cancel")} okButtonProps={{ danger: true }}
                    onConfirm={() => remove(p)}
                  >
                    <Tooltip title={t("删除", "Delete")}>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label={t("删除", "Delete")} loading={busy === `delete:${p.project_id}`} />
                    </Tooltip>
                  </Popconfirm>
                </>)}
              </div>
            </div>
          );
        })}
        {!projects.length && <p className="muted proj-none">{t("还没有项目。", "No projects yet.")}</p>}
        {missing.map((m) => (
          <div key={m.project_id} className="proj-row missing">
            <WarningOutlined className="proj-ic" />
            <div className="proj-txt">
              <b>{m.name}</b>
              <span className="muted">{t(`找不到文件夹：${m.folder}。移动过的话，用“打开已有项目”重新添加。`,
                `Folder not found: ${m.folder}. If you moved it, add it again with "Open existing project".`)}</span>
            </div>
            <div className="proj-acts">
              <Button size="small" loading={busy === `delete:${m.project_id}`} onClick={() => forget(m)}>{t("从列表移除", "Remove from list")}</Button>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
