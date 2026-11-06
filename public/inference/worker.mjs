import { SIZE, letterbox, decode } from './geometry.mjs';
let ort, session, provider, busy = false;
async function initialize() {
  if (session) return { provider };
  ort = await import('../ort/ort.webgpu.min.mjs');
  ort.env.wasm.wasmPaths = new URL('../ort/', import.meta.url).href;
  ort.env.wasm.numThreads = 1;
  const modelUrl = new URL('../models/person.onnx', import.meta.url).href;
  if (self.navigator.gpu) {
    try { session = await ort.InferenceSession.create(modelUrl, { executionProviders: ['webgpu'] }); provider = 'WebGPU'; }
    catch { session = null; }
  }
  if (!session) {
    session = await ort.InferenceSession.create(modelUrl, { executionProviders: ['wasm'] }); provider = 'WebAssembly';
  }
  return { provider };
}
self.onmessage = async ({ data }) => {
  const { id, type, bitmap, capturedAt } = data;
  try {
    if (type === 'init') { self.postMessage({ id, result: await initialize() }); return; }
    if (busy || !session) throw new Error('Detector is not ready');
    busy = true;
    const width = bitmap.width, height = bitmap.height, box = letterbox(width, height);
    const canvas = new OffscreenCanvas(SIZE, SIZE), context = canvas.getContext('2d', { willReadFrequently: true });
    context.fillStyle = 'rgb(114,114,114)'; context.fillRect(0,0,SIZE,SIZE);
    context.drawImage(bitmap, box.left, box.top, box.resizedWidth, box.resizedHeight);
    bitmap.close();
    const pixels = context.getImageData(0,0,SIZE,SIZE).data;
    const plane = SIZE*SIZE, tensor = new Float32Array(plane*3);
    for (let i=0;i<plane;i++) { tensor[i]=pixels[i*4]/255; tensor[i+plane]=pixels[i*4+1]/255; tensor[i+plane*2]=pixels[i*4+2]/255; }
    const input = new ort.Tensor('float32',tensor,[1,3,SIZE,SIZE]);
    let outputs;
    try {
      outputs = await session.run({ [session.inputNames[0]]: input });
      const output = outputs[session.outputNames[0]];
      const stale = Date.now()/1000-capturedAt > 10;
      const detections = stale ? [] : decode(output.data, output.dims, width, height, box);
      self.postMessage({ id, result: { model_loaded: true, model_version: 'YOLO26s-browser', frame_status: stale ? 'stale' : 'valid', captured_at: capturedAt, processed_at: Date.now()/1000, detections, visible_person_count: stale ? null : detections.length, provider } });
    } finally { input.dispose(); if (outputs) Object.values(outputs).forEach(output => output.dispose()); }
  } catch (error) {
    bitmap?.close(); self.postMessage({ id, error: error.message || 'Browser inference failed' });
  } finally { busy = false; }
};
