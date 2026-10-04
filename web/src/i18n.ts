// Interface language. Strings stay next to their use as (中文, English) pairs, like the backend's label().
import { createContext, useContext } from "react";
import type { Lang } from "./api";

export const LangContext = createContext<Lang>("zh");

export function useT() {
  const lang = useContext(LangContext);
  return { lang, t: (zh: string, en: string) => (lang === "zh" ? zh : en) };
}

export const dateTime = (iso: string | null | undefined) => (iso ? iso.slice(0, 16).replace("T", " ") : "—");
