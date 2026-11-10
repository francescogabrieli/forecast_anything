import { readFile } from 'node:fs/promises';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import { documents } from './scripts/documents.mjs';

export default defineConfig({
  base: './',
  plugins: [
    tailwindcss(),
    {
      name: 'forecast-static-pages',
      configureServer(server) {
        server.middlewares.use(async (req, res, next) => {
          const path = req.url?.split('?')[0];
          try {
            if (path in documents) {
              res.setHeader('Content-Type', 'text/plain; charset=utf-8');
              res.end(await readFile(documents[path]));
              return;
            }
            if (path !== '/' && path !== '/index.html') return next();
            const template = await readFile(new URL('./index.html', import.meta.url), 'utf8');
            const { render } = await server.ssrLoadModule('/src/render.tsx');
            const html = await server.transformIndexHtml(path, template.replace('<!--app-->', () => render()));
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.end(html);
          } catch (error) {
            next(error);
          }
        });
      }
    }
  ]
});
