from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Name = Annotated[str, Field(min_length=1, max_length=200)]
Identifier = Annotated[str, Field(min_length=1, max_length=100)]
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudentInput(Input):
    first_name: Name
    last_name: Name
    guardian_ids: list[Identifier] = Field(min_length=1, max_length=10)


class GuardianInput(Input):
    display_name: Name


class DriverInput(Input):
    display_name: Name


class BusAssignmentInput(Input):
    default_driver_id: Identifier | None = None


class BusInput(BusAssignmentInput):
    bus_code: Identifier
    plate_number: Identifier
    passenger_capacity: int = Field(gt=0, le=100)


class StopInput(Input):
    name: Name
    latitude: Latitude
    longitude: Longitude


class Assignment(Input):
    student_id: Identifier
    pickup_sequence: int = Field(ge=0)
    dropoff_sequence: int = Field(ge=1)


class TripInput(Input):
    trip_code: Identifier
    bus_id: Identifier
    driver_id: Identifier
    service_date: date
    shift: Literal["morning", "afternoon"]
    trip_type: Literal["pickup", "dropoff"]
    stop_ids: list[Identifier] = Field(min_length=2, max_length=100)
    students: list[Assignment] = Field(min_length=1, max_length=100)


class Versioned(Input):
    expected_version: int = Field(ge=1)


class AttendanceInput(Versioned):
    status: Literal["pending", "absent", "boarded", "dropped"]
    operator_confirmed_stopped: bool = False
    override_reason: str = Field(default="", max_length=500)
    observed_at: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class StartInput(Versioned):
    route_confirmed: bool
    operator_confirmed_stopped: bool


class FinishInput(Versioned):
    physically_inspected: bool
    physically_empty: bool
    operator_confirmed_stopped: bool
    notes: str = Field(min_length=5, max_length=1000)


class LocationInput(Input):
    device_id: Identifier
    sequence_number: int = Field(ge=0)
    recorded_at: float = Field(gt=0, allow_inf_nan=False)
    latitude: Latitude
    longitude: Longitude
    accuracy_m: float = Field(ge=0, le=10000, allow_inf_nan=False)
    speed_mps: float | None = Field(default=None, ge=0, le=80, allow_inf_nan=False)


class RouteInput(Versioned):
    strategy: Literal["fixed", "nearest", "ortools"] = "fixed"


class SyncEvent(Input):
    event_id: Identifier
    trip_id: Identifier
    student_id: Identifier
    mutation: AttendanceInput


class SyncBatch(Input):
    events: list[SyncEvent] = Field(min_length=1, max_length=100)
