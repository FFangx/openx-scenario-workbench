// Typed client for the FastAPI layer in src/openx_workbench/api.py (proxied at /api by Vite).
// The shapes come from the backend's OpenAPI document: run `npm run gen:api` after changing api_schemas.py.
import type { components } from "./api-types";

type Schemas = components["schemas"];

export type Project = Schemas["Project"];
export type PdfDocument = Schemas["PdfDocument"];
export type Evidence = Schemas["Evidence"];
/** A scene as the review queue lists it; a search response carries the same scene without queue state. */
export type Scene = Schemas["QueuedScene"];
export type Participant = Schemas["SceneParticipant"];
export type SceneStructure = Schemas["SceneStructure"];
/** What a spatial fact rests on: a quote, the reasoning for an implied one, and why to check it. */
export type FieldEvidence = Schemas["FieldEvidence"];
export type SceneSchema = Schemas["SceneSchema"];
export type Revision = Schemas["Revision"];
export type ExtractionRecord = Schemas["ExtractionRecord"];
export type Explanation = Schemas["Explanation"];
export type PreviewStatus = Schemas["PreviewStatus"];
export type Difference = Schemas["Difference"];
export type ReviewItem = Schemas["ReviewItem"];
export type StandardCheck = Schemas["StandardCheck"];
export type Candidate = Schemas["Candidate"];
export type Level = Candidate["level"];
export type Library = Schemas["Library"];
export type Report = Schemas["Report"];
export type TraceSource = Schemas["TraceSource"];
export type TraceCandidate = Schemas["TraceCandidate"];
export type Trace = Schemas["Trace"];
export type ReportDetail = Schemas["ReportDetail"];
export type Overview = Schemas["Overview"];
export type SearchResponse = Schemas["SearchResponse"];
export type MatchRequest = Schemas["MatchRequest"];
export type DecisionReq = Schemas["DecisionRequest"];
export type ModelSettings = Schemas["ModelSettings"];
/** A blank api_key keeps the saved key, but only while the endpoint is unchanged. */
export type ModelDraft = Schemas["ModelDraft"];
export type ModelInfo = Schemas["ModelInfo"];
export type PreviewSettings = Schemas["PreviewSettings"];
export type Preferences = Schemas["Preferences"];
export type Lang = Preferences["language"];
export type Appearance = Preferences["appearance"];
export type Encoder = Preferences["encoder"];
export type Settings = Schemas["Settings"];
export type SchemaStatus = Schemas["SchemaStatus"];
export type SchemaCheck = Schemas["SchemaCheck"];
export type SchemaVerdictChange = Schemas["SchemaVerdictChange"];
export type Job = Schemas["Job"];
export type JobStatus = Job["status"];
export type ImportReport = Schemas["ImportReport"];
export type AssetRow = Schemas["AssetRow"];
export type ClassificationLabels = Schemas["ClassificationLabels"];
export type ClassificationRecord = Schemas["ClassificationRecord"];
export type AssetDetail = Schemas["AssetDetail"];
export type StandardExportResult = Schemas["StandardExportResult"];
export type RequirementRecord = Schemas["RequirementRecord"];
export type GroupBindings = Schemas["GroupBindings"];
export type SceneBinding = Schemas["SceneBinding"];
export type BindingSuggestion = Schemas["BindingSuggestion"];
export type SuggestedCandidate = Schemas["SuggestedCandidate"];
export type ConfirmedBinding = Schemas["ConfirmedBinding"];
export type BindingStatus = ConfirmedBinding["status"];
export type AssetBinding = Schemas["AssetBinding"];
export type BindingCoverage = Schemas["BindingCoverage"];
/** What a person confirms for one scene: the bound asset versions, the preferred one, and what to change. */
export interface BindingDraft { status: BindingStatus; assets: { asset_id: string; version_id: string }[]; preferred: string | null; changes: string }
/** A scene of one of the PDFs shown together. */
export interface SceneRef { document_id: string; scene_id: string }

/** An asset version as the client addresses it; a search candidate may have no stored version. */
export interface VersionRef { asset_id: string; version_id: string | null }

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
  batch: (pid: string, dids: string[]) => post<{ signature: string; trace: Trace }>(`/api/projects/${pid}/batch`, { document_ids: dids }),
  batchSave: (pid: string, signature: string) => post<{ report_id: string }>(`/api/projects/${pid}/batch/save`, { signature }),
  bindings: (pid: string, dids: string[]) =>
    call<GroupBindings>(`/api/projects/${pid}/bindings?${dids.map((d) => `document_ids=${encodeURIComponent(d)}`).join("&")}`),
  suggestBindings: (pid: string, dids: string[], scenes?: SceneRef[]) =>
    post<Job>(`/api/projects/${pid}/bindings/suggest`, { document_ids: dids, scenes: scenes ?? null }),
  acceptBindings: (pid: string, dids: string[], scenes?: SceneRef[]) =>
    post<GroupBindings>(`/api/projects/${pid}/bindings/accept`, { document_ids: dids, scenes: scenes ?? null }),
  confirmBinding: (pid: string, s: SceneRef, draft: BindingDraft) =>
    send<SceneBinding>("PUT", `/api/projects/${pid}/documents/${s.document_id}/scenes/${s.scene_id}/binding`, draft),
  unbind: (pid: string, s: SceneRef) =>
    send<SceneBinding>("DELETE", `/api/projects/${pid}/documents/${s.document_id}/scenes/${s.scene_id}/binding`),
  assetBindings: (assetId: string) => call<AssetBinding[]>(`/api/assets/${assetId}/bindings`),
  coverage: (pid: string) => call<BindingCoverage>(`/api/projects/${pid}/bindings/coverage`),
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
  modelList: (d: ModelDraft) => post<Schemas["ModelList"]>("/api/settings/model/models", d),
  modelTest: (d: ModelDraft) => post<{ model: string }>("/api/settings/model/test", d),
  modelSave: (d: ModelDraft) => send<ModelSettings>("PUT", "/api/settings/model", d),
  modelRemoveKey: () => send<ModelSettings>("DELETE", "/api/settings/model/key"),
  previewBrowse: () => post<PreviewSettings>("/api/settings/preview/browse", {}),
  previewDetect: () => post<PreviewSettings>("/api/settings/preview/detect", {}),
  openFolder: (target: "data" | "esmini") => post<{ opened: string }>("/api/settings/open-folder", { target }),
  schemaStatus: () => call<SchemaStatus>("/api/settings/schemas"),
  schemaCheck: () => post<SchemaCheck>("/api/settings/schemas/check", {}),
  schemaPreview: (revision: string) => post<Job>("/api/settings/schemas/preview", { revision }),
  schemaApply: (revision: string) => post<SchemaStatus>("/api/settings/schemas/apply", { revision }),
  schemaRollback: () => post<SchemaStatus>("/api/settings/schemas/rollback", {}),
  schemaDiscard: () => send<SchemaStatus>("DELETE", "/api/settings/schemas/staged"),

  jobs: (kind?: Job["kind"]) => call<Job[]>(`/api/jobs${kind ? `?kind=${kind}` : ""}`),
  job: (id: string) => call<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => post<Job>(`/api/jobs/${id}/cancel`, {}),
  startPreviews: (retryFailed = false) => post<Job>("/api/previews", { retry_failed: retryFailed }),
  importPdfs: (pid: string, files: File[], standard: string) => call<Job>(`/api/projects/${pid}/documents`, form(files, { standard })),
  reextract: (pid: string, did: string) => post<Job>(`/api/projects/${pid}/documents/${did}/reextract`, {}),
  importAssets: (files: File[]) => call<Job>("/api/assets/import", form(files)),
  importDemo: () => post<Job>("/api/assets/import/demo", {}),
  pendingClassification: () => call<{ count: number; versions: { asset_id: string; version_id: string }[] }>("/api/assets/classification/pending"),
  relabel: (versions?: { asset_id: string; version_id: string }[], force = false) => post<Job>("/api/assets/classify", { versions, force }),
};

export const urls = {
  page: (pid: string, did: string, page: number, width: number, clip?: number[]) =>
    `/api/projects/${pid}/documents/${did}/pages/${page}?width=${width}${clip ? `&clip=${clip.join(",")}` : ""}`,
  pdf: (pid: string, did: string, page?: number) => `/api/projects/${pid}/documents/${did}/file${page ? `#page=${page}` : ""}`,
  report: (pid: string, rid: string, format: "json" | "html", lang: Lang) =>
    `/api/projects/${pid}/reports/${rid}/download?format=${format}&lang=${lang}`,
  frame: (c: VersionRef, bust?: number) => `/api/assets/${c.asset_id}/versions/${c.version_id}/frame${bust ? `?v=${bust}` : ""}`,
  roadDrawing: (c: VersionRef) => `/api/assets/${c.asset_id}/versions/${c.version_id}/road-drawing`,
  extraction: (pid: string, did: string) => `/api/projects/${pid}/documents/${did}/extraction/download`,
  classification: (v: VersionRef) => `/api/assets/${v.asset_id}/versions/${v.version_id}/classification/download`,
  standardExport: (v: VersionRef) => `/api/assets/${v.asset_id}/versions/${v.version_id}/standard-export/download`,
  requirement: (libraryId: string) => `/api/requirements/${libraryId}/download`,
  bindingsExport: (pid: string, dids: string[], format: "csv" | "html", lang: Lang) =>
    `/api/projects/${pid}/bindings/export?${dids.map((d) => `document_ids=${encodeURIComponent(d)}`).join("&")}&format=${format}&lang=${lang}`,
  batch: (pid: string, signature: string, format: "json" | "html", lang: Lang) =>
    `/api/projects/${pid}/batch/${signature}/download?format=${format}&lang=${lang}`,
  file: (c: VersionRef, role: "scenario" | "road") => `/api/assets/${c.asset_id}/versions/${c.version_id}/files/${role}`,
};

// The rules' verdicts on the four reuse levels the model and a person use; the sub-kind of a
// review and a major modification are told by the explanation under the level, not by its name.
export const LEVEL: Record<Level, { zh: string; en: string; cls: ReuseClass }> = {
  direct: { zh: "直接复用", en: "Direct reuse", cls: "direct" },
  modify: { zh: "修改复用", en: "Modify and reuse", cls: "modify" },
  major_modify: { zh: "修改复用", en: "Modify and reuse", cls: "modify" },
  review: { zh: "无法判断", en: "Undetermined", cls: "review" },
  new_build: { zh: "不适用", en: "Not applicable", cls: "not" },
};
export type ReuseClass = "direct" | "modify" | "review" | "not";
export const REUSE_CLASSES: ReuseClass[] = ["direct", "modify", "review", "not"];
export const classLabel = (cls: ReuseClass, lang: Lang) => Object.values(LEVEL).find((l) => l.cls === cls)![lang];

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
  background_participant: "Background participant", placement: "Placement", ego_action: "Ego action", action: "Action", entity: "Participant", trigger: "Trigger", environment: "Environment",
  parameter: "Parameter", parameter_resolution: "Parameter resolution", weather: "Weather", time_of_day: "Time of day",
  ego_route: "Ego route", variant: "Either-or choice", figure: "Figure",
};
export const categoryLabel = (d: { category: string; category_label: string }, lang: Lang) =>
  lang === "zh" ? d.category_label : CATEGORY_EN[d.category] ?? d.category.replaceAll("_", " ").replace(/^./, (m) => m.toUpperCase());

export const basename = (path: string) => path.split(/[\\/]/).pop() ?? path;
