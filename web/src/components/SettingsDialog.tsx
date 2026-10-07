import { useEffect, useState } from "react";
import { Alert, App, AutoComplete, Button, Collapse, Form, Input, InputNumber, Modal, Popconfirm, Radio, Select, Space, Switch, Tabs } from "antd";
import { ApiOutlined, FolderOpenOutlined, ReloadOutlined, SaveOutlined, SearchOutlined } from "@ant-design/icons";
import { api, type Appearance, type Encoder, type Lang, type ModelDraft, type ModelInfo, type Preferences, type Settings } from "../api";
import { useT } from "../i18n";
import { SchemaTab } from "./SchemaUpdates";

interface Props {
  open: boolean;
  onClose: () => void;
  preferences: Preferences;
  onPreferences: (p: Partial<Preferences>) => void;
}

export function SettingsDialog({ open, onClose, preferences, onPreferences }: Props) {
  const { t } = useT();
  const { message } = App.useApp();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    api.settings().then(setSettings).catch((e: Error) => setError(e.message));
  }, [open]);

  const openFolder = (target: "data" | "esmini") => api.openFolder(target).catch((e: Error) => message.error(e.message));

  return (
    <Modal title={t("工作区设置", "Workspace settings")} open={open} onCancel={onClose} footer={null} width={640} destroyOnHidden>
      <p className="muted settings-lead">{t("设置保存在本机，重启后仍然有效。", "Settings are saved on this computer and survive restarts.")}</p>
      {error && <Alert type="error" showIcon title={error} />}
      {settings && (
        <Tabs
          className="settings-tabs"
          items={[
            { key: "model", label: t("大模型", "Language model"), children: <ModelTab settings={settings} onSaved={(model) => setSettings({ ...settings, model })} /> },
            {
              key: "service",
              label: t("本机服务", "Local service"),
              children: <ServiceTab settings={settings} onPreview={(preview) => setSettings({ ...settings, preview })} onOpen={openFolder}
                preferences={preferences} onPreferences={onPreferences} />,
            },
            { key: "display", label: t("显示", "Display"), children: <DisplayTab preferences={preferences} onChange={onPreferences} /> },
            {
              key: "advanced",
              label: t("高级", "Advanced"),
              children: <><RetrievalChoice preferences={preferences} onChange={onPreferences} /><h4 className="settings-h">{t("文件标准", "File standards")}</h4><SchemaTab /></>,
            },
          ]}
        />
      )}
    </Modal>
  );
}

function ModelTab({ settings, onSaved }: { settings: Settings; onSaved: (m: Settings["model"]) => void }) {
  const { t } = useT();
  const { message } = App.useApp();
  const saved = settings.model;
  const [form] = Form.useForm<ModelDraft>();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const modelId = (Form.useWatch("model", form) ?? "").trim();
  const chosen = models.find((m) => m.id === modelId);
  const thinking = Form.useWatch("thinking", form);
  const effort = Form.useWatch("reasoning_effort", form) ?? "";
  // Levels the service declares for the chosen model; a saved level stays selectable.
  const levels = [...new Set([...(chosen?.effort_levels ?? []), ...(effort ? [effort] : [])])];
  const [busy, setBusy] = useState<"list" | "test" | "save" | "key" | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    form.setFieldsValue({ ...saved, api_key: "" });
  }, [form, saved]);
  // Every call may use the model's whole output limit: only generated tokens are billed.
  const limit = chosen?.max_output_tokens;
  useEffect(() => {
    if (limit) form.setFieldValue("max_tokens", Math.min(limit, 1048576));
  }, [form, limit]);
  // A model that declares image input reads each scene's figures with its text.
  const reads = chosen?.image_input;
  useEffect(() => {
    if (reads !== undefined) form.setFieldValue("image_input", reads);
  }, [form, reads]);

  const run = async <T,>(kind: NonNullable<typeof busy>, work: (d: ModelDraft) => Promise<T>, done: (r: T) => string) => {
    setBusy(kind);
    setResult(null);
    try {
      const draft = { ...form.getFieldsValue(true), model: (form.getFieldValue("model") ?? "").trim() } as ModelDraft;
      setResult({ ok: true, text: done(await work(draft)) });
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const fetchModels = () =>
    run("list", api.modelList, (r) => {
      setModels(r.details);
      return t(`获取到 ${r.models.length} 个模型，可在“模型名”中选择。`, `${r.models.length} models found. Choose one under Model ID.`);
    });
  const test = () => run("test", api.modelTest, (r) => t(`模型可用：${r.model}`, `Model available: ${r.model}`));
  const save = () =>
    form.validateFields().then(() =>
      run("save", api.modelSave, (m) => {
        onSaved(m);
        form.setFieldValue("api_key", "");
        return t("模型配置已保存。", "Model settings saved.");
      }),
    ).catch(() => undefined);
  const removeKey = async () => {
    setBusy("key");
    try {
      onSaved(await api.modelRemoveKey());
      message.success(t("已移除保存的 Key。", "Saved key removed."));
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Form form={form} layout="vertical" size="middle" className="settings-form">
      <p className="muted">{t("用于 PDF 场景识别、资产分类和匹配解释。兼容 Chat Completions 接口。", "Used for PDF extraction, asset classification and explanations. Chat Completions compatible.")}</p>
      {!saved.readable && <Alert type="warning" showIcon title={t("保存的模型设置无法读取，请重新配置。", "Saved model settings could not be read. Configure them again.")} />}
      <Form.Item name="base_url" label={t("服务地址", "Base URL")} rules={[{ required: true }]} extra={t("例如 https://api.deepseek.com 或供应商的 /v1 地址", "For example https://api.deepseek.com or a provider's /v1 URL")}>
        <Input />
      </Form.Item>
      <Form.Item name="api_key" label="API Key" extra={saved.has_key ? t("修改服务地址后，需要重新输入 Key。", "Changing the base URL requires entering the key again.") : undefined}>
        <Input.Password autoComplete="off" placeholder={saved.has_key ? t("已保存；留空保持", "Saved; leave blank to keep") : t("请输入 Key", "Enter API key")} />
      </Form.Item>
      <Form.Item label={t("模型名（可手动输入）", "Model ID (editable)")} required>
        <Space.Compact block>
          <Form.Item name="model" noStyle rules={[{ required: true, whitespace: true }]}>
            <AutoComplete options={models.map((m) => ({ value: m.id }))} filterOption={(input, o) => !!o?.value.toLowerCase().includes(input.toLowerCase())}
              placeholder={t("选择模型或手动输入", "Select or enter a model ID")} />
          </Form.Item>
          <Button icon={<ReloadOutlined />} loading={busy === "list"} onClick={fetchModels}>{t("获取模型清单", "Fetch model list")}</Button>
        </Space.Compact>
      </Form.Item>
      <Collapse
        size="small"
        ghost
        items={[{
          key: "adv",
          label: t("高级参数", "Advanced options"),
          children: (
            <div className="settings-grid">
              <Form.Item name="thinking" label={t("思考模式", "Thinking mode")} valuePropName="checked"><Switch /></Form.Item>
              <Form.Item name="reasoning_effort" label={t("思考等级", "Thinking effort")}
                extra={!thinking ? t("思考模式关闭时不生效。", "Applies only with thinking on.")
                  : !chosen ? t("先获取模型清单，才能看到该模型支持的等级。", "Fetch the model list to see this model's levels.")
                  : !chosen.effort_levels.length ? t("该服务没有声明思考等级，使用服务默认。", "The service declares no levels; its default applies.") : undefined}>
                <Select disabled={!thinking || !levels.length}
                  options={[{ value: "", label: chosen?.default_effort ? t(`服务默认（${chosen.default_effort}）`, `Service default (${chosen.default_effort})`) : t("服务默认", "Service default") },
                    ...levels.map((level) => ({ value: level, label: level }))]} />
              </Form.Item>
              <Form.Item name="max_tokens" label={t("最大输出 tokens", "Maximum output tokens")}
                extra={limit ? t("已取该模型的上限；只按实际生成计费。", "Set to this model's limit; only generated tokens are billed.")
                  : t("获取模型清单后自动取模型上限。", "Fetch the model list to use the model's limit.")}>
                <InputNumber min={256} max={1048576} step={256} />
              </Form.Item>
              <Form.Item name="timeout" label={t("超时（秒）", "Timeout (seconds)")}><InputNumber min={10} max={1800} step={10} /></Form.Item>
              <Form.Item name="image_input" label={t("读取示意图", "Read figures")} valuePropName="checked"
                extra={reads === false ? t("该模型没有声明图片输入。", "This model declares no image input.")
                  : reads ? t("该模型支持图片输入：PDF 提取时把场景示意图一起发给模型。", "This model reads images: PDF extraction sends each scene's figures.")
                  : t("获取模型清单后按模型是否支持图片自动设置。", "Fetch the model list to set this from the model's image support.")}>
                <Switch disabled={reads === false} />
              </Form.Item>
              <Form.Item name="concurrency" label={t("PDF 并发请求数", "Concurrent PDF requests")}
                extra={t("PDF 提取同时发出的模型请求数；服务限流时调低。", "Model requests a PDF extraction sends at once; lower it if the service rate-limits.")}>
                <InputNumber min={1} max={256} />
              </Form.Item>
            </div>
          ),
        }]}
      />
      {result && <Alert className="settings-result" type={result.ok ? "success" : "error"} showIcon title={result.text} />}
      <div className="settings-actions">
        <Button icon={<ApiOutlined />} loading={busy === "test"} onClick={test}>{t("测试所选模型", "Test selected model")}</Button>
        <Button type="primary" icon={<SaveOutlined />} loading={busy === "save"} onClick={save}>{t("保存模型配置", "Save model settings")}</Button>
        {saved.has_key && (
          <Popconfirm title={t("移除本机保存的 API Key？", "Remove the API key saved on this computer?")} onConfirm={removeKey}
            okText={t("移除", "Remove")} cancelText={t("取消", "Cancel")}>
            <Button danger type="text" loading={busy === "key"}>{t("移除保存的 Key", "Remove saved key")}</Button>
          </Popconfirm>
        )}
      </div>
      <p className="muted settings-note">
        {t("测试会发送一条简短请求；解析 PDF 时会发送文档文字。Key 只保存在本机，Windows 使用当前用户加密。",
          "Testing sends a short request; PDF extraction sends document text. The key stays on this computer and is encrypted for the current Windows user.")}
      </p>
    </Form>
  );
}

function ServiceTab({ settings, onPreview, onOpen, preferences, onPreferences }: {
  settings: Settings; onPreview: (p: Settings["preview"]) => void; onOpen: (t: "data" | "esmini") => void;
  preferences: Preferences; onPreferences: (p: Partial<Preferences>) => void;
}) {
  const { t } = useT();
  const [busy, setBusy] = useState<"browse" | "detect" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const preview = settings.preview;

  const act = async (kind: "browse" | "detect") => {
    setBusy(kind);
    setError(null);
    try {
      onPreview(await (kind === "browse" ? api.previewBrowse() : api.previewDetect()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="settings-form">
      <h4 className="settings-h">{t("仿真预览（esmini）", "Simulation preview (esmini)")}</h4>
      {preview.executable ? (
        <Alert type="success" showIcon title={t("仿真预览已就绪，已找到 esmini。", "Simulation preview ready. esmini was found.")} />
      ) : (
        <Alert type="info" showIcon title={preview.configured
          ? t("所选文件夹中没有完整的 esmini，请重新选择或改为自动查找。", "The chosen folder has no complete esmini. Choose again or detect automatically.")
          : t("尚未找到 esmini。已检查常用安装位置；如果已安装，请选择安装文件夹。", "esmini was not found in common locations. If it is installed, browse to its folder.")} />
      )}
      {preview.folder && (
        <div className="location">
          <span className="muted">{preview.configured ? t("手动选择的位置", "Chosen location") : t("自动找到的位置", "Detected location")}</span>
          <code>{preview.folder}</code>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => onOpen("esmini")}>{t("打开文件夹", "Open folder")}</Button>
        </div>
      )}
      {error && <Alert type="error" showIcon title={error} />}
      <Space>
        <Button icon={<FolderOpenOutlined />} loading={busy === "browse"} onClick={() => act("browse")}>{t("浏览安装文件夹", "Browse installation folder")}</Button>
        <Button icon={<SearchOutlined />} loading={busy === "detect"} onClick={() => act("detect")} disabled={!preview.configured}>{t("自动查找", "Detect automatically")}</Button>
      </Space>
      <p className="muted settings-note">{t("文件夹选择窗口会在这台电脑的桌面上打开。", "The folder picker opens on this computer's desktop.")}</p>
      <label className="switch-row">
        <Switch size="small" checked={preferences.auto_preview} onChange={(on) => onPreferences({ auto_preview: on })} />
        <span>{t("导入素材后自动生成预览", "Make previews after an asset import")}</span>
      </label>
      <p className="muted settings-note">{t("逐个运行 esmini 截一张画面并画出道路俯视图，会占用一部分 CPU，可在资产管理里随时停止；也可以在资产管理里手动点“生成预览”。",
        "Runs esmini on one version at a time to save a frame and draws each road from above. It uses some CPU and can be stopped in Asset management at any time, where \"Make previews\" also starts it by hand.")}</p>

      <h4 className="settings-h">{t("数据位置", "Data location")}</h4>
      <div className="location">
        <code>{settings.data_dir}</code>
        <Button size="small" icon={<FolderOpenOutlined />} onClick={() => onOpen("data")}>{t("打开文件夹", "Open folder")}</Button>
      </div>
      <p className="muted settings-note">{t("资产、项目、PDF 和决策都保存在这里。", "Assets, projects, PDFs and decisions are stored here.")}</p>
    </div>
  );
}

function DisplayTab({ preferences, onChange }: { preferences: Preferences; onChange: (p: Partial<Preferences>) => void }) {
  const { t } = useT();
  return (
    <Form layout="vertical" className="settings-form">
      <Form.Item label={t("外观", "Appearance")} extra={t("跟随系统会自动响应系统外观变化。", "System mode follows your device automatically.")}>
        <Radio.Group optionType="button" value={preferences.appearance} onChange={(e) => onChange({ appearance: e.target.value as Appearance })}
          options={[
            { value: "light", label: t("亮色", "Light") },
            { value: "dark", label: t("暗色", "Dark") },
            { value: "system", label: t("跟随系统", "System") },
          ]} />
      </Form.Item>
      <Form.Item label={t("界面语言", "Language")} extra={t("也会切换评估词汇和报告语言。", "Also switches assessment vocabulary and report language.")}>
        <Radio.Group optionType="button" value={preferences.language} onChange={(e) => onChange({ language: e.target.value as Lang })}
          options={[{ value: "zh", label: "中文" }, { value: "en", label: "English" }]} />
      </Form.Item>
      <Form.Item label={t("候选素材的名字", "Candidate names")}
        extra={t("仿真软件导出的场景和道路文件常以编号命名；默认显示场景名和地图名。", "Scenario and road files exported by a simulator are often named by an id; by default the scenario and map names are shown.")}>
        <Radio.Group optionType="button" value={preferences.show_file_names} onChange={(e) => onChange({ show_file_names: e.target.value as boolean })}
          options={[{ value: false, label: t("场景名和地图名", "Scenario and map names") }, { value: true, label: t("文件名", "File names") }]} />
      </Form.Item>
    </Form>
  );
}

/** How the library is searched for candidates; changing it re-ranks. */
function RetrievalChoice({ preferences, onChange }: { preferences: Preferences; onChange: (p: Partial<Preferences>) => void }) {
  const { t } = useT();
  return (
    <Form layout="vertical" className="settings-form">
      <Form.Item label={t("候选检索后端", "Candidate retrieval backend")} extra={t("复用建议与手动检索均由它召回候选；更改后将重新检索。", "Reuse suggestions and manual search both recall candidates with it; changing it searches again.")}>
        <Radio.Group value={preferences.encoder} onChange={(e) => onChange({ encoder: e.target.value as Encoder })}>
          <Space orientation="vertical">
            <Radio value="bge">{t("BGE-M3 语义检索（需安装 semantic 依赖）", "BGE-M3 semantic retrieval (semantic extra required)")}</Radio>
            <Radio value="hashing">{t("轻量离线检索", "Lightweight offline retrieval")}</Radio>
          </Space>
        </Radio.Group>
      </Form.Item>
    </Form>
  );
}
