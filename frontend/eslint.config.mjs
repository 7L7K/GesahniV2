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
      "no-restricted-globals": [
        "error",
        {
          name: "fetch",
          message: "Use apiFetch from @/lib/api instead of global fetch",
        },
      ],
    },
  },
];
