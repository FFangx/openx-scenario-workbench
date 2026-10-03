import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App as AntApp, ConfigProvider } from "antd";
import { buildTheme } from "./theme";
import { api, type Lang, type Library, type PdfDocument, type Project, type Scene, type SearchResponse } from "./api";
import { StepBar, TopBar, type Appearance } from "./components/TopBar";
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

function readAppearance(): Appearance {
  try {
    const v = localStorage.getItem("openx.appearance");
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch { /* storage unavailable */ }
  return "light";
}

export default function Root() {
  const [appearance, setAppearance] = useState<Appearance>(readAppearance);
  const systemDark = useSystemDark();
  const dark = appearance === "dark" || (appearance === "system" && systemDark);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try { localStorage.setItem("openx.appearance", appearance); } catch { /* ignore */ }
  }, [dark, appearance]);

  const themeConfig = useMemo(() => buildTheme(dark), [dark]);

  return (
    <ConfigProvider theme={themeConfig}>
      <AntApp>
        <Workbench appearance={appearance} onAppearance={setAppearance} />
      </AntApp>
    </ConfigProvider>
  );
}

export interface SceneRef { projectId: string; doc: PdfDocument; scene: Scene }

function Workbench({ appearance, onAppearance }: { appearance: Appearance; onAppearance: (a: Appearance) => void }) {
  const { message } = AntApp.useApp();
  const [lang, setLang] = useState<Lang>("en");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [docs, setDocs] = useState<PdfDocument[]>([]);
  const [docId, setDocId] = useState<string | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [sceneId, setSceneId] = useState<string | null>(null);
  const [library, setLibrary] = useState<Library | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const searchSeq = useRef(0);

  const doc = docs.find((d) => d.document_id === docId) ?? null;
  const scene = scenes.find((s) => s.scene_id === sceneId) ?? null;
  const cand = result?.results.find((c) => c.asset_id === activeKey) ?? null;

  useEffect(() => {
    Promise.all([api.projects(), api.library()])
      .then(([p, lib]) => {
        setProjects(p.projects);
        setProjectId(p.last_project_id ?? p.projects[0]?.project_id ?? null);
        setLibrary(lib);
        setOnline(true);
      })
      .catch((e: Error) => {
        setOnline(false);
        message.error(`Cannot reach the workbench API: ${e.message}`);
      });
  }, [message]);

  useEffect(() => {
    if (!projectId) return;
    setDocs([]);
    setDocId(null);
    api.documents(projectId).then((d) => {
      setDocs(d);
      setDocId(d[0]?.document_id ?? null);
    }).catch((e: Error) => message.error(e.message));
  }, [projectId, message]);

  useEffect(() => {
    setScenes([]);
    setSceneId(null);
    setResult(null);
    if (!projectId || !docId) return;
    api.scenes(projectId, docId).then((s) => {
      setScenes(s);
      if (s[0]) {
        setSceneId(s[0].scene_id);
        setQuery(s[0].title);
      }
    }).catch((e: Error) => message.error(e.message));
  }, [projectId, docId, message]);

  const runSearch = useCallback(
    (opts: { text?: string; filters?: Record<string, string> } = {}) => {
      if (!projectId) return;
      const seq = ++searchSeq.current;
      setSearching(true);
      setSearchError(null);
      api
        .search({
          project_id: projectId,
          document_id: scene ? docId ?? undefined : undefined,
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
    [projectId, docId, scene, query, filters, lang],
  );

  // A new scene (or language) re-runs matching so the middle and right columns never show stale results.
  const sceneKey = scene ? `${scene.scene_id}@${scene.revision}:${lang}` : "";
  useEffect(() => {
    if (sceneKey) runSearch({ text: scene!.title });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneKey]);

  const pickScene = (id: string) => {
    const s = scenes.find((x) => x.scene_id === id);
    if (!s) return;
    setSceneId(id);
    setQuery(s.title);
  };
  const activate = (key: string) => {
    setActiveKey(key);
    setChecked((prev) => (prev.includes(key) ? prev : [...prev, key]));
  };
  const changeFilters = (f: Record<string, string>) => {
    setFilters(f);
    runSearch({ filters: f });
  };
  const pickProject = (id: string) => {
    setProjectId(id);
    api.selectProject(id).catch(() => undefined);
  };

  const ref: SceneRef | null = projectId && doc && scene ? { projectId, doc, scene } : null;
  const step = cand ? 2 : result ? 1 : 0;

  return (
    <div className="ox-root">
      <TopBar
        appearance={appearance}
        onAppearance={onAppearance}
        lang={lang}
        onLang={setLang}
        projects={projects}
        projectId={projectId}
        onProject={pickProject}
      />
      <StepBar active={step} projectId={projectId} docs={docs} docId={docId} onDoc={setDocId} />
      <main className="ox-main">
        <RequirementsPanel projectId={projectId} doc={doc} scenes={scenes} scene={scene} onPick={pickScene} />
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
          activeKey={activeKey}
          onActivate={activate}
          checked={checked}
          onChecked={setChecked}
          active={cand}
        />
        <DecisionPanel sceneRef={ref} cand={cand} searching={searching} query={query} lang={lang} />
      </main>
    </div>
  );
}
