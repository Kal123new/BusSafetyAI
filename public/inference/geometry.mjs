export const SIZE = 640;
export function letterbox(width, height) {
  if (!(width > 0 && height > 0)) throw new Error('Invalid frame size');
  const scale = Math.min(SIZE / width, SIZE / height);
  const resizedWidth = Math.round(width * scale), resizedHeight = Math.round(height * scale);
  return { scale, resizedWidth, resizedHeight, left: Math.floor((SIZE - resizedWidth) / 2), top: Math.floor((SIZE - resizedHeight) / 2) };
}
export function decode(data, dims, width, height, box, threshold = 0.45) {
  if (dims.length !== 3 || dims[0] !== 1 || dims[2] !== 6) throw new Error('Unsupported model output; expected YOLO26 end-to-end detections');
  const detections = [];
  const clamp = (v, max) => Math.max(0, Math.min(max, v));
  for (let offset = 0; offset < data.length; offset += 6) {
    const [x1, y1, x2, y2, confidence, classId] = data.subarray(offset, offset + 6);
    if (![x1,y1,x2,y2,confidence,classId].every(Number.isFinite)) throw new Error('Invalid model output');
    if (confidence < threshold || classId !== 0) continue;
    const left = clamp((x1-box.left)/box.scale, width), top = clamp((y1-box.top)/box.scale, height);
    const right = clamp((x2-box.left)/box.scale, width), bottom = clamp((y2-box.top)/box.scale, height);
    if (right <= left || bottom <= top) continue;
    detections.push({ class_id: 0, class_name: 'Person', confidence, x: left/width*100, y: top/height*100, width: (right-left)/width*100, height: (bottom-top)/height*100 });
  }
  return detections;
}
