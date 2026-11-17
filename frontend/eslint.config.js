import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import i18next from 'eslint-plugin-i18next'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig([
  globalIgnores([
    'dist',
    'coverage',
    'playwright-report',
    'test-results',
    'src/api/schema.d.ts',
    'scripts',
  ]),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      // Hard rules from CLAUDE.md / architecture sections 6 and 7.
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML is forbidden (architecture section 7).',
        },
      ],
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'Use the typed client in src/api through a TanStack Query hook.',
        },
      ],
      '@typescript-eslint/no-explicit-any': 'error',
    },
  },
  {
    // No hard-coded user-facing text in components (FR-I18N-02).
    files: ['src/**/*.tsx'],
    ignores: ['src/**/*.test.tsx', 'src/test/**'],
    plugins: { i18next },
    rules: {
      'i18next/no-literal-string': [
        'error',
        {
          mode: 'jsx-only',
          // Only attributes people read; ids, names, routes and data-* are code.
          'jsx-attributes': {
            include: ['alt', 'aria-label', 'aria-description', 'title', 'placeholder', 'label'],
          },
        },
      ],
    },
  },
  {
    // shadcn/ui primitives export variants next to components.
    files: ['src/components/ui/**'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  {
    files: ['e2e/**', '*.config.ts'],
    languageOptions: { globals: globals.node },
  },
])
