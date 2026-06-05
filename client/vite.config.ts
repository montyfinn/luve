import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Skeleton config. Dev server runs on :5173 (already in core_api CORS allow-list).
// NOTE: when core_api serving is wired (migration plan Phase 10), set
// `base: "/app/"` so built asset URLs resolve under the /app route. Left as the
// default "/" for the skeleton — no serving is implemented in this phase.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
