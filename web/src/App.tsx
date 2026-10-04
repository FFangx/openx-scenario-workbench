import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import enUS from "antd/locale/en_US";
import { buildTheme } from "./theme";
import { api, type Library, type PdfDocument, type Preferences, type Project, type Scene, type SearchResponse } from "./api";
import { LangContext, useT } from "./i18n";
import { StepBar, TopBar, type Page } from "./components/TopBar";
import { HelpDialog } from "./components/HelpDialog";
import { SettingsDialog } from "./components/SettingsDialog";
import { OverviewPage } from "./components/OverviewPage";
import { RequirementsPanel } from "./components/RequirementsPanel";
import { SearchPanel } from "./components/SearchPanel";
import { DecisionPanel } from "./components/DecisionPanel";

function useSystemDark() {
  const q = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return dark;
}

const CACHE = "openx.preferences";
const DEFAULTS: Preferences = { language: "zh", appearance: "system", encoder: "bge" };

/** The server owns preferences; a local copy only avoids a flash of the wrong theme and language on load. */
function cachedPreferences(): Preferences {
  try {
    const value = JSON.parse(localStorage.getItem(CACHE) ?? "null");
    if (value && typeof value === "object") return { ...DEFAULTS, ...value };
  } catch { /* storage unavailable */ }
  return DEFAULTS;
}

export default function Root() {
  const [prefs, setPrefs] = useState<Preferences>(cachedPreferences);
  const systemDark = useSystemDark();
  const dark = prefs.appearance === "dark" || (prefs.appearance === "system" && systemDark);

  useEffect(() => {
    api.settings().then((s) => setPrefs(s.preferences)).catch(() => undefined);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.lang = prefs.language === "zh" ? "zh-CN" : "en";
    try { localStorage.setItem(CACHE, JSON.stringify(prefs)); } catch { /* ignore */ }
  }, [dark, prefs]);

  const changePrefs = useCallback((change: Partial<Preferences>) => {
    setPrefs((p) => ({ ...p, ...change }));
    api.savePreferences(change).then(setPrefs).catch(() => undefined);
  }, []);

  const themeConfig = useMemo(() => buildTheme(dark), [dark]);

  return (
    <ConfigProvider theme={themeConfig} locale={prefs.language === "zh" ? zhCN : enUS} button={{ autoInsertSpace: false }}>
      <LangContext.Provider value={prefs.language}>
        <AntApp>
          <Workbench prefs={prefs} onPrefs={changePrefs} />
        </AntApp>
      </LangContext.Provider>
    </ConfigProvider>
  );
}

export interface SceneRef { projectId: string; doc: PdfDocument; scene: Scene }

export type Scope = "pdf" | "all";
export type LeftTab = "scenes" | "facts" | "doc";
const keyOf = (s: Scene) => `${s.document_id}/${s.scene_id}`;

function Workbench({ prefs, onPrefs }: { prefs: Preferences; onPrefs: (p: Partial<Preferences>) => void }) {
  const { message } = AntApp.useApp();
  const { t } = useT();
  const lang = prefs.language;
  const [page, setPage] = useState<Page>("workbench");
  const [dialog, setDialog] = useState<"help" | "settings" | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [docs, setDocs] = useState<PdfDocument[]>([]);
  const [docId, setDocId] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("pdf");
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [leftTab, setLeftTab] = useState<LeftTab>("scenes");
  const [queue, setQueue] = useState<string[]>([]);
  const [library, setLibrary] = useState<Library | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [esmini, setEsmini] = useState<boolean>(false);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const searchSeq = useRef(0);
  const pending = useRef<string | null>(null);

  const scene = scenes.find((s) => keyOf(s) === selected) ?? null;
  const doc = docs.find((d) => d.document_id === (scene?.document_id ?? docId)) ?? null;
  const cand = result?.results.find((c) => c.asset_id === activeKey) ?? null;

  const loadLibrary = useCallback(() => api.library().then(setLibrary), []);
  const loadTools = useCallback(() => api.settings().then((s) => setEsmini(!!s.preview.executable)).catch(() => undefined), []);

  useEffect(() => {
    Promise.all([api.projects(), loadLibrary()])
      .then(([p]) => {
        setProjects(p.projects);
        setProjectId(p.last_project_id ?? p.projects[0]?.project_id ?? null);
        setOnline(true);
      })
      .catch((e: Error) => {
        setOnline(false);
        message.error(t(`无法连接工作台服务：${e.message}`, `Cannot reach the workbench API: ${e.message}`));
      });
    loadTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message]);

  const loadDocs = useCallback((pid: string, select?: string) =>
    api.documents(pid).then((d) => {
      setDocs(d);
      setDocId(select && d.some((x) => x.document_id === select) ? select : d[0]?.document_id ?? null);
      if (d.length < 2) setScope("pdf");
    }).catch((e: Error) => message.error(e.message)), [message]);

  useEffect(() => {
    if (projectId) loadDocs(projectId);
  }, [projectId, loadDocs]);

  /** Reload the queue; keep the current selection when it still exists, else enter at the requested or first scene. */
  const loadScenes = useCallback((keep: string | null) => {
    if (!projectId || (scope === "pdf" && !docId)) {
      setScenes([]);
      setSelected(null);
      return;
    }
    const request = scope === "all" ? api.allScenes(projectId) : api.scenes(projectId, docId!);
    request.then((s) => {
      setScenes(s);
      const wanted = pending.current ?? keep;
      pending.current = null;
      const next = s.find((x) => keyOf(x) === wanted) ?? s[0];
      setSelected(next ? keyOf(next) : null);
      if (next && keyOf(next) !== keep) setQuery(next.title);
    }).catch((e: Error) => message.error(e.message));
  }, [projectId, docId, scope, message]);

  useEffect(() => {
    setResult(null);
    loadScenes(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, docId, scope]);

  const runSearch = useCallback(
    (opts: { text?: string; filters?: Record<string, string> } = {}) => {
      if (!projectId) return;
      const seq = ++searchSeq.current;
      setSearching(true);
      setSearchError(null);
      api
        .search({
          project_id: projectId,
          document_id: scene?.document_id,
          scene_id: scene?.scene_id,
          revision: scene?.revision,
          text: opts.text ?? query,
          filters: opts.filters ?? filters,
          lang,
        })
        .then((r) => {
          if (seq !== searchSeq.current) return;
          setResult(r);
          const first = r.results[0]?.asset_id ?? null;
          setActiveKey(first);
          setChecked(first ? [first] : []);
        })
        .catch((e: Error) => seq === searchSeq.current && (setSearchError(e.message), setResult(null)))
        .finally(() => seq === searchSeq.current && setSearching(false));
    },
    [projectId, scene, query, filters, lang],
  );

  // A new scene revision (or language, or encoder) re-runs matching so the middle and right columns never show stale results.
  const sceneKey = scene ? `${keyOf(scene)}@${scene.revision}:${lang}:${prefs.encoder}` : "";
  useEffect(() => {
    if (sceneKey) runSearch({ text: scene!.title });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneKey]);

  const pickScene = (key: string) => {
    const s = scenes.find((x) => keyOf(x) === key);
    if (!s) return;
    setSelected(key);
    setQuery(s.title);
  };
  /** Free text search: matching without a requirement gives text recall only, never a reuse decision. */
  const clearScene = () => {
    setSelected(null);
    setResult(null);
    setActiveKey(null);
    setQuery("");
  };
  const activate = (key: string) => {
    setActiveKey(key);
    setChecked((prev) => (prev.includes(key) ? prev : [...prev, key]));
  };
  const changeFilters = (f: Record<string, string>) => {
    setFilters(f);
    runSearch({ filters: f });
  };
  // Clear the document in the same render, so scenes are never requested with the previous project's document.
  const switchProject = (id: string) => {
    setDocs([]);
    setDocId(null);
    setScenes([]);
    setSelected(null);
    setResult(null);
    setScope("pdf");
    setQuery("");
    setProjectId(id);
  };
  const pickProject = (id: string) => {
    switchProject(id);
    api.selectProject(id).catch(() => undefined);
  };
  const openScene = (documentId: string, sceneId: string) => {
    setPage("workbench");
    setLeftTab("facts");
    const key = `${documentId}/${sceneId}`;
    if (scenes.some((s) => keyOf(s) === key)) {
      pickScene(key);
    } else {
      pending.current = key;
      setScope("pdf");
      setDocId(documentId);
    }
  };
  const projectCreated = (p: Project) => {
    setProjects((all) => [...all, p]);
    switchProject(p.project_id);
  };
  const sceneChanged = (s: Scene) => {
    setScenes((all) => all.map((x) => (keyOf(x) === keyOf(s) ? s : x)));
    loadScenes(keyOf(s));
  };
  const nextKey = scene ? queue[queue.indexOf(keyOf(scene)) + 1] ?? null : null;

  const ref: SceneRef | null = projectId && doc && scene ? { projectId, doc, scene } : null;
  const step = cand ? 2 : result ? 1 : 0;

  return (
    <div className="ox-root">
      <TopBar
        page={page}
        onPage={setPage}
        onLang={(language) => onPrefs({ language })}
        projects={projects}
        projectId={projectId}
        onProject={pickProject}
        onCreated={projectCreated}
        onHelp={() => setDialog("help")}
        onSettings={() => setDialog("settings")}
      />
      <HelpDialog open={dialog === "help"} onClose={() => setDialog(null)} />
      <SettingsDialog open={dialog === "settings"} onClose={() => { setDialog(null); loadTools(); }} preferences={prefs} onPreferences={onPrefs} />
      {page === "workbench" && (<>
      <StepBar active={step} projectId={projectId} docs={docs} docId={docId} onDoc={(id) => { setScope("pdf"); setDocId(id); }} onAllDecisions={() => setPage("overview")} />
      <main className="ox-main">
        <RequirementsPanel
          projectId={projectId}
          docs={docs}
          doc={doc}
          onDoc={(id) => { setScope("pdf"); setDocId(id); }}
          onDocsChanged={(select) => projectId && loadDocs(projectId, select)}
          scope={scope}
          onScope={setScope}
          scenes={scenes}
          scene={scene}
          selectedKey={selected}
          onPick={pickScene}
          onQueue={setQueue}
          tab={leftTab}
          onTab={setLeftTab}
          onSceneChanged={sceneChanged}
        />
        <SearchPanel
          query={query}
          onQuery={setQuery}
          onSearch={() => runSearch()}
          onReset={() => {
            const text = scene?.title ?? "";
            setQuery(text);
            setFilters({});
            runSearch({ text, filters: {} });
          }}
          filters={filters}
          onFilters={changeFilters}
          library={library}
          online={online}
          result={result}
          searching={searching}
          error={searchError}
          canSearch={!!projectId && (!!scene || !!query.trim())}
          scene={scene}
          onClearScene={clearScene}
          activeKey={activeKey}
          onActivate={activate}
          checked={checked}
          onChecked={setChecked}
          active={cand}
          esmini={esmini}
          onSettings={() => setDialog("settings")}
        />
        <DecisionPanel
          sceneRef={ref}
          cand={cand}
          searching={searching}
          query={query}
          lang={lang}
          onReviewFacts={() => setLeftTab("facts")}
          onSaved={() => scene && loadScenes(keyOf(scene))}
          onNext={nextKey ? () => pickScene(nextKey) : undefined}
        />
      </main>
      </>)}
      {page === "overview" && <OverviewPage projectId={projectId} onNavigate={setPage} onOpenScene={openScene} />}
    </div>
  );
}
