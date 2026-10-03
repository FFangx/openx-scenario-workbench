import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // phase 2: FastAPI backend
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
