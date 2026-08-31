import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The frontend never talks to Hugging Face directly. All backend capability
// goes through chat_service. In dev, /api is proxied to the FastAPI server so
// the browser stays same-origin and CORS is a non-issue.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8100",
        changeOrigin: true,
      },
    },
  },
});
