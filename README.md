# SafeSense — BusSafetyAI

A school-bus dashboard with camera-based person detection, live location, student attendance, trip management, and post-trip inspection workflows. The current application uses React, FastAPI, and a custom YOLO26s model.

[Hosted dashboard](https://kal123new-bussafetyai.hf.space/) · [Hugging Face Space](https://huggingface.co/spaces/Kal123new/BusSafetyAI) · [Model details](models/MODEL_CARD.md)

The hosted app requires an account token. Hosting runs independently of the developer's laptop; availability depends on the hosting service. Camera detection and maps require connectivity to their services.

## Features

- Browser camera input from the device opening the dashboard, with permission. Frames are processed by the backend model.
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

## Hugging Face deployment

The included Dockerfile builds the frontend and starts the authenticated Space entry point on port 7860. Create a Docker Space and push this source to its repository. Configure these **Space Secrets**, never commit their values:

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
