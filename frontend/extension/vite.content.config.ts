import { resolve } from "node:path";
import { defineConfig } from "vite";

// See vite.background.config.ts for why this is a separate build. emptyOutDir is false here so
// this run doesn't wipe out background.js from the first build.
export default defineConfig({
  // Vite's automatic NODE_ENV=production define doesn't reliably apply in library mode, so React
  // was shipping its (much larger) development bundle, dev warnings and all. Force it explicitly.
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "dist",
    emptyOutDir: false,
    minify: "esbuild",
    lib: {
      entry: resolve(__dirname, "src/content/main.tsx"),
      formats: ["iife"],
      name: "LJAContent",
      fileName: () => "content.js",
    },
  },
});
