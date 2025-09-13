import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const useDevProxy = ["1", "true", "yes", "on"].includes(String(process.env.NEXT_PUBLIC_USE_DEV_PROXY || process.env.USE_DEV_PROXY || "false").toLowerCase());

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  // Global rules
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
  // Stricter rules only for client/src code (not tests/scripts)
  {
    files: ["src/**/*.{js,jsx,ts,tsx}"],
    ignores: ["src/**/__tests__/**", "src/**/__mocks__/**", "src/**/tests/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.name='fetch'][arguments.0.value='/v1/whoami']",
          message:
            "Never call /v1/whoami directly; use getAuthOrchestrator().checkAuth().",
        },
        {
          selector:
            "CallExpression[callee.name='apiFetch'][arguments.0.value='/v1/whoami']",
          message:
            "Never call /v1/whoami directly; use getAuthOrchestrator().checkAuth().",
        },
        {
          selector:
            "Literal[value=/^https?:\\/\\/(localhost|127\\.0\\.0\\.1):8000\\//]",
          message:
            "Do not hardcode http://localhost:8000 URLs. Use relative paths with dev proxy or NEXT_PUBLIC_API_ORIGIN for server-only contexts.",
        },
      ],
    },
  },
  // When using the dev proxy, block absolute API URLs in src/ to enforce same-origin
  ...(useDevProxy ? [{
    files: ["src/**/*.{js,jsx,ts,tsx}"],
    ignores: ["src/**/__tests__/**", "src/**/__mocks__/**", "src/**/tests/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch'][arguments.0.value=/^https?:\\/\\//]",
          message: "Use relative API paths when NEXT_PUBLIC_USE_DEV_PROXY=true.",
        },
        {
          selector: "CallExpression[callee.name='apiFetch'][arguments.0.value=/^https?:\\/\\//]",
          message: "Use relative API paths when NEXT_PUBLIC_USE_DEV_PROXY=true.",
        },
      ],
    },
  }] : []),
];

export default eslintConfig;
