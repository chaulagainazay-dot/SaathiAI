import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

/** Bounded Next.js ESLint — non-interactive. */
const eslintConfig = [
  {
    ignores: ["node_modules/**", ".next/**", "out/**", "public/sw.js", "postcss.config.mjs"],
  },
  ...compat.extends("next/core-web-vitals"),
  {
    rules: {
      // Pre-existing codebase is large; M47.3 lint is deterministic and non-blocking on legacy react patterns.
      "react/no-unescaped-entities": "off",
      "@next/next/no-html-link-for-pages": "off",
    },
  },
];

export default eslintConfig;
