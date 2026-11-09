import { access, readFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';

import sharp from 'sharp';

const projectRoot = resolve(dirname(new URL(import.meta.url).pathname), '..');
const packageRoot = join(projectRoot, 'packages', 'workout-guide');
const manifest = JSON.parse(await readFile(join(packageRoot, 'manifest.json'), 'utf8'));

if (manifest.length !== 303) throw new Error(`Expected 303 exercises, found ${manifest.length}.`);
if (new Set(manifest.map((item) => item.id)).size !== 303) throw new Error('Exercise IDs are not unique.');
if (new Set(manifest.map((item) => item.slug)).size !== 303) throw new Error('Exercise slugs are not unique.');

let frameCount = 0;
let sourcedCount = 0;
let sourcedFrameCount = 0;
for (const exercise of manifest) {
  if (exercise.frames.length !== 3) throw new Error(`${exercise.id} does not have three frames.`);
  if (exercise.attribution?.source) sourcedCount += 1;
  for (const [offset, frame] of exercise.frames.entries()) {
    if (frame.index !== offset + 1) throw new Error(`${exercise.id} frame order is invalid.`);
    if (frame.attribution?.creator !== 'Bryl Lim' || frame.attribution?.license !== 'CC BY-SA 4.0') {
      throw new Error(`${exercise.id} frame ${frame.index} has incomplete attribution.`);
    }
    if (frame.attribution.source) sourcedFrameCount += 1;
    const path = join(packageRoot, frame.path);
    await access(path);
    const metadata = await sharp(path).metadata();
    if (metadata.width !== 512 || metadata.height !== 512 || metadata.format !== 'svg' || !metadata.hasAlpha) {
      throw new Error(`${frame.path} must be a transparent 512 × 512 SVG.`);
    }
    frameCount += 1;
  }
}

if (frameCount !== 909) throw new Error(`Expected 909 frames, found ${frameCount}.`);
if (sourcedCount !== 77) throw new Error(`Expected 77 Everkinetic attributions, found ${sourcedCount}.`);
if (sourcedFrameCount !== 77) throw new Error(`Expected 77 sourced frame records, found ${sourcedFrameCount}.`);

console.log(`Validated ${manifest.length} exercises, ${frameCount} frames, and ${sourcedCount} sourced poses.`);
