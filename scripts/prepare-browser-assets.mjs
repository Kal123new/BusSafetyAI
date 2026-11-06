import { mkdir, writeFile, cp, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const release = 'https://github.com/Kal123new/BusSafetyAI/releases/download/browser-model-v1/';
async function download(name) {
  const response = await fetch(release+name);
  if (!response.ok) throw new Error(`Model asset ${name} unavailable (${response.status}). Run the Export browser model workflow first.`);
  return Buffer.from(await response.arrayBuffer());
}
await mkdir('public/models', { recursive: true });
const manifest = JSON.parse(await download('manifest.json'));
const model = await download('person.onnx');
if (manifest.checkpoint_sha256 !== '5e86f6e125dbfe1cf4755966e8a4e1a4a3966410a41f312e4ae801b0a9003df7' || createHash('sha256').update(model).digest('hex') !== manifest.sha256) throw new Error('Model integrity check failed');
await writeFile('public/models/person.onnx', model);
await writeFile('public/models/manifest.json', JSON.stringify(manifest));
// Keep runtime JS and WASM from one exact package version, served same-origin.
execFileSync('npm', ['install','--no-save','--package-lock=false','onnxruntime-web@1.23.2'], { stdio: 'inherit', shell: process.platform === 'win32' });
await cp('node_modules/onnxruntime-web/dist', 'public/ort', { recursive: true });
console.log('Browser model integrity verified; local inference assets prepared.');
