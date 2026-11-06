# SafeSense — BusSafetyAI

> **Compatibility: computers / large screens only.** Use a desktop or laptop with a modern Chrome or Edge browser and a window at least 1024 CSS pixels wide. Phones and tablets are not supported. Detection performance depends on the computer's hardware.

A school-bus dashboard with camera-based person detection, live location, student attendance, trip management, and post-trip inspection workflows. The current application uses React, FastAPI, and a custom YOLO26s model.

**[Open the dashboard](https://bus-safety-ai.vercel.app/)** · [Browser hosting guide](docs/BROWSER_HOSTING.md) · [Model details](models/MODEL_CARD.md) · [Browser model download](https://github.com/Kal123new/BusSafetyAI/releases/tag/browser-model-v1)

## Browser version

The desktop browser build runs the custom model locally using WebGPU or WebAssembly. Camera images stay on the visitor's computer. An isolated public sample includes fictional students and saves only in that browser. Shared trips, administration, replacement buses, and guardian records require account-token sign-in to the configured backend.

The free-hosting configuration uses Vercel Hobby for a personal, non-commercial project and Neon Free for persistent records, within their usage limits. It does not require the developer's laptop to stay on. **Live dashboard: https://bus-safety-ai.vercel.app/** Open the link and choose “Open sample dashboard” to try the fictional sample, or sign in for shared records. The earlier Hugging Face deployment is paused and is not the browser version.

The `Browser dashboard checks` workflow verifies the build, browser model execution, public sample rendering, small-screen guard, and trip workflow tests. It does not certify model accuracy or performance on every computer. See the [hosting guide](docs/BROWSER_HOSTING.md).

## Features

- Browser camera input with permission. The new browser build processes frames locally; the original local Python mode processes them in its backend.
- Live GPS position on the map, with optional OpenStreetMap tiles and OSRM road routing.
- Expandable dashboard sections and wider camera/map panels.
- Separate administrator, driver, and guardian access.
- Student boarding/drop-off records, trip start/finish controls, stopped-bus checks, and post-trip physical inspection.
- Morning/afternoon service plans with weekdays, date ranges, holidays, bus, driver, route, and roster. Daily trips are created from plans; drivers still review and start them.
- Replacement-bus trips with capacity checks, passenger handover confirmation, transfer history, and guardian inbox updates.
- Persistent SQLite storage locally and external PostgreSQL storage for hosting.

Camera counts do not identify individual students or establish whether a bus is empty. The model detects people, including adults. Attendance and physical inspection remain separate operator responsibilities.

## Model results

The bundled checkpoint is `models/best.pt`, a custom YOLO26s model with one class, `Person`. Its recorded validation metrics are:

| Metric | Value |
| --- | ---: |
| Precision | 97.134% |
| Recall | 96.260% |
| mAP@0.50 | 98.598% |
| mAP@0.50:0.95 | 76.647% |

These are checkpoint-recorded **validation** results, not a new independent test or a claim of 97.1% overall accuracy. See the [model card](models/MODEL_CARD.md) for provenance and limitations. A reproducible comparison of model sizes or training stages also requires their individual logs, identical evaluation settings, and dataset split manifests; those materials are not included here.

## Run locally

Use Python 3.12 and Node.js 22. From a terminal:

```sh
git clone https://github.com/Kal123new/BusSafetyAI.git
cd BusSafetyAI
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```sh
source .venv/bin/activate
```

Install dependencies, build the dashboard, and start the local demo:

```sh
python -m pip install -r backend/requirements.txt
python -m pip install ultralytics==8.4.127
npm ci
npm run build
python -m backend.run_local
```

Keep the terminal open and visit `http://127.0.0.1:8000/`. If that port is occupied, use the port printed by startup. `/docs` is the API documentation. The local demo uses fictional data and persistent SQLite storage. Do not expose or tunnel demo mode publicly.

For live maps, instead start with:

```sh
python -m backend.run_local --public-live-maps
```

This enables public map/routing services: OpenStreetMap receives viewed map areas and OSRM receives routing coordinates. Allow location access in the browser. Camera access requires localhost or an HTTPS site and explicit browser permission.

## Earlier Hugging Face deployment

The Dockerfile builds the original server-inference frontend and starts the authenticated Space entry point on port 7860. This is separate from the new browser/Vercel configuration and is not a free-hosting promise. Configure these **Space Secrets**, never commit their values:

- `DATABASE_URL`: the Neon PostgreSQL connection string, including its required TLS settings.
- `SAFESENSE_INITIAL_ADMIN_TOKEN`: a random 32–200 character owner token with no internal spaces. Used to bootstrap the initial owner account.

The Space entry point applies database migrations and requires the bundled model. PostgreSQL provides durable application data independently of the container filesystem. Configure optional `MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION`, and `OSRM_URL` variables for approved map/routing providers. An empty configuration leaves external map services disabled.

GitHub stores the source and weights; GitHub Pages alone cannot run the Python inference backend. Never commit real passenger records, database backups, tokens, or `.env` files.

## Repository layout

```text
src/                   React dashboard
backend/               FastAPI, persistence, inference, trip workflows
backend/migrations/    Database schema migrations
backend/tests/         Backend workflow tests
models/best.pt         Custom YOLO26s checkpoint
models/MODEL_CARD.md   Recorded metrics and limitations
Dockerfile             Hugging Face container build
Code/                  Earlier prototype, retained for history
yolov8n.pt             Earlier base model, not used by the current app
```

## Tests

```sh
python -m pytest backend/tests/test_scheduling.py backend/tests/test_replacements.py backend/tests/test_service_edges.py
npm run build
```

The older prototype's Telegram and threat-object behavior does not describe the current one-class person detector. This repository does not include the training dataset or grant rights to third-party datasets or dependencies; review their respective terms before reuse.
