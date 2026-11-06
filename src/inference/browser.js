export const browserInference = import.meta.env.VITE_BROWSER_INFERENCE === 'true';
let worker, ready, sequence = 0;
const pending = new Map();

function stop(error) {
  worker?.terminate(); worker = null; ready = null;
  for (const task of pending.values()) { clearTimeout(task.timer); task.reject(error); }
  pending.clear();
}

function send(type, payload = {}, transfer = []) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => stop(new Error('Browser detection timed out. Stop and restart the camera to retry.')), type === 'init' ? 180000 : 30000);
    pending.set(id, { resolve, reject, timer });
    worker.postMessage({ id, type, ...payload }, transfer);
  });
}

export function loadBrowserModel() {
  if (ready) return ready;
  if (!window.isSecureContext || !window.Worker || !window.OffscreenCanvas) {
    return Promise.reject(new Error('Browser detection requires HTTPS and a current desktop Chrome or Edge browser.'));
  }
  worker = new Worker(new URL(`${import.meta.env.BASE_URL}inference/worker.mjs`, window.location.origin), { type: 'module' });
  worker.onmessage = ({ data }) => {
    const task = pending.get(data.id); if (!task) return;
    clearTimeout(task.timer); pending.delete(data.id);
    data.error ? task.reject(new Error(data.error)) : task.resolve(data.result);
  };
  worker.onerror = () => stop(new Error('Browser detector could not start. Reload the page or try current desktop Chrome/Edge.'));
  ready = send('init').catch(error => { stop(error); throw error; });
  return ready;
}

export async function predictBrowserFrame(blob, capturedAt, signal) {
  await loadBrowserModel();
  if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
  const bitmap = await createImageBitmap(blob);
  if (signal?.aborted) { bitmap.close(); throw new DOMException('Cancelled', 'AbortError'); }
  const result = await send('predict', { bitmap, capturedAt }, [bitmap]);
  if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
  return result;
}
