import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    rules: {
      // `any` is only allowed with an explaining eslint-disable comment.
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  { ignores: [".next/**", ".next-e2e/**", "playwright-report/**", "test-results/**"] },
];

export default eslintConfig;
