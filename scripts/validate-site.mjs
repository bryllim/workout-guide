import { access, readdir, readFile } from 'node:fs/promises';
import { dirname, extname, join, resolve } from 'node:path';

const projectRoot = resolve(dirname(new URL(import.meta.url).pathname), '..');
const dist = join(projectRoot, 'apps', 'site', 'dist');
const base = '/workout-guide/';

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  }));
  return nested.flat();
}

const files = await walk(dist);
const htmlFiles = files.filter((file) => file.endsWith('.html'));
const failures = [];

if (htmlFiles.length !== 306) {
  failures.push(`Expected 306 HTML pages, found ${htmlFiles.length}.`);
}

for (const htmlFile of htmlFiles) {
  const html = await readFile(htmlFile, 'utf8');
  for (const match of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    const value = match[1];
    if (!value.startsWith(base)) continue;
    const pathname = decodeURIComponent(value.split(/[?#]/, 1)[0].slice(base.length));
    if (!pathname) continue;
    const target = extname(pathname) ? join(dist, pathname) : join(dist, pathname, 'index.html');
    try {
      await access(target);
    } catch {
      failures.push(`${htmlFile.slice(dist.length + 1)} links to missing ${value}`);
    }
  }
}

for (const required of ['index.html', 'exercises/index.html', 'exercises/push-up/index.html', 'guide/index.html', 'sitemap-index.xml', 'og.png', 'og.svg']) {
  try {
    await access(join(dist, required));
  } catch {
    failures.push(`Missing built output: ${required}`);
  }
}

if (failures.length) {
  throw new Error(`Site validation failed:\n${failures.slice(0, 30).join('\n')}`);
}

console.log(`Validated ${htmlFiles.length} pages and their internal asset and route links.`);
