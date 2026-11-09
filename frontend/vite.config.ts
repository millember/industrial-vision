import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  base: "/industrial-vision/",
  plugins: [react()],
  server: {proxy: {
    "^/industrial-vision/(api|docs|openapi.json|redoc)": {
      target: "http://127.0.0.1:8000",
      rewrite: p => p.replace(/^\/industrial-vision/, ""),
    },
  }},
});
