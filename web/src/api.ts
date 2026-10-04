// Typed client for the FastAPI layer in src/openx_workbench/api.py (proxied at /api by Vite).

export type Level = "direct" | "modify" | "major_modify" | "review" | "new_build";
export type Lang = "en" | "zh";
export type Appearance = "light" | "dark" | "system";
export type Encoder = "bge" | "hashing";

export interface Project { project_id: string; name: string; created_at: string }

export interface PdfDocument {
  document_id: string;
  project_id: string;
  filename: string;
  source_standard: string;
  sha256: string;
  imported_at: string;
  page_count: number;
  scene_count: number;
  extraction_engine: string;
  size_bytes: number | null;
}

export interface Evidence { source_pdf: string; section_id: string; page_start: number; page_end: number; source_text: string }

export interface Scene {
  scene_id: string;
  revision: number;
  package_id: string;
  title: string;
  preferred_text: string;
  section_id: string;
  pages: [number, number] | null;
  evidence: Evidence[];
  review_status: string;
  classification: Record<string, string | number | null>;
  entities: string[];
  actions: string[];
  road_types: string[];
  source_region: { page: number; clip: [number, number, number, number] } | null;
  document_id: string;
  structure: SceneStructure | Record<string, never>;
  triggers: string[];
  weather: string[];
  time_of_day: string[];
  parameters: Record<string, number>;
  issues: string[];
  ocr: boolean;
  /** Only in queue listings: is this revision confirmed into the library, or already assessed. */
  published?: boolean;
  queue_status?: "pending" | "confirmed" | "assessed";
}

export interface Participant { kind: string; bearing: string; facing: string; actions: string[]; age?: string; speed_kph?: number | null; [key: string]: unknown }

export interface SceneStructure {
  road_class: string;
  tested_function: string;
  test_intent: string;
  ego_actions: string[];
  semantic_triggers: string[];
  participants: Participant[];
  params: Record<string, unknown>;
  [key: string]: unknown;
}

export type SceneSchema = Record<
  "road_class" | "tested_function" | "test_intent" | "ego_actions" | "semantic_triggers" | "weather" | "time_of_day"
  | "participant_kind" | "bearing" | "facing" | "participant_actions" | "age",
  string[]
>;

export interface Revision { revision: number; title: string; parameters: Record<string, number>; structure: SceneStructure | Record<string, never> }

export interface ExtractionRecord { engine: string; current_engine: string; outdated: boolean; has_record: boolean; model: string | null; issues: string[]; flags: string[]; ocr: boolean }

export interface Explanation {
  evidence: { evidence_id: string; location: string; text: string }[];
  insufficient: string[];
  explanation_id?: string;
  explanation?: { verdict: string; method: string; observations: { text: string; citations: string[] }[] };
}

export interface PreviewStatus {
  state: "idle" | "starting" | "running" | "finished" | "failed" | "stopped";
  asset_id?: string;
  version_id?: string;
  frames?: number;
  error?: string;
  snapshot_error?: string;
  stream_url?: string;
  log?: string;
}

export interface Difference {
  category: string;
  requested: string;
  candidate: string;
  action: string;
  blocking: boolean;
  cost: number;
  verified: boolean;
  category_label: string;
  requested_label: string;
  candidate_label: string;
  text: string;
}

export interface ReviewItem { id: string; kind: "difference" | "standards"; difference: number | null }

export interface StandardCheck { status: string; standard?: string; version?: string | null; issues?: { message: string; line?: number | null }[]; detail?: string }

export interface Candidate {
  asset_id: string;
  version_id: string | null;
  version_number: number | null;
  source_name: string;
  compatibility: string;
  title: string;
  display_title: string;
  xosc: string;
  xodr: string;
  description: string;
  classification: Record<string, string | string[]>;
  scores: { combined: number; semantic: number; scenario: number; road: number };
  level: Level;
  structural_level: Level;
  review_kind: string;
  /** What a reviewer confirms, each with a reason, before a "review" decision can be saved. */
  review_items: ReviewItem[];
  change_cost: number | null;
  reasons: { code: string; label: string }[];
  differences: Difference[];
  standard_checks: { passed: boolean; pending: Record<string, string>; checks?: Record<string, StandardCheck> };
  scenario: { name: string | null; entities: { name: string; kind: string; category: string | null }[]; actions: string[]; trigger_count: number; parameters: string[]; environment: Record<string, string | number> };
  road: { total_length_m: number; lane_count: number; lane_types: Record<string, number>; geometry_types: Record<string, number>; junction_count: number; road_count: number; revision: string | null };
  has_frame: boolean;
}

export interface Library { asset_count: number; last_import: string | null; encoder: string; facets: Record<string, string[]> }

export interface Report {
  report_id: string;
  saved_at: string;
  asset_id: string | null;
  version_id: string | null;
  kind: "decision" | "batch";
  level: Level | null;
  review_kind: string;
  signed_off: boolean;
  counts: Record<string, number> | null;
  scene_count: number | null;
  scene: { title: string | null; scene_id: string | null; revision: number | null; document_id: string | null };
}

export interface TraceSource { title?: string; scene_id?: string; revision?: number; document_id?: string; evidence?: Evidence[] }

export interface TraceCandidate { title?: string; xosc?: string; xodr?: string; asset_id?: string; version_id?: string; version_number?: number }

export interface Trace {
  kind?: "batch_match";
  source?: TraceSource;
  candidate?: TraceCandidate;
  reuse?: { level: Level; review_kind?: string; estimated_change_cost?: number | null; review_signoff?: { signed_at: string; items: { id: string; reason: string; difference?: { category: string; requested: string; candidate: string } }[] } };
  // batch reports
  scene_count?: number;
  encoder?: string;
  counts?: Record<string, number>;
  entries?: { source: TraceSource; assessment: { level: Level | "no_candidates"; review_kind?: string; estimated_change_cost?: number | null }; candidates: { candidate: TraceCandidate }[] }[];
}

export interface ReportDetail { report_id: string; saved_at: string; version_id?: string; trace: Trace; reopenable: { document_id: string; scene_id: string }[] }

export interface Overview {
  assets: number;
  versions: number;
  playable: number;
  unavailable: number;
  untested: number;
  recent: { asset_id: string; version_id: string; title: string; source_name: string; version_number: number; compatibility: string; created_at: string }[];
}

export interface SearchResponse { encoder: string; total: number; library_size: number; scene: Scene | null; results: Candidate[] }

export interface MatchRequest {
  project_id: string;
  document_id?: string;
  scene_id?: string;
  revision?: number;
  text?: string;
  filters?: Record<string, string>;
  lang?: Lang;
}

export interface ModelSettings {
  base_url: string;
  model: string;
  thinking: boolean;
  max_tokens: number;
  timeout: number;
  has_key: boolean;
  readable: boolean;
}

/** A blank api_key keeps the saved key, but only while the endpoint is unchanged. */
export interface ModelDraft { base_url: string; model: string; api_key: string; thinking: boolean; max_tokens: number; timeout: number }

export interface PreviewSettings { configured: string; executable: string | null; folder: string | null; cancelled?: boolean }

export interface Preferences { language: Lang; appearance: Appearance; encoder: Encoder }

export interface Settings { model: ModelSettings; preview: PreviewSettings; data_dir: string; preferences: Preferences }

export type JobStatus = "running" | "completed" | "failed" | "stopped" | "interrupted";

export interface ImportReport { source_name: string; case_count: number; imported_count: number; missing_road_references: string[] }

export interface Job {
  id: string;
  kind: "pdf_import" | "asset_import";
  status: JobStatus;
  stage: string;
  current: string;
  done: number;
  total: number;
  started: number;
  updated: number;
  finished?: number;
  error: string;
  messages: string[];
  result: { project_id?: string; document_ids?: string[]; versions?: { asset_id: string; version_id: string }[] };
  cancelling: boolean;
  saved?: number;
  failed?: number;
  reports?: ImportReport[];
}

export interface VersionRef { asset_id: string; version_id: string | null }

export interface AssetRow {
  asset_id: string;
  version_id: string;
  version_number: number;
  name: string;
  xosc_name: string;
  xodr_name: string;
  source_name: string;
  created_at: string;
  compatibility: string;
  latest: boolean;
  function: string;
  road: string;
  targets: string[];
  classification: string;
  needs_review: boolean;
}

export interface ClassificationLabels { function_type: string; label_road_type: string; label_target_type: string[]; label_actions: string[]; scenario_intent: string }

export interface ClassificationRecord {
  status: string;
  needs_review: boolean;
  final: ClassificationLabels;
  rule: ClassificationLabels;
  llm: (ClassificationLabels & { confidence: number; reason: string }) | null;
  model: string;
  error?: string;
  saved_at?: string;
}

export interface AssetDetail {
  version: {
    asset_id: string; version_id: string; version_number: number; title: string; source_name: string; xosc_name: string; xodr_name: string;
    created_at: string; content_sha256: string; source_sha256: string; compatibility: string; compatibility_detail: string;
    files: { role: string; original_name: string; sha256: string }[];
  };
  classification: ClassificationRecord | null;
  references: string[];
  has_frame: boolean;
  history: { version_id: string; version_number: number; created_at: string; compatibility: string; source_name: string }[];
  standard_export: boolean;
  summary?: { title: string; entities: number; road_length_m: number; lane_count: number; junction_count: number; description: string };
  validation?: Record<string, StandardCheck>;
  error?: string;
}

export interface StandardExportResult {
  ready: boolean;
  audit: {
    validation: Record<string, StandardCheck & { issues?: { path?: string; message: string }[] }>;
    external_dependencies: unknown[];
    runtime_extension_points: unknown[];
    parameter_issues: unknown[];
    unresolved: unknown[];
    [key: string]: unknown;
  };
}

export interface RequirementRecord {
  library_id: string;
  revision: number;
  reviewed_at: string;
  project_id: string;
  document_id: string;
  scene_id: string;
  title: string;
  preferred_text: string;
  classification: Record<string, unknown>;
  structure: Record<string, unknown>;
}

export type DecisionReq = MatchRequest & { asset_id: string; version_id: string; explanation_id?: string; confirmations?: { item: string; reason: string }[] };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

const send = <T,>(method: string, path: string, body?: unknown) =>
  call<T>(path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
const post = <T,>(path: string, body: unknown) => send<T>("POST", path, body);

function form(files: File[], fields: Record<string, string> = {}) {
  const data = new FormData();
  files.forEach((f) => data.append("files", f, f.name));
  Object.entries(fields).forEach(([k, v]) => data.append(k, v));
  return { method: "POST", body: data };
}

export const api = {
  projects: () => call<{ projects: Project[]; last_project_id: string | null }>("/api/projects"),
  selectProject: (id: string) => post<{ project_id: string }>(`/api/projects/${id}/select`, {}),
  documents: (pid: string) => call<PdfDocument[]>(`/api/projects/${pid}/documents`),
  allScenes: (pid: string) => call<Scene[]>(`/api/projects/${pid}/scenes`),
  sceneSchema: () => call<SceneSchema>("/api/scene-schema"),
  revise: (pid: string, did: string, sid: string, edits: Record<string, unknown>) =>
    post<Scene>(`/api/projects/${pid}/documents/${did}/scenes/${sid}/revisions`, { edits }),
  revisions: (pid: string, did: string, sid: string) => call<Revision[]>(`/api/projects/${pid}/documents/${did}/scenes/${sid}/revisions`),
  publish: (pid: string, did: string, sid: string, revision: number) =>
    post<{ library_id: string; revision: number; reviewed_at: string }>(`/api/projects/${pid}/documents/${did}/scenes/${sid}/publish`, { revision }),
  extraction: (pid: string, did: string) => call<ExtractionRecord>(`/api/projects/${pid}/documents/${did}/extraction`),
  batch: (pid: string, did: string) => post<{ signature: string; trace: Trace }>(`/api/projects/${pid}/documents/${did}/batch`, {}),
  batchSave: (pid: string, did: string, signature: string) =>
    post<{ report_id: string }>(`/api/projects/${pid}/documents/${did}/batch/save`, { signature }),
  explanation: (req: DecisionReq & { mode: "evidence" | "structural" | "model" }) => post<Explanation>("/api/explanation", req),
  traceReport: async (req: DecisionReq) => {
    const res = await fetch("/api/trace/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
    return res.text();
  },
  assets: () => call<AssetRow[]>("/api/assets"),
  assetDetail: (v: VersionRef) => call<AssetDetail>(`/api/assets/${v.asset_id}/versions/${v.version_id}`),
  classificationSchema: () => call<Record<"function_type" | "label_road_type" | "label_target_type", string[]>>("/api/classification-schema"),
  classifyRules: (v: VersionRef) => post<ClassificationRecord>(`/api/assets/${v.asset_id}/versions/${v.version_id}/classification/rules`, {}),
  confirmClassification: (v: VersionRef, labels: ClassificationLabels) =>
    send<ClassificationRecord>("PUT", `/api/assets/${v.asset_id}/versions/${v.version_id}/classification`, labels),
  deleteVersion: (v: VersionRef) => send<{ deleted: string }>("DELETE", `/api/assets/${v.asset_id}/versions/${v.version_id}`),
  standardExport: (v: VersionRef) => post<StandardExportResult>(`/api/assets/${v.asset_id}/versions/${v.version_id}/standard-export`, {}),
  requirements: () => call<RequirementRecord[]>("/api/requirements"),
  previewStart: (assetId: string, versionId: string, duration: number) =>
    post<PreviewStatus>(`/api/assets/${assetId}/versions/${versionId}/preview`, { duration }),
  previewStatus: () => call<PreviewStatus>("/api/preview"),
  previewStop: () => post<PreviewStatus>("/api/preview/stop", {}),
  scenes: (pid: string, did: string) => call<Scene[]>(`/api/projects/${pid}/documents/${did}/scenes`),
  library: () => call<Library>("/api/library"),
  search: (req: MatchRequest) => post<SearchResponse>("/api/search", req),
  trace: (req: DecisionReq) => post<Record<string, unknown>>("/api/trace", req),
  createProject: (name: string) => post<Project>("/api/projects", { name }),
  reports: (pid: string) => call<Report[]>(`/api/projects/${pid}/reports`),
  report: (pid: string, rid: string) => call<ReportDetail>(`/api/projects/${pid}/reports/${rid}`),
  overview: () => call<Overview>("/api/overview"),
  saveDecision: (req: DecisionReq) =>
    post<{ report_id: string; saved_to: string }>("/api/decisions", req),

  settings: () => call<Settings>("/api/settings"),
  savePreferences: (p: Partial<Preferences>) => send<Preferences>("PUT", "/api/settings/preferences", p),
  modelList: (d: ModelDraft) => post<{ models: string[] }>("/api/settings/model/models", d),
  modelTest: (d: ModelDraft) => post<{ model: string }>("/api/settings/model/test", d),
  modelSave: (d: ModelDraft) => send<ModelSettings>("PUT", "/api/settings/model", d),
  modelRemoveKey: () => send<ModelSettings>("DELETE", "/api/settings/model/key"),
  previewBrowse: () => post<PreviewSettings>("/api/settings/preview/browse", {}),
  previewDetect: () => post<PreviewSettings>("/api/settings/preview/detect", {}),
  openFolder: (target: "data" | "esmini") => post<{ opened: string }>("/api/settings/open-folder", { target }),

  jobs: (kind?: Job["kind"]) => call<Job[]>(`/api/jobs${kind ? `?kind=${kind}` : ""}`),
  job: (id: string) => call<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => post<Job>(`/api/jobs/${id}/cancel`, {}),
  importPdfs: (pid: string, files: File[], standard: string) => call<Job>(`/api/projects/${pid}/documents`, form(files, { standard })),
  reextract: (pid: string, did: string) => post<Job>(`/api/projects/${pid}/documents/${did}/reextract`, {}),
  importAssets: (files: File[], classify: boolean) => call<Job>("/api/assets/import", form(files, { classify: String(classify) })),
  importDemo: () => post<Job>("/api/assets/import/demo", {}),
  pendingClassification: () => call<{ count: number; versions: { asset_id: string; version_id: string }[] }>("/api/assets/classification/pending"),
  classify: (versions?: { asset_id: string; version_id: string }[], force = false) => post<Job>("/api/assets/classify", { versions, force }),
};

export const urls = {
  page: (pid: string, did: string, page: number, width: number, clip?: number[]) =>
    `/api/projects/${pid}/documents/${did}/pages/${page}?width=${width}${clip ? `&clip=${clip.join(",")}` : ""}`,
  pdf: (pid: string, did: string, page?: number) => `/api/projects/${pid}/documents/${did}/file${page ? `#page=${page}` : ""}`,
  report: (pid: string, rid: string, format: "json" | "html", lang: Lang) =>
    `/api/projects/${pid}/reports/${rid}/download?format=${format}&lang=${lang}`,
  frame: (c: VersionRef, bust?: number) => `/api/assets/${c.asset_id}/versions/${c.version_id}/frame${bust ? `?v=${bust}` : ""}`,
  extraction: (pid: string, did: string) => `/api/projects/${pid}/documents/${did}/extraction/download`,
  classification: (v: VersionRef) => `/api/assets/${v.asset_id}/versions/${v.version_id}/classification/download`,
  standardExport: (v: VersionRef) => `/api/assets/${v.asset_id}/versions/${v.version_id}/standard-export/download`,
  requirement: (libraryId: string) => `/api/requirements/${libraryId}/download`,
  batch: (pid: string, did: string, signature: string, format: "json" | "html", lang: Lang) =>
    `/api/projects/${pid}/documents/${did}/batch/${signature}/download?format=${format}&lang=${lang}`,
  file: (c: VersionRef, role: "scenario" | "road") => `/api/assets/${c.asset_id}/versions/${c.version_id}/files/${role}`,
};

export const LEVEL: Record<Level, { zh: string; en: string; cls: "direct" | "modify" | "review" | "not" }> = {
  direct: { zh: "直接复用", en: "Direct reuse", cls: "direct" },
  modify: { zh: "修改复用", en: "Modify and reuse", cls: "modify" },
  major_modify: { zh: "大幅修改复用", en: "Major modification", cls: "modify" },
  review: { zh: "待复核", en: "Needs review", cls: "review" },
  new_build: { zh: "不可复用", en: "Not reusable", cls: "not" },
};

export const levelLabel = (level: Level, lang: Lang) => LEVEL[level][lang];

// "Needs review" splits into sub-kinds with their own headline, matching the desktop wording.
const REVIEW_TITLE: Record<string, { zh: string; en: string }> = {
  standards: { zh: "文件标准待复核", en: "File standards need review" },
  partial: { zh: "部分已验证 · 待复核", en: "Partially verified · review" },
  undecidable: { zh: "关键结构不足 · 无法判断", en: "Insufficient structure · undecidable" },
  recall: { zh: "文本召回 · 待结构验证", en: "Text recall · verify structure" },
};

export const verdictLabel = (level: Level | "no_candidates" | string, kind: string | undefined, lang: Lang, signedOff = false) =>
  signedOff && level === "review"
    ? lang === "zh" ? "复核后确认" : "Confirmed after review"
    : level === "no_candidates"
    ? lang === "zh" ? "没有候选资产" : "No candidate assets"
    : level === "review" && kind && REVIEW_TITLE[kind]
      ? REVIEW_TITLE[kind][lang]
      : REVIEW_TITLE[level]?.[lang] ?? LEVEL[level as Level]?.[lang] ?? level;

export const verdictClass = (level: string) => LEVEL[level as Level]?.cls ?? (REVIEW_TITLE[level] ? "review" : "not");

export const FACET_LABEL: Record<string, { zh: string; en: string }> = {
  function_type: { zh: "功能", en: "Function" },
  label_road_type: { zh: "道路类型", en: "Road type" },
  label_target_type: { zh: "目标", en: "Target" },
};

export const facetLabel = (key: string, lang: Lang) => FACET_LABEL[key]?.[lang] ?? key;

// The API returns machine vocabulary in English mode; give the common categories readable names.
const CATEGORY_EN: Record<string, string> = {
  unverified: "Unverified fact", function: "Tested function", road: "Road", road_type: "Road type",
  participant_signature: "Participant", participant: "Participant", participant_topology: "Participant relation",
  ego_action: "Ego action", action: "Action", entity: "Participant", trigger: "Trigger", environment: "Environment",
  parameter: "Parameter", parameter_resolution: "Parameter resolution", weather: "Weather", time_of_day: "Time of day",
};
export const categoryLabel = (d: { category: string; category_label: string }, lang: Lang) =>
  lang === "zh" ? d.category_label : CATEGORY_EN[d.category] ?? d.category.replaceAll("_", " ").replace(/^./, (m) => m.toUpperCase());

export const basename = (path: string) => path.split(/[\\/]/).pop() ?? path;
