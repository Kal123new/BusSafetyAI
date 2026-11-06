"""Export the trusted project checkpoint and validate its browser tensor contract."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import numpy as np
import onnx
import onnxruntime as ort
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
checkpoint = ROOT / 'models/best.pt'
EXPECTED = '5e86f6e125dbfe1cf4755966e8a4e1a4a3966410a41f312e4ae801b0a9003df7'
assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == EXPECTED, 'Unexpected checkpoint'
torch.set_num_threads(2)
model = YOLO(str(checkpoint))
exported = Path(model.export(format='onnx', imgsz=640, opset=17, simplify=False, dynamic=False, half=False, batch=1, device='cpu'))
onnx.checker.check_model(str(exported))
runtime = ort.InferenceSession(str(exported), providers=['CPUExecutionProvider'])
sample = np.random.default_rng(42).random((1,3,640,640), dtype=np.float32)
output = runtime.run(None, {runtime.get_inputs()[0].name: sample})[0]
assert output.ndim == 3 and output.shape[0] == 1 and output.shape[2] == 6, output.shape
assert np.isfinite(output).all()
assert set(model.names.values()) == {'Person'}
# Compare the same deterministic tensor through the exported PyTorch network.
with torch.inference_mode():
    expected = model.model(torch.from_numpy(sample))
    if isinstance(expected, (tuple, list)):
        expected = expected[0]
    expected = expected.detach().cpu().numpy()
assert expected.shape == output.shape, (expected.shape, output.shape)
# Near-tied top-k detections can change row ordering: compare sorted score sets.
np.testing.assert_allclose(np.sort(expected[...,4]), np.sort(output[...,4]), atol=1e-4, rtol=1e-3)
destination = ROOT / 'browser-model'
destination.mkdir(exist_ok=True)
shutil.copyfile(exported, destination / 'person.onnx')
data = (destination / 'person.onnx').read_bytes()
metadata = dict(checkpoint_sha256=EXPECTED, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), input=[1,3,640,640], output=list(output.shape), classes=model.names, confidence=0.45, validation='ONNX checker, CPU execution, finite outputs and deterministic tensor score parity. Not dataset accuracy or desktop performance validation.')
(destination / 'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
print(json.dumps(metadata))
