import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "no-restricted-globals": [
        "error",
        {
          "name": "fetch",
          "message": "Use apiFetch from @/lib/api instead of global fetch"
        }
      ],
      "no-restricted-syntax": [
        "error",
        {
          "selector": "CallExpression[callee.name='fetch'][arguments.0.value='/v1/whoami']",
          "message": "Never call /v1/whoami directly; use getAuthOrchestrator().checkAuth()."
        },
        {
          "selector": "CallExpression[callee.name='apiFetch'][arguments.0.value='/v1/whoami']",
          "message": "Never call /v1/whoami directly; use getAuthOrchestrator().checkAuth()."
        }
      ]
    }
  }
];

export default eslintConfig;
