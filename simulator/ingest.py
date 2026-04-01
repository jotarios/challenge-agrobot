"""Weather data simulator for local development and testing.

In local dev (no DMS), pushes events directly to Kinesis so the
Matching Engine can consume them. Also inserts into PostgreSQL
to keep the weather_data table populated.

Scenarios:
  NORMAL       - Steady-state: 1 event/sec across random cities
  HEAT_WAVE    - temp > 38C, humidity < 20% in Buenos Aires
  COLD_SNAP    - temp < -5C, wind > 60km/h in Sao Paulo
  SEVERE_STORM - Burst of 10k+ events across H3 k-ring from Buenos Aires center

Usage:
  python -m simulator.ingest --scenario NORMAL --duration 30
  python -m simulator.ingest --scenario HEAT_WAVE --duration 10
  python -m simulator.ingest --scenario SEVERE_STORM --events 100
"""

import argparse
import json
import random
import time
from datetime import datetime, timezone

import boto3
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


class EventPublisher:
    """Writes events to both PostgreSQL and Kinesis."""

    def __init__(self, dsn: str, kinesis_endpoint: str, stream_name: str):
        self.conn = psycopg2.connect(dsn)
        self.cursor = self.conn.cursor()
        self.kinesis = boto3.client(
            "kinesis",
            region_name="us-east-1",
            endpoint_url=kinesis_endpoint,
        )
        self.stream_name = stream_name
        self.count = 0

    def publish(self, lat: float, lon: float, metric: str, value: float):
        now = datetime.now(timezone.utc)

        # Insert into DB (simulates black-box pipeline)
        self.cursor.execute(
            """INSERT INTO weather_data (location_lat, location_lon, metric_type, value, recorded_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (lat, lon, metric, value, now),
        )

        # Push to Kinesis (simulates DMS CDC, since DMS isn't available locally)
        record = json.dumps({
            "location_lat": lat,
            "location_lon": lon,
            "metric_type": metric,
            "value": value,
            "recorded_at": now.isoformat(),
        })
        self.kinesis.put_record(
            StreamName=self.stream_name,
            Data=record.encode("utf-8"),
            PartitionKey=f"{lat:.4f},{lon:.4f}",
        )
        self.count += 1

    def flush(self):
        self.conn.commit()

    def close(self):
        self.cursor.close()
        self.conn.close()


def scenario_normal(pub: EventPublisher, duration_sec: int = 60):
    start = time.time()
    while time.time() - start < duration_sec:
        city = random.choice(list(CITIES.keys()))
        lat, lon = CITIES[city]
        lat += random.uniform(-0.05, 0.05)
        lon += random.uniform(-0.05, 0.05)
        metric = random.choice(METRICS)
        value = _random_value(metric)
        pub.publish(lat, lon, metric, value)
        pub.flush()
        print(f"  [{pub.count}] {city}: {metric}={value:.1f}")
        time.sleep(1)
    print(f"\nNORMAL: Published {pub.count} events over {duration_sec}s")


def scenario_heat_wave(pub: EventPublisher, duration_sec: int = 30):
    lat, lon = CITIES["buenos_aires"]
    start = time.time()
    while time.time() - start < duration_sec:
        temp = random.uniform(38.5, 45.0)
        hum = random.uniform(5.0, 19.0)
        pub.publish(lat, lon, "temperature", temp)
        pub.publish(lat, lon, "humidity", hum)
        pub.flush()
        print(f"  [{pub.count}] buenos_aires: temp={temp:.1f} humidity={hum:.1f}")
        time.sleep(0.5)
    print(f"\nHEAT_WAVE: Published {pub.count} events over {duration_sec}s")


def scenario_cold_snap(pub: EventPublisher, duration_sec: int = 30):
    lat, lon = CITIES["sao_paulo"]
    start = time.time()
    while time.time() - start < duration_sec:
        temp = random.uniform(-15.0, -5.5)
        wind = random.uniform(61.0, 120.0)
        pub.publish(lat, lon, "temperature", temp)
        pub.publish(lat, lon, "wind_speed", wind)
        pub.flush()
        print(f"  [{pub.count}] sao_paulo: temp={temp:.1f} wind={wind:.1f}")
        time.sleep(0.5)
    print(f"\nCOLD_SNAP: Published {pub.count} events over {duration_sec}s")


def scenario_severe_storm(pub: EventPublisher, num_events: int = 10000):
    lat, lon = CITIES["buenos_aires"]
    center_h3 = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
    ring_cells = list(h3.grid_disk(center_h3, 2))

    for i in range(num_events):
        cell = random.choice(ring_cells)
        cell_lat, cell_lon = h3.cell_to_latlng(cell)
        metric = random.choice(METRICS)
        value = _random_value(metric, extreme=True)
        pub.publish(cell_lat, cell_lon, metric, value)
        if (i + 1) % 100 == 0:
            pub.flush()
            print(f"  [{pub.count}] burst: {i+1}/{num_events}")
    pub.flush()
    print(f"\nSEVERE_STORM: Published {pub.count} events across {len(ring_cells)} H3 cells")


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


def main():
    parser = argparse.ArgumentParser(description="Agrobot weather data simulator")
    parser.add_argument(
        "--scenario",
        choices=["NORMAL", "HEAT_WAVE", "COLD_SNAP", "SEVERE_STORM"],
        default="NORMAL",
    )
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    parser.add_argument("--events", type=int, default=100, help="Number of events (SEVERE_STORM)")
    parser.add_argument(
        "--dsn",
        default="postgresql://postgres:postgres@localhost:5432/agrobot",
    )
    parser.add_argument(
        "--kinesis-endpoint",
        default="http://localhost:4566",
    )
    parser.add_argument(
        "--stream",
        default="weather-events",
    )
    args = parser.parse_args()

    pub = EventPublisher(args.dsn, args.kinesis_endpoint, args.stream)
    print(f"Connected. Running scenario: {args.scenario}")

    scenarios = {
        "NORMAL": lambda: scenario_normal(pub, args.duration),
        "HEAT_WAVE": lambda: scenario_heat_wave(pub, args.duration),
        "COLD_SNAP": lambda: scenario_cold_snap(pub, args.duration),
        "SEVERE_STORM": lambda: scenario_severe_storm(pub, args.events),
    }

    try:
        scenarios[args.scenario]()
    finally:
        pub.close()


if __name__ == "__main__":
    main()
