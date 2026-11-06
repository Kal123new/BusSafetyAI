# Desktop browser hosting

Supported: desktop/laptop Chrome or Edge, window width at least 1024 CSS pixels. Phones and tablets are unsupported. The size guard is a layout check, not a hardware performance guarantee.

## Architecture

The new build runs the custom YOLO26s detector in a dedicated browser worker, using WebGPU when available and WebAssembly otherwise. Images stay on the visitor's computer. The model downloads on first camera use; detection performance depends on that computer.

Vercel serves the React app and the existing lightweight FastAPI backend. Neon keeps shared records. The Python deployment excludes PyTorch and does not process camera frames. The API still enforces account roles, trip ownership, state transitions, transaction/version checks, and idempotent writes. Daily plans generate trips on authenticated access instead of a continuous background thread.

The public sample has fictional students and browser-local storage only. It does not expose operational records. Shared administration, replacement buses, guardian messages and cross-device records require signing in to the configured API. The public sample illustrates boarding, trip start, drop-off, inspection, GPS and camera; it is not a shared transport-management database.

## Hosting setup

1. Run the `Export browser model` GitHub workflow. It validates the checkpoint hash, exports ONNX, checks the graph, and compares deterministic-tensor confidence scores. It publishes versioned model assets in the `browser-model-v1` release.
2. Import this repository into Vercel with the free Hobby plan for a personal, non-commercial project. The checked-in `vercel.json` builds the browser version and routes API calls to `api/index.py`.
3. Add `DATABASE_URL` as a sensitive hosting environment variable, using the existing Neon database with `sslmode=require` (or stronger). Never add it to source, GitHub, a VITE-prefixed variable, or frontend code. Existing accounts continue using their tokens.
4. For a new database, apply migrations with `python -m backend.manage migrate` only after checking the command's help; the existing migrated Neon database does not need reseeding. Keep migrations as an explicit controlled step, not one performed concurrently on every serverless request.
5. Configure approved map/routing environment variables (`MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION`, `OSRM_URL`) as in the existing deployment.
6. Run `Browser dashboard checks` and verify the actual HTTPS deployment, sign-in, shared changes on two devices, camera permission, and GPS. Update the main README's launch link only after that verification.

GitHub Actions performs model conversion once; ordinary site builds download and integrity-check the exported asset. Runtime JS and WASM are pinned together at ONNX Runtime Web 1.23.2 and served from the app's own origin.

## Limits

Vercel Hobby is limited to personal/non-commercial use and has usage caps. Neon Free also has compute and storage caps. Neither is an unlimited or guaranteed-permanent free service. Hidden-page trip/health polling is suspended to reduce unnecessary usage. Shared records and maps need connectivity; the developer's laptop is not a hosting dependency. Closing the visitor's tab stops camera monitoring.

Export validation is not a remeasurement of dataset accuracy. The original 97.1% precision is the saved PyTorch checkpoint's validation metric, not a browser accuracy certification. Physical inspection remains mandatory.
