"""DB-only simulator. Inserts into weather_data and lets DMS handle CDC.

No Kinesis push. Just PostgreSQL inserts, same as the real black-box pipeline.

Usage: python -m simulator.db_only --scenario HEAT_WAVE --duration 10
"""

import argparse
import os
import random
import time
from datetime import datetime, timezone

import h3
import psycopg2

from src.shared.constants import H3_RESOLUTION

CITIES = {
    "buenos_aires": (-34.6037, -58.3816),
    "sao_paulo": (-23.5505, -46.6333),
    "mexico_city": (19.4326, -99.1332),
    "bogota": (4.7110, -74.0721),
    "lima": (-12.0464, -77.0428),
}

METRICS = ["temperature", "humidity", "wind_speed", "pressure", "precipitation"]


def _random_value(metric: str, extreme: bool = False) -> float:
    ranges = {
        "temperature": (35.0, 48.0) if extreme else (15.0, 35.0),
        "humidity": (5.0, 25.0) if extreme else (30.0, 80.0),
        "wind_speed": (60.0, 150.0) if extreme else (5.0, 40.0),
        "pressure": (950.0, 980.0) if extreme else (1000.0, 1025.0),
        "precipitation": (50.0, 200.0) if extreme else (0.0, 20.0),
    }
    low, high = ranges.get(metric, (0.0, 100.0))
    return round(random.uniform(low, high), 2)


def insert(cursor, lat, lon, metric, value):
    cursor.execute(
        "INSERT INTO weather_data (location_lat, location_lon, metric_type, value, recorded_at) VALUES (%s,%s,%s,%s,%s)",
        (lat, lon, metric, value, datetime.now(timezone.utc)),
    )


def run(conn, scenario, duration, events):
    cursor = conn.cursor()
    count = 0

    if scenario == "NORMAL":
        start = time.time()
        while time.time() - start < duration:
            city = random.choice(list(CITIES.keys()))
            lat, lon = CITIES[city]
            lat += random.uniform(-0.05, 0.05)
            lon += random.uniform(-0.05, 0.05)
            metric = random.choice(METRICS)
            value = _random_value(metric)
            insert(cursor, lat, lon, metric, value)
            conn.commit()
            count += 1
            print(f"  [{count}] {city}: {metric}={value:.1f}")
            time.sleep(1)

    elif scenario == "HEAT_WAVE":
        lat, lon = CITIES["buenos_aires"]
        start = time.time()
        while time.time() - start < duration:
            insert(cursor, lat, lon, "temperature", random.uniform(38.5, 45.0))
            insert(cursor, lat, lon, "humidity", random.uniform(5.0, 19.0))
            conn.commit()
            count += 2
            print(f"  [{count}] buenos_aires: temp+humidity")
            time.sleep(0.5)

    elif scenario == "COLD_SNAP":
        lat, lon = CITIES["sao_paulo"]
        start = time.time()
        while time.time() - start < duration:
            insert(cursor, lat, lon, "temperature", random.uniform(-15.0, -5.5))
            insert(cursor, lat, lon, "wind_speed", random.uniform(61.0, 120.0))
            conn.commit()
            count += 2
            print(f"  [{count}] sao_paulo: temp+wind")
            time.sleep(0.5)

    elif scenario == "SEVERE_STORM":
        lat, lon = CITIES["buenos_aires"]
        cells = list(h3.grid_disk(h3.latlng_to_cell(lat, lon, H3_RESOLUTION), 2))
        for i in range(events):
            cell = random.choice(cells)
            clat, clon = h3.cell_to_latlng(cell)
            insert(cursor, clat, clon, random.choice(METRICS), _random_value(random.choice(METRICS), extreme=True))
            count += 1
            if count % 100 == 0:
                conn.commit()
                print(f"  [{count}] burst: {count}/{events}")
        conn.commit()

    cursor.close()
    print(f"\n{scenario}: Inserted {count} rows into weather_data")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["NORMAL", "HEAT_WAVE", "COLD_SNAP", "SEVERE_STORM"], default="NORMAL")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--events", type=int, default=100)
    default_dsn = os.environ.get("AGROBOT_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/agrobot")
    # Convert asyncpg URL to psycopg2 format
    default_dsn = default_dsn.replace("postgresql+asyncpg://", "postgresql://")
    parser.add_argument("--dsn", default=default_dsn)
    args = parser.parse_args()

    conn = psycopg2.connect(args.dsn)
    print(f"Connected. Scenario: {args.scenario}")
    try:
        run(conn, args.scenario, args.duration, args.events)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
