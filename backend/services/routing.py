import math

import httpx
from fastapi import HTTPException

DEMO_COORDINATES = {(24.4539, 54.3773), (24.455, 54.379), (24.457, 54.382)}


def nearest_order(matrix):
    end = len(matrix) - 1
    remaining = set(range(1, end))
    result = [0]
    while remaining:
        node = min(remaining, key=lambda j: matrix[result[-1]][j])
        remaining.remove(node)
        result.append(node)
    return result + [end]


def optimize_order(matrix):
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError as exc:
        raise HTTPException(503, "Install requirements-routing.txt to enable OR-Tools") from exc
    manager = pywrapcp.RoutingIndexManager(len(matrix), 1, [0], [len(matrix) - 1])
    routing = pywrapcp.RoutingModel(manager)
    callback = routing.RegisterTransitCallback(lambda a, b: int(matrix[manager.IndexToNode(a)][manager.IndexToNode(b)]))
    routing.SetArcCostEvaluatorOfAllVehicles(callback)
    options = pywrapcp.DefaultRoutingSearchParameters()
    options.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    options.time_limit.seconds = 2
    solution = routing.SolveWithParameters(options)
    if not solution:
        raise HTTPException(422, "No routing solution found")
    result, index = [], routing.Start(0)
    while not routing.IsEnd(index):
        result.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    return result + [manager.IndexToNode(index)]


def plan_route(stops, settings, strategy="fixed", client=None):
    if settings.public_demo_services and (settings.mode != 'demo' or any((s.latitude, s.longitude) not in DEMO_COORDINATES for s in stops)):
        raise HTTPException(403, "Public routing is permitted only for the fixed fictional demo stops. Configure private OSRM for other coordinates.")
    if not settings.osrm_url:
        raise HTTPException(503, "OSRM is not configured; no road ETA is available")
    coordinates = ";".join(f"{s.longitude},{s.latitude}" for s in stops)
    try:
        with httpx.Client(timeout=10) if client is None else client as sender:
            order = list(range(len(stops)))
            if strategy != "fixed":
                response = sender.get(f"{settings.osrm_url}/table/v1/driving/{coordinates}", params={"annotations": "duration"})
                response.raise_for_status()
                table = response.json()
                matrix = table.get("durations")
                if (table.get("code") != "Ok" or not isinstance(matrix, list)
                        or len(matrix) != len(stops)
                        or any(not isinstance(row, list) or len(row) != len(stops) for row in matrix)
                        or any(isinstance(v, bool) or not isinstance(v, (int, float))
                               or not math.isfinite(v) or v < 0 for row in matrix for v in row)):
                    raise ValueError("Invalid or unreachable road matrix")
                order = nearest_order(matrix) if strategy == "nearest" else optimize_order(matrix)
            coordinates = ";".join(f"{stops[i].longitude},{stops[i].latitude}" for i in order)
            response = sender.get(f"{settings.osrm_url}/route/v1/driving/{coordinates}",
                                  params={"overview": "full", "geometries": "geojson"})
            response.raise_for_status()
            result = response.json()
            if result.get("code") != "Ok" or not result.get("routes"):
                raise ValueError("No road route")
            route = result["routes"][0]
            return {"source": "osrm", "strategy": strategy, "stop_order": [stops[i].id for i in order],
                    "distance_m": route["distance"], "eta_s": route["duration"],
                    "geometry": route["geometry"], "legs": [
                        {"distance_m": leg["distance"], "eta_s": leg["duration"]} for leg in route["legs"]],
                    "traffic_aware": False, "requires_bus_route_review": True}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Routing unavailable; the previously approved route is unchanged") from exc
