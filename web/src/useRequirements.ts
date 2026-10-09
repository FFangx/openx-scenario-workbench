import { useCallback, useEffect, useReducer, useRef } from "react";
import { api, type PdfDocument, type Project, type Scene } from "./api";

export type Scope = "pdf" | "all";
export const sceneKey = (s: Scene) => `${s.document_id}/${s.scene_id}`;

interface State {
  projects: Project[];
  /** False until the project list first arrives: "no project" is only said once it has. */
  projectsLoaded: boolean;
  projectId: string | null;
  docs: PdfDocument[];
  /** The project `docs` belong to; another value means its PDFs are still on the way. */
  docsFor: string | null;
  docId: string | null;
  scope: Scope;
  scenes: Scene[];
  selected: string | null;
}

type Action =
  | { type: "projects"; projects: Project[]; projectId: string | null }
  | { type: "created"; project: Project }
  | { type: "renamed"; project: Project }
  | { type: "switch"; projectId: string }
  | { type: "docs"; projectId: string; docs: PdfDocument[]; docId: string | null }
  | { type: "doc"; docId: string }
  | { type: "scope"; scope: Scope }
  | { type: "scenes"; scenes: Scene[]; selected: string | null }
  | { type: "select"; key: string | null }
  | { type: "replace"; scene: Scene };

const INITIAL: State = { projects: [], projectsLoaded: false, projectId: null, docs: [], docsFor: null, docId: null, scope: "pdf", scenes: [], selected: null };

/** Switching project clears its documents and scenes at once, so scenes are never requested with the previous project's document. */
const switched = (state: State, projectId: string | null): State =>
  ({ ...state, projectId, docs: [], docsFor: null, docId: null, scope: "pdf", scenes: [], selected: null });

function reduce(state: State, action: Action): State {
  switch (action.type) {
    case "projects": {
      const next = { ...state, projects: action.projects, projectsLoaded: true };
      return action.projectId === state.projectId ? next : switched(next, action.projectId);
    }
    case "created": return switched({ ...state, projects: [...state.projects, action.project] }, action.project.project_id);
    case "renamed": return { ...state, projects: state.projects.map((p) => (p.project_id === action.project.project_id ? action.project : p)) };
    case "switch": return switched(state, action.projectId);
    case "docs": return { ...state, docs: action.docs, docsFor: action.projectId, docId: action.docId, scope: action.docs.length < 2 ? "pdf" : state.scope };
    case "doc": return { ...state, scope: "pdf", docId: action.docId };
    case "scope": return { ...state, scope: action.scope };
    case "scenes": return { ...state, scenes: action.scenes, selected: action.selected };
    case "select": return { ...state, selected: action.key };
    case "replace": return { ...state, scenes: state.scenes.map((x) => (sceneKey(x) === sceneKey(action.scene) ? action.scene : x)) };
  }
}

/**
 * Projects, their PDFs and the requirement queue, with the selected scene.
 * `onEnter` runs when loading the queue enters a different scene than the one kept, and `onError` reports failed loads.
 */
export function useRequirements({ onEnter, onError }: { onEnter: (scene: Scene) => void; onError: (message: string) => void }) {
  const [state, dispatch] = useReducer(reduce, INITIAL);
  const { projectId, docId, scope, scenes, selected } = state;
  // A scene (and its PDF) to open once the queue of another project or PDF has loaded.
  const pending = useRef<string | null>(null);
  const pendingDoc = useRef<string | null>(null);
  const handlers = useRef({ onEnter, onError });
  handlers.current = { onEnter, onError };
  // Only the latest load of each list may fill it: switching project or PDF again before an answer
  // arrives leaves that answer unused.
  const docsSeq = useRef(0);
  const scenesSeq = useRef(0);

  const loadDocs = useCallback((pid: string, select?: string) => {
    const seq = ++docsSeq.current;
    return api.documents(pid).then((d) => {
      if (seq !== docsSeq.current) return;
      const wanted = select ?? pendingDoc.current;
      pendingDoc.current = null;
      dispatch({ type: "docs", projectId: pid, docs: d, docId: wanted && d.some((x) => x.document_id === wanted) ? wanted : d[0]?.document_id ?? null });
    }).catch((e: Error) => seq === docsSeq.current && handlers.current.onError(e.message));
  }, []);

  useEffect(() => {
    if (projectId) loadDocs(projectId);
  }, [projectId, loadDocs]);

  /** Reload the queue; keep the current selection when it still exists, else enter at the requested or first scene. */
  const loadScenes = useCallback((keep: string | null) => {
    const seq = ++scenesSeq.current;
    if (!projectId || (scope === "pdf" && !docId)) {
      dispatch({ type: "scenes", scenes: [], selected: null });
      return;
    }
    const request = scope === "all" ? api.allScenes(projectId) : api.scenes(projectId, docId!);
    request.then((s) => {
      if (seq !== scenesSeq.current) return;
      const wanted = pending.current ?? keep;
      pending.current = null;
      const next = s.find((x) => sceneKey(x) === wanted) ?? s[0];
      dispatch({ type: "scenes", scenes: s, selected: next ? sceneKey(next) : null });
      if (next && sceneKey(next) !== keep) handlers.current.onEnter(next);
    }).catch((e: Error) => seq === scenesSeq.current && handlers.current.onError(e.message));
  }, [projectId, docId, scope]);

  const scene = scenes.find((s) => sceneKey(s) === selected) ?? null;
  const doc = state.docs.find((d) => d.document_id === (scene?.document_id ?? docId)) ?? null;

  return {
    ...state,
    scene,
    doc,
    docsLoading: !state.projectsLoaded || (!!projectId && state.docsFor !== projectId),
    loadDocs,
    loadScenes,
    /** The project list, with the project to show: the current one is kept when it is the same. */
    setProjects: (projects: Project[], current: string | null) => dispatch({ type: "projects", projects, projectId: current }),
    projectCreated: (project: Project) => dispatch({ type: "created", project }),
    projectRenamed: (project: Project) => dispatch({ type: "renamed", project }),
    switchProject: (id: string) => dispatch({ type: "switch", projectId: id }),
    chooseDoc: (id: string) => dispatch({ type: "doc", docId: id }),
    setScope: (value: Scope) => dispatch({ type: "scope", scope: value }),
    select: (key: string | null) => dispatch({ type: "select", key }),
    replaceScene: (s: Scene) => dispatch({ type: "replace", scene: s }),
    /** Open a scene after the next queue load: of document `documentId` when given. */
    openLater: (key: string, documentId?: string) => {
      pending.current = key;
      if (documentId) pendingDoc.current = documentId;
    },
  };
}
