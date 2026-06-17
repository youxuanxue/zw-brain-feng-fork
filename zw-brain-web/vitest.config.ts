import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

// 组件单测用：jsdom 环境 + Vue SFC 编译 + @/ 别名（与 tsconfig paths 对齐）。
// 运行：npx vitest run（需 vitest / @vue/test-utils / jsdom，见 README/报告说明）。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    globals: true,
  },
});
