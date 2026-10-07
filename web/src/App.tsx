import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App as AntApp, Button, ConfigProvider } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import zhCN from "antd/locale/zh_CN";
import enUS from "antd/locale/en_US";
import { buildTheme } from "./theme";
import { api, type Library, type PdfDocument, type Preferences, type Project, type Scene } from "./api";
import { sceneKey, useRequirements, type Scope } from "./useRequirements";
import { useMatching } from "./useMatching";
import { LangContext, useT } from "./i18n";
import { FileNamesContext } from "./names";
import { TopBar, type Page } from "./components/TopBar";
import { HelpDialog } from "./components/HelpDialog";
import { SettingsDialog } from "./components/SettingsDialog";
import { OverviewPage } from "./components/OverviewPage";
import { AssetsPage } from "./components/AssetsPage";
import { RequirementsPanel } from "./components/RequirementsPanel";
import { SearchPanel } from "./components/SearchPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { StartPage } from "./components/StartPage";
import { BindingWorkspace } from "./components/BindingWorkspace";
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
const DEFAULTS: Preferences = { language: "zh", appearance: "system", encoder: "bge", show_file_names: false, auto_preview: false };

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
  const [library, setLibrary] = useState<Library | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [esmini, setEsmini] = useState<boolean>(false);
  const [libraryStamp, setLibraryStamp] = useState(0);
  // The workbench opens on the start page; free-text search and the PDF's binding table are entered from it,
  // and finding an asset by hand (the rule-based search of one scene) from the table.
  const [mode, setMode] = useState<"start" | "search" | "pdf" | "manual">("start");
  const [searchFrom, setSearchFrom] = useState<DOMRect | null>(null);
  // The PDFs the binding table shows together, and the row to select when it opens.
  const [bindDocs, setBindDocs] = useState<string[]>([]);
  const [bindFocus, setBindFocus] = useState<string | null>(null);

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
  // Only finding by hand shows them, so the binding table ranks nothing.
  const runKey = scene && mode === "manual" ? `${sceneKey(scene)}@${scene.revision}:${lang}:${prefs.encoder}:${libraryStamp}` : "";
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
  /** The binding table of one PDF. */
  const enterWorkflow = (documentId: string) => {
    req.chooseDoc(documentId);
    setBindDocs([documentId]);
    setBindFocus(null);
    setMode("pdf");
  };
  /** Find an asset for one scene by hand: the rule-based search with the scene selected. */
  const enterManual = (documentId: string, sceneId: string) => {
    const key = `${documentId}/${sceneId}`;
    setLeftTab("scenes");
    setBindFocus(key);
    if (req.scope === "pdf" && req.docId === documentId && scenes.some((s) => sceneKey(s) === key)) {
      pickScene(key);
    } else {
      req.openLater(key);
      req.chooseDoc(documentId);
    }
    setMode("manual");
  };
  /** Back to the binding table at the scene shown, with its PDF among those the table shows. */
  const backToTable = () => {
    if (scene) {
      setBindFocus(sceneKey(scene));
      if (!bindDocs.includes(scene.document_id)) setBindDocs([scene.document_id]);
    }
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
  /** A clause's row in the binding table, of this project or another one. */
  const openSceneIn = (pid: string, documentId: string, sceneId: string) => {
    setPage("workbench");
    setBindDocs([documentId]);
    setBindFocus(`${documentId}/${sceneId}`);
    setMode("pdf");
    if (pid !== projectId) {
      switchProject(pid);
      req.openLater(`${documentId}/${sceneId}`, documentId);
      api.selectProject(pid).catch(() => undefined);
    } else {
      req.chooseDoc(documentId);
    }
  };
  const openScene = (documentId: string, sceneId: string) => projectId && openSceneIn(projectId, documentId, sceneId);
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
  const ref: SceneRef | null = projectId && doc && scene ? { projectId, doc, scene } : null;

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
          onImported={(ids) => {
            if (projectId) req.loadDocs(projectId, ids[ids.length - 1]);
            setBindDocs(ids.slice(-1));
            setBindFocus(null);
            setMode("pdf");
          }} />
      )}
      {page === "workbench" && mode === "search" && (
        <SearchPage search={textSearch} library={library} from={searchFrom} esmini={esmini} onBack={goHome}
          onSettings={() => setDialog("settings")} onLibraryChanged={libraryChanged} />
      )}
      {page === "workbench" && mode === "pdf" && projectId && (
        <BindingWorkspace projectId={projectId} docs={req.docs} picked={bindDocs} onPicked={(ids) => { setBindDocs(ids); setBindFocus(null); }}
          focus={bindFocus} esmini={esmini} onSettings={() => setDialog("settings")}
          onDocsChanged={(select) => req.loadDocs(projectId, select)} onManual={enterManual} />
      )}
      {page === "workbench" && mode === "manual" && (<>
      <nav className="ox-steps manual-bar">
        <Button type="text" size="small" icon={<ArrowLeftOutlined />} onClick={backToTable}>{t("返回复用评估", "Back to the assessment")}</Button>
        <span className="muted">
          {t("手动检索：在资产库中检索并查看规则逐项比对；选定素材后，点击右下角“采用为本条款的复用素材”。",
            "Manual search: search the library and see the rule-by-rule comparison; pick a candidate and press \"Adopt for this clause\".")}
        </span>
      </nav>
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
          onBound={backToTable}
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
