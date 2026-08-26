import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",

    // Generated foundation components. fcontext/ai-workflow-rules.md forbids modifying these, so linting
    // them only produces errors nobody is permitted to fix. They are vendored third-party code, not ours.
    "components/ui/**",
    "hooks/use-mobile.ts",

    // Static assets, never source. public/cesium holds Cesium's minified runtime workers, copied in by
    // scripts/copy-cesium-assets.mjs on postinstall.
    "public/**",
  ]),
]);

export default eslintConfig;
