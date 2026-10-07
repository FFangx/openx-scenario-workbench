import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import enUS from "antd/locale/en_US";
import { buildTheme } from "./theme";
import { api, type Library, type PdfDocument, type Preferences, type Project, type Scene } from "./api";
import { sceneKey, useRequirements, type Scope } from "./useRequirements";
import { useMatching } from "./useMatching";
import { LangContext, useT } from "./i18n";
import { FileNamesContext } from "./names";
import { StepBar, TopBar, type Page } from "./components/TopBar";
import { HelpDialog } from "./components/HelpDialog";
import { SettingsDialog } from "./components/SettingsDialog";
import { OverviewPage } from "./components/OverviewPage";
import { AssetsPage } from "./components/AssetsPage";
import { RequirementsPanel } from "./components/RequirementsPanel";
import { SearchPanel } from "./components/SearchPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { StartPage } from "./components/StartPage";
import { SearchPage } from "./components/SearchPage";

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
const DEFAULTS: Preferences = { language: "zh", appearance: "system", encoder: "bge", show_file_names: false };

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
        <FileNamesContext.Provider value={prefs.show_file_names}>
          <AntApp>
            <Workbench prefs={prefs} onPrefs={changePrefs} />
          </AntApp>
        </FileNamesContext.Provider>
      </LangContext.Provider>
    </ConfigProvider>
  );
}

export interface SceneRef { projectId: string; doc: PdfDocument; scene: Scene }

export type { Scope };
export type LeftTab = "scenes" | "facts" | "doc";

function Workbench({ prefs, onPrefs }: { prefs: Preferences; onPrefs: (p: Partial<Preferences>) => void }) {
  const { message } = AntApp.useApp();
  const { t } = useT();
  const lang = prefs.language;
  const [page, setPage] = useState<Page>("workbench");
  const [dialog, setDialog] = useState<"help" | "settings" | null>(null);
  const [leftTab, setLeftTab] = useState<LeftTab>("scenes");
  const [queue, setQueue] = useState<string[]>([]);
  const [library, setLibrary] = useState<Library | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [esmini, setEsmini] = useState<boolean>(false);
  const [libraryStamp, setLibraryStamp] = useState(0);
  // The workbench opens on the start page; free-text search and the PDF workflow are entered from it.
  const [mode, setMode] = useState<"start" | "search" | "pdf">("start");
  const [searchFrom, setSearchFrom] = useState<DOMRect | null>(null);

  // Entering another scene puts its title in the search box; the matching hook owns that box.
  const enterQuery = useRef<(title: string) => void>(() => undefined);
  const req = useRequirements({ onEnter: (s) => enterQuery.current(s.title), onError: (text) => message.error(text) });
  const { projectId, docId, scope, scenes, scene, doc } = req;
  const match = useMatching({ projectId, scene, lang });
  const textSearch = useMatching({ projectId, scene: null, lang, topK: 24 });
  enterQuery.current = match.setQuery;
  const { result, runSearch } = match;
  const cand = result?.results.find((c) => c.asset_id === match.activeKey) ?? null;

  const loadLibrary = useCallback(() => api.library().then(setLibrary), []);
  const loadTools = useCallback(() => api.settings().then((s) => setEsmini(!!s.preview.executable)).catch(() => undefined), []);

  useEffect(() => {
    Promise.all([api.projects(), loadLibrary()])
      .then(([p]) => {
        req.setProjects(p.projects, p.last_project_id ?? p.projects[0]?.project_id ?? null);
        setOnline(true);
      })
      .catch((e: Error) => {
        setOnline(false);
        message.error(t(`无法连接工作台服务：${e.message}`, `Cannot reach the workbench API: ${e.message}`));
      });
    loadTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message]);

  useEffect(() => {
    match.clear();
    req.loadScenes(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, docId, scope]);

  // A new scene revision (or language, or encoder) re-runs matching so the middle and right columns never show stale results.
  const runKey = scene ? `${sceneKey(scene)}@${scene.revision}:${lang}:${prefs.encoder}:${libraryStamp}` : "";
  useEffect(() => {
    if (runKey) runSearch({ text: scene!.title });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey]);

  const pickScene = (key: string) => {
    const s = scenes.find((x) => sceneKey(x) === key);
    if (!s) return;
    req.select(key);
    match.setQuery(s.title);
  };
  /** Free text search: matching without a requirement gives text recall only, never a reuse decision. */
  const startSearch = (text: string, from: DOMRect | null) => {
    textSearch.setQuery(text);
    setSearchFrom(from);
    setMode("search");
    if (text.trim()) textSearch.runSearch({ text });
  };
  const enterWorkflow = (documentId?: string) => {
    if (documentId) req.chooseDoc(documentId);
    setMode("pdf");
  };
  const goHome = () => {
    setPage("workbench");
    setMode("start");
  };
  const changeFilters = (f: Record<string, string>) => {
    match.setFilters(f);
    runSearch({ filters: f });
  };
  const switchProject = (id: string) => {
    req.switchProject(id);
    match.clear();
    match.setQuery("");
  };
  const pickProject = (id: string) => {
    switchProject(id);
    setMode("start");
    api.selectProject(id).catch(() => undefined);
  };
  /** After imports, deletions or relabelling: refresh facets and re-rank, so no stale candidate stays on screen. */
  const libraryChanged = useCallback(() => {
    loadLibrary();
    setLibraryStamp((n) => n + 1);
    match.clear();
    textSearch.clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadLibrary]);
  const openSceneIn = (pid: string, documentId: string, sceneId: string) => {
    if (pid === projectId) {
      openScene(documentId, sceneId);
      return;
    }
    setPage("workbench");
    setMode("pdf");
    setLeftTab("facts");
    switchProject(pid);
    req.openLater(`${documentId}/${sceneId}`, documentId);
    api.selectProject(pid).catch(() => undefined);
  };
  const openScene = (documentId: string, sceneId: string) => {
    setPage("workbench");
    setMode("pdf");
    setLeftTab("facts");
    const key = `${documentId}/${sceneId}`;
    if (scenes.some((s) => sceneKey(s) === key)) {
      pickScene(key);
    } else {
      req.openLater(key);
      req.chooseDoc(documentId);
    }
  };
  const projectCreated = (p: Project) => {
    req.projectCreated(p);
    setMode("start");
    match.clear();
    match.setQuery("");
  };
  const sceneChanged = (s: Scene) => {
    req.replaceScene(s);
    req.loadScenes(sceneKey(s));
  };
  const nextKey = scene ? queue[queue.indexOf(sceneKey(scene)) + 1] ?? null : null;

  const ref: SceneRef | null = projectId && doc && scene ? { projectId, doc, scene } : null;
  const step = cand ? 2 : result ? 1 : 0;

  return (
    <div className="ox-root">
      <TopBar
        page={page}
        onPage={setPage}
        onLang={(language) => onPrefs({ language })}
        projects={req.projects}
        projectId={projectId}
        onProject={pickProject}
        onCreated={projectCreated}
        onHelp={() => setDialog("help")}
        onSettings={() => setDialog("settings")}
        onHome={goHome}
      />
      <HelpDialog open={dialog === "help"} onClose={() => setDialog(null)} />
      <SettingsDialog open={dialog === "settings"} onClose={() => { setDialog(null); loadTools(); }} preferences={prefs} onPreferences={onPrefs} />
      {page === "workbench" && mode === "start" && (
        <StartPage projectId={projectId} docs={req.docs} library={library} onSearch={startSearch} onOpenDoc={enterWorkflow}
          onImported={(ids) => { if (projectId) req.loadDocs(projectId, ids[ids.length - 1]); setMode("pdf"); }} />
      )}
      {page === "workbench" && mode === "search" && (
        <SearchPage search={textSearch} library={library} from={searchFrom} esmini={esmini} onBack={goHome}
          onSettings={() => setDialog("settings")} onLibraryChanged={libraryChanged} />
      )}
      {page === "workbench" && mode === "pdf" && (<>
      <StepBar active={step} projectId={projectId} docs={req.docs} docId={docId} onDoc={req.chooseDoc} onAllDecisions={() => setPage("overview")} />
      <main className="ox-main">
        <RequirementsPanel
          projectId={projectId}
          docs={req.docs}
          doc={doc}
          onDoc={req.chooseDoc}
          onDocsChanged={(select) => projectId && req.loadDocs(projectId, select)}
          scope={scope}
          onScope={req.setScope}
          scenes={scenes}
          scene={scene}
          selectedKey={req.selected}
          onPick={pickScene}
          onQueue={setQueue}
          tab={leftTab}
          onTab={setLeftTab}
          onSceneChanged={sceneChanged}
        />
        <SearchPanel
          query={match.query}
          onQuery={match.setQuery}
          onSearch={() => runSearch()}
          onReset={() => {
            const text = scene?.title ?? "";
            match.setQuery(text);
            match.setFilters({});
            runSearch({ text, filters: {} });
          }}
          filters={match.filters}
          onFilters={changeFilters}
          library={library}
          online={online}
          result={result}
          searching={match.searching}
          error={match.error}
          canSearch={!!projectId && (!!scene || !!match.query.trim())}
          scene={scene}
          onClearScene={() => startSearch(textSearch.query, null)}
          activeKey={match.activeKey}
          onActivate={match.activate}
          checked={match.checked}
          onChecked={match.setChecked}
          active={cand}
          esmini={esmini}
          onSettings={() => setDialog("settings")}
        />
        <DecisionPanel
          sceneRef={ref}
          cand={cand}
          searching={match.searching}
          query={match.query}
          lang={lang}
          onReviewFacts={() => setLeftTab("facts")}
          onSaved={() => scene && req.loadScenes(sceneKey(scene))}
          onNext={nextKey ? () => pickScene(nextKey) : undefined}
        />
      </main>
      </>)}
      {page === "overview" && <OverviewPage projectId={projectId} onNavigate={setPage} onOpenScene={openScene} />}
      {page === "assets" && (
        <AssetsPage esmini={esmini} onSettings={() => setDialog("settings")} onLibraryChanged={libraryChanged} onOpenScene={openSceneIn} />
      )}
    </div>
  );
}
