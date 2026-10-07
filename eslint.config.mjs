// ESLint 9 flat config for the Vite app in src/. (frontend/ is a separate CRA app with its own lint.)
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  { ignores: ["dist/", "node_modules/", "frontend/", "backend/"] },
  ...tsPlugin.configs["flat/recommended"],
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];
