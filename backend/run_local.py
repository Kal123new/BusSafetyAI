"""Start an isolated synthetic demo without changing Windows execution policy."""
import argparse
import os
import socket
import tempfile
from pathlib import Path

import uvicorn

from .app import create_app
from .config import Settings
from .manage import migrate, seed
from .storage import demo_database


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    maps = parser.add_mutually_exclusive_group()
    maps.add_argument("--public-demo-maps", action="store_true", help="Allow public routing/tiles for the fixed fictional demo stops only")
    maps.add_argument("--public-live-maps", action="store_true", help="Explicit consent to share real map areas and route coordinates with public OSM/OSRM services")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65525:
        parser.error("Choose a port between 1024 and 65525")
    port = None
    for candidate in range(args.port, args.port + 10):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            port = candidate
            break
    if port is None:
        parser.error("No free local port in the requested range")
    path = demo_database()
    public_maps = args.public_demo_maps or args.public_live_maps
    settings = Settings(database_url=f"sqlite:///{path.as_posix()}", mode="demo",
                        model_path=os.getenv("YOLO_MODEL_PATH", str(Path(__file__).resolve().parents[1] / "models" / "best.pt")),
                        confidence=float(os.getenv("YOLO_CONFIDENCE", "0.45")),
                        tile_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" if public_maps else os.getenv("MAP_TILE_URL", ""),
                        tile_attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' if public_maps else os.getenv("MAP_TILE_ATTRIBUTION", ""),
                        public_demo_services=args.public_demo_maps,
                        public_live_locations=args.public_live_maps,
                        osrm_url="https://router.project-osrm.org" if public_maps else os.getenv("OSRM_URL", "").rstrip("/"))
    migrate(settings.database_url)
    app = create_app(settings)
    with app.state.sessions.begin() as db:
        seed(db)
    print(f"Synthetic local demo: http://127.0.0.1:{port}/docs", flush=True)
    print("Persistent local SQLite storage; no external notifications. Do not tunnel demo mode.", flush=True)
    if args.public_live_maps:
        print("Public live maps enabled: map areas go to OpenStreetMap and route coordinates to OSRM. Browser GPS remains opt-in.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, proxy_headers=False)


if __name__ == "__main__":
    main()
