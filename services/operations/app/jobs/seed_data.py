"""Demo stations for local and staging (TP "Seed users" organizations A and B), loaded
through the station import so they follow the same rules and land in the audit trail.

The stations are made up: codes, names and coordinates are not any client's. Organization A
is in Jamaica and B in Trinidad and Tobago, as auth's seed has them.
"""

from __future__ import annotations

from app.domain.stations.importing import SENSORS, STATIONS, Table, norm_header

_STATION_HEADER = (
    "code", "name", "organization", "country", "type", "region", "latitude", "longitude",
    "elevation_m", "parameters", "status", "install_date", "logger_model", "logger_serial",
    "comms_type", "access_notes",
)
_STATIONS = [
    ("JM-KIN-001", "Kingston Harbour", "Organization A", "JM", "Synoptic", "Kingston",
     17.9714, -76.7920, 4, "AT RH BP RAIN WS WD SR", "operational", "2019-03-14",
     "CR1000X", "LG-10031", "cellular", "Gate code with the harbour office."),
    ("JM-MBJ-002", "Montego Bay Airport", "Organization A", "JM", "Aviation", "St James",
     18.5037, -77.9134, 1, "AT RH BP WS WD", "degraded", "2020-07-02",
     "CR1000X", "LG-10032", "cellular", "Airside pass needed; ask operations."),
    ("JM-BLU-003", "Blue Mountain Ridge", "Organization A", "JM", "Mountain", "St Andrew",
     18.0469, -76.5794, 1680, "AT RH RAIN SR", "offline", "2018-11-20",
     "CR300", "LG-10033", "satellite", "Four-wheel drive only; 2 h walk in the rain season."),
    ("TT-POS-001", "Port of Spain", "Organization B", "TT", "Synoptic", "Port of Spain",
     10.6596, -61.5089, 8, "AT RH BP RAIN WS WD", "operational", "2021-01-12",
     "CR1000X", "LG-20011", "cellular", ""),
    ("TT-TOB-002", "Tobago Coast", "Organization B", "TT", "Coastal", "Tobago",
     11.1490, -60.8320, 12, "AT RH WS WD", "operational", "2022-05-30",
     "CR300", "LG-20012", "radio", "Key with the lighthouse keeper."),
]

_SENSOR_HEADER = (
    "station_code", "kind", "manufacturer", "model", "serial", "parameter", "installed_at",
    "last_calibrated_at", "default_calibration_interval_days",
)
_SENSORS = [
    ("JM-KIN-001", "sensor", "Vaisala", "HMP155", "V-23001", "AT", "2019-03-14", "2026-01-10", 365),
    ("JM-KIN-001", "sensor", "Vaisala", "HMP155", "V-23002", "RH", "2019-03-14", "2026-01-10", 365),
    ("JM-KIN-001", "sensor", "Vaisala", "PTB330", "V-41007", "BP", "2019-03-14", "2025-08-02", 730),
    ("JM-KIN-001", "sensor", "Texas Electronics", "TR-525M", "TE-8812", "RAIN", "2023-06-01",
     "2025-10-01", 365),
    ("JM-KIN-001", "sensor", "Gill", "WindSonic", "G-55120", "WS", "2019-03-14", "2025-11-20", 730),
    ("JM-KIN-001", "sensor", "Gill", "WindSonic", "G-55121", "WD", "2019-03-14", "2025-11-20", 730),
    ("JM-KIN-001", "sensor", "Kipp & Zonen", "SMP3", "KZ-3301", "SR", "2019-03-14", "2024-09-15",
     730),
    ("JM-KIN-001", "battery", "Trojan", "SCS200", "B-0091", "", "2024-02-01", "", ""),
    ("JM-MBJ-002", "sensor", "Vaisala", "HMP155", "V-23011", "AT", "2020-07-02", "2025-11-05", 365),
    ("JM-MBJ-002", "sensor", "Vaisala", "HMP155", "V-23012", "RH", "2020-07-02", "2025-11-05", 365),
    ("JM-MBJ-002", "sensor", "Gill", "WindSonic", "G-55130", "WS", "2020-07-02", "2026-03-01", 730),
    ("JM-BLU-003", "sensor", "Vaisala", "HMP155", "V-23021", "AT", "2018-11-20", "2025-02-14", 365),
    ("TT-POS-001", "sensor", "Vaisala", "HMP155", "V-23031", "AT", "2021-01-12", "2026-06-20", 365),
    ("TT-POS-001", "sensor", "Vaisala", "PTB330", "V-41017", "BP", "2021-01-12", "2026-04-11", 730),
    ("TT-POS-001", "sensor", "Texas Electronics", "TR-525M", "TE-8820", "RAIN", "2021-01-12",
     "2025-12-01", 365),
    ("TT-TOB-002", "sensor", "Gill", "WindSonic", "G-55140", "WS", "2022-05-30", "2026-02-02", 730),
]


def tables() -> dict[str, Table]:
    def table(header: tuple[str, ...], rows: list[tuple[object, ...]]) -> Table:
        names = [norm_header(h) for h in header]
        return [(i + 2, dict(zip(names, row, strict=True))) for i, row in enumerate(rows)]

    return {STATIONS: table(_STATION_HEADER, list(_STATIONS)),
            SENSORS: table(_SENSOR_HEADER, list(_SENSORS))}
