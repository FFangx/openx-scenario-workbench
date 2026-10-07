// How candidates are named: by the scenario's and the map's names, or (a preference) by their file names.
// Tools that export cases often name the files by an id, so names are the default.
import { createContext, useContext } from "react";
import { basename } from "./api";

export const FileNamesContext = createContext(false);

interface Named { xosc: string; xodr: string; display_title: string; map_name: string }

export function useNames() {
  const files = useContext(FileNamesContext);
  return {
    files,
    scenario: (c: Pick<Named, "xosc" | "display_title">) => (files || !c.display_title ? basename(c.xosc) : c.display_title),
    road: (c: Pick<Named, "xodr" | "map_name">) => (files || !c.map_name ? basename(c.xodr) : c.map_name),
  };
}
