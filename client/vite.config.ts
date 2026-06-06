import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server runs on :5173 (already in the core_api CORS allow-list).
// The production build is served by core_api under the /app route, so built
// asset URLs must be prefixed with /app/. Dev keeps base "/" so the local
// `npm run dev` workflow is unchanged.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/app/" : "/",
  server: {
    port: 5173,
  },
}));
