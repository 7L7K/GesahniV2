import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

// Simple ESLint config to avoid regex parsing issues
export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "no-restricted-imports": ["error", {
        paths: [{
          name: 'node-fetch',
          message: 'Use apiFetch()',
        }],
        patterns: [{
          group: ['**/fetch'],
          message: 'Use apiFetch()',
        }],
      }],
    },
  },
];
