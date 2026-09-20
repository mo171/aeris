// vitest.config.ts — mirrors the tsconfig "@/*" path alias so tests resolve
// the same imports the Next.js app does.
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
