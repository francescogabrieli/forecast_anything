import { copyFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { render } from '../.prerender/render.js';
import { documents } from './documents.mjs';

const html = new URL('../dist/index.html', import.meta.url);
const template = await readFile(html, 'utf8');
if (!template.includes('<!--app-->')) throw new Error('Missing HTML render slot');
await writeFile(html, template.replace('<!--app-->', () => render()));

for (const [path, source] of Object.entries(documents)) {
  const dest = new URL(`../dist${path}`, import.meta.url);
  await mkdir(dirname(dest.pathname), { recursive: true });
  await copyFile(source, dest);
}
await rm(new URL('../.prerender', import.meta.url), { recursive: true });
