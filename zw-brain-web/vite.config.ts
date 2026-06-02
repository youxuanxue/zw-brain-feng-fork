import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
import { promises as fs, createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';

const STATIC_MIME: Record<string, string> = {
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
};

const serveLegacyStatic = (): Plugin => ({
  name: 'zw-brain:serve-legacy-static',
  apply: 'serve',
  configureServer(server) {
    const root = path.dirname(fileURLToPath(import.meta.url));
    server.middlewares.use((req, res, next) => {
      const url = (req.url || '').split('?')[0];
      if (!(url.startsWith('/css/') || url.startsWith('/assets/'))) {
        next();
        return;
      }
      const filePath = path.join(root, url.replace(/^\//, ''));
      if (!existsSync(filePath) || !statSync(filePath).isFile()) {
        next();
        return;
      }
      const mime = STATIC_MIME[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream';
      res.setHeader('Content-Type', mime);
      createReadStream(filePath).pipe(res);
    });
  },
});

// F2: index.html 切回 vite 入口；旧 vanilla bundle (js/, auth.js, pages.js) 保留在仓库
// 但已不再被入口引用——单一启动路径只走 vite。
//
// closeBundle hook：build 时把 css/ + assets/ 复制到 dist-vite/ 同名子目录，
// 保留 /css/app.css + /assets/zw-brain-mark.svg 这两条历史 URL 契约（preflight
// scripts/check_ui_spec_b.py 仍要求 index.html 引用 /css/app.css；同时 svg favicon
// 也需要在生产产物里可达）。dev 模式 vite 直接从源文件树服务，无需复制。
//
// 旧 js/ 目录不参与 build——只是源树残留，等 F3 完成后再统一删除（supervisor 指令 F2 双跑）。

const copyLegacyStaticToDist = (): Plugin => ({
  name: 'zw-brain:copy-legacy-static',
  apply: 'build',
  async closeBundle() {
    const root = path.dirname(fileURLToPath(import.meta.url));
    const outDir = path.join(root, 'dist-vite');
    // F-001 防御：outDir 在 vite 自身 build 出错或被外部清理时可能不存在；
    // fs.cp 不会 recursive 创建父目录，会以 ENOENT 失败且错误信息指回 closeBundle，
    // 让用户误以为是 vite 配置 bug。先 mkdir recursive 兜底。
    await fs.mkdir(outDir, { recursive: true });
    for (const dir of ['css', 'assets']) {
      const from = path.join(root, dir);
      const to = path.join(outDir, dir);
      await fs.cp(from, to, { recursive: true });
    }
    // eslint-disable-next-line no-console
    console.log('[zw-brain] copied css/ + assets/ -> dist-vite/');
  },
});

export default defineConfig({
  base: '/zw-brain/',
  plugins: [vue(), serveLegacyStatic(), copyLegacyStaticToDist()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    open: false,
    proxy: {
      // brain REST 默认端口 8800（zw_brain/shared/runtime_config.py::DEFAULT_REST_PORT）。
      // 启动方式：ZW_BRAIN_DEV_IAM_BYPASS=1 python -m zw_brain.entry.rest.server
      '/zw-brain/api': { target: 'http://127.0.0.1:8800', changeOrigin: true },
      '/zw-brain/auth': { target: 'http://127.0.0.1:8800', changeOrigin: true },
      '/zw-brain/health': { target: 'http://127.0.0.1:8800', changeOrigin: true },
      '/zw-brain/assets': { target: 'http://127.0.0.1:8800', changeOrigin: true },
      '/zw-brain/css': { target: 'http://127.0.0.1:8800', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist-vite',
    emptyOutDir: true,
    sourcemap: false,
  },
});
