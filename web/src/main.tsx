import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Root from "./App";
import "@fontsource-variable/inter-tight";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
