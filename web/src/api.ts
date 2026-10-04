// Typed client for the FastAPI layer in src/openx_workbench/api.py (proxied at /api by Vite).

export type Level = "direct" | "modify" | "review" | "new_build";
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
  change_cost: number | null;
  reasons: { code: string; label: string }[];
  differences: Difference[];
  standard_checks: { passed: boolean; pending: Record<string, string> };
  scenario: { name: string | null; entities: { name: string; kind: string; category: string | null }[]; actions: string[]; trigger_count: number; parameters: string[]; environment: Record<string, string | number> };
  road: { total_length_m: number; lane_count: number; lane_types: Record<string, number>; geometry_types: Record<string, number>; junction_count: number; road_count: number; revision: string | null };
  has_frame: boolean;
}

export interface Library { asset_count: number; last_import: string | null; encoder: string; facets: Record<string, string[]> }

export interface Report { report_id: string; saved_at: string; asset_id: string | null; version_id: string | null; level: Level | null; scene: { title: string | null; scene_id: string | null; revision: number | null; document_id: string | null } }

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
  scenes: (pid: string, did: string) => call<Scene[]>(`/api/projects/${pid}/documents/${did}/scenes`),
  library: () => call<Library>("/api/library"),
  search: (req: MatchRequest) => post<SearchResponse>("/api/search", req),
  trace: (req: MatchRequest & { asset_id: string; version_id: string }) => post<Record<string, unknown>>("/api/trace", req),
  createProject: (name: string) => post<Project>("/api/projects", { name }),
  reports: (pid: string) => call<Report[]>(`/api/projects/${pid}/reports`),
  saveDecision: (req: MatchRequest & { asset_id: string; version_id: string }) =>
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
  frame: (c: Candidate) => `/api/assets/${c.asset_id}/versions/${c.version_id}/frame`,
  file: (c: Candidate, role: "scenario" | "road") => `/api/assets/${c.asset_id}/versions/${c.version_id}/files/${role}`,
};

export const LEVEL: Record<Level, { zh: string; en: string; cls: "direct" | "modify" | "review" | "not" }> = {
  direct: { zh: "直接复用", en: "Direct reuse", cls: "direct" },
  modify: { zh: "修改复用", en: "Modify and reuse", cls: "modify" },
  review: { zh: "待复核", en: "Needs review", cls: "review" },
  new_build: { zh: "不可复用", en: "Not reusable", cls: "not" },
};

export const levelLabel = (level: Level, lang: Lang) => LEVEL[level][lang];

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
