# SafeSense custom YOLO26s

- Checkpoint: `best.pt`
- Task: bounding-box person detection inside buses.
- Class: `Person` (one class; not identity recognition or child/adult classification).
- SHA-256: `5e86f6e125dbfe1cf4755966e8a4e1a4a3966410a41f312e4ae801b0a9003df7`

## Recorded validation results

| Checkpoint metric | Value |
| --- | ---: |
| Precision | 0.97134 |
| Recall | 0.96260 |
| mAP50 | 0.98598 |
| mAP50–95 | 0.76647 |

These values come from the checkpoint's saved training metrics. They have not been independently recomputed for this publication. Precision of 97.1% is not overall accuracy, and these metrics do not establish performance on unseen buses or an independent test set.

The training workflow explored model sizes and augmentation for difficult lighting and camera movement, followed by further fine-tuning. This release does not include the original dataset, split manifests, per-run comparison logs, or complete stage-by-stage recipe. Consequently, a numerical improvement attributed to a particular stage cannot be independently established from this checkpoint alone.

For an interview or reproducible comparison, retain each run's data split, training configuration, seed, checkpoint selection rule, validation image size, confidence/IoU settings, precision/recall/mAP results, and latency on the same hardware. Report test-set results separately.

## Inference and limitations

The application loads this checkpoint through Ultralytics; the hosted build pins version 8.4.127. The application's default inference confidence is 0.45. That runtime threshold is not evidence of the threshold used to calculate the saved validation summary.

Occlusion, lighting, motion blur, camera placement, and unfamiliar interiors can produce missed or false detections. Adults are also people. A zero count cannot certify an empty bus, and detected boxes cannot replace named attendance or a physical inspection. Browser camera frames are sent to the application backend for inference.

Only load trusted PyTorch checkpoints. The training images are not distributed here. Check the applicable Ultralytics and dataset licensing terms before redistribution or commercial use.
