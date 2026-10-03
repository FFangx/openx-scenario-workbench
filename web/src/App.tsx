import { useEffect, useMemo, useState } from "react";
import { App as AntApp, ConfigProvider } from "antd";
import { buildTheme } from "./theme";
import { CANDIDATES, DEFAULT_FILTERS, SCENES } from "./data/mock";
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

function Workbench({ appearance, onAppearance }: { appearance: Appearance; onAppearance: (a: Appearance) => void }) {
  const [sceneId, setSceneId] = useState(2);
  const [activeKey, setActiveKey] = useState(CANDIDATES[1].key);
  const [checked, setChecked] = useState<string[]>([CANDIDATES[1].key]);
  const [query, setQuery] = useState(SCENES[1].query);
  const [filters, setFilters] = useState<Record<string, string>>(DEFAULT_FILTERS);

  const scene = SCENES.find((s) => s.id === sceneId)!;
  const cand = CANDIDATES.find((c) => c.key === activeKey)!;

  const pickScene = (id: number) => {
    setSceneId(id);
    setQuery(SCENES.find((s) => s.id === id)!.query);
  };
  const activate = (key: string) => {
    setActiveKey(key);
    setChecked((prev) => (prev.includes(key) ? prev : [...prev, key]));
  };

  return (
    <div className="ox-root">
      <TopBar appearance={appearance} onAppearance={onAppearance} />
      <StepBar />
      <main className="ox-main">
        <RequirementsPanel scene={scene} onPick={pickScene} />
        <SearchPanel
          query={query}
          onQuery={setQuery}
          filters={filters}
          onFilters={setFilters}
          activeKey={activeKey}
          onActivate={activate}
          checked={checked}
          onChecked={setChecked}
          active={cand}
        />
        <DecisionPanel scene={scene} cand={cand} />
      </main>
    </div>
  );
}
