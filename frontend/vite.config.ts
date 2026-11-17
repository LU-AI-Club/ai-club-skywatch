import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server runs on 8081 so skywatch-config.js treats it as a "local frontend"
// and points the browser at the API on :8000 (see public/skywatch-config.js).
export default defineConfig({
  plugins: [react()],
  server: { port: 8081, host: true },
  preview: { port: 8081, host: true },
});
