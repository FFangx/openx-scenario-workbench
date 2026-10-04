import { useCallback, useReducer, useRef, useState } from "react";
import { api, type Lang, type Scene, type SearchResponse } from "./api";

interface Search {
  result: SearchResponse | null;
  searching: boolean;
  error: string | null;
  /** The candidate shown in the decision panel, and the ones ticked for comparison. */
  activeKey: string | null;
  checked: string[];
}

type Action =
  | { type: "start" }
  | { type: "done"; result: SearchResponse }
  | { type: "failed"; error: string }
  | { type: "clear" }
  | { type: "activate"; key: string }
  | { type: "check"; keys: string[] };

const IDLE: Search = { result: null, searching: false, error: null, activeKey: null, checked: [] };

function reduce(state: Search, action: Action): Search {
  switch (action.type) {
    case "start": return { ...state, searching: true, error: null };
    case "done": {
      const first = action.result.results[0]?.asset_id ?? null;
      return { ...state, searching: false, result: action.result, activeKey: first, checked: first ? [first] : [] };
    }
    case "failed": return { ...state, searching: false, error: action.error, result: null };
    case "clear": return { ...state, result: null, activeKey: null };
    case "activate": return { ...state, activeKey: action.key, checked: state.checked.includes(action.key) ? state.checked : [...state.checked, action.key] };
    case "check": return { ...state, checked: action.keys };
  }
}

/** Search text, filters and the ranked candidates for the selected scene (or free text without one). */
export function useMatching({ projectId, scene, lang }: { projectId: string | null; scene: Scene | null; lang: Lang }) {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [search, dispatch] = useReducer(reduce, IDLE);
  // Only the latest request may update the results; an older one finishing later is ignored.
  const searchSeq = useRef(0);

  const runSearch = useCallback(
    (opts: { text?: string; filters?: Record<string, string> } = {}) => {
      if (!projectId) return;
      const seq = ++searchSeq.current;
      dispatch({ type: "start" });
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
        .then((result) => seq === searchSeq.current && dispatch({ type: "done", result }))
        .catch((e: Error) => seq === searchSeq.current && dispatch({ type: "failed", error: e.message }));
    },
    [projectId, scene, query, filters, lang],
  );

  return {
    ...search,
    query,
    setQuery,
    filters,
    setFilters,
    runSearch,
    clear: () => dispatch({ type: "clear" }),
    activate: (key: string) => dispatch({ type: "activate", key }),
    setChecked: (keys: string[]) => dispatch({ type: "check", keys }),
  };
}
