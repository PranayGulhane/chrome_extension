import { resolve } from "node:path";
import { defineConfig } from "vite";

// Rollup structurally refuses IIFE output for a multi-entry/code-splitting build even when
// nothing is actually shared between entries — so background and content are built as two
// separate single-entry library-mode builds (see vite.content.config.ts) rather than one
// rollupOptions.input config. Both write into the same dist/; this one owns emptying it.
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    minify: "esbuild",
    lib: {
      entry: resolve(__dirname, "src/background/service-worker.ts"),
      formats: ["iife"],
      name: "LJABackground",
      fileName: () => "background.js",
    },
  },
});
