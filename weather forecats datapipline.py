"""
============================================================
  Weather Data Pipeline
  Author: Generated with Claude
  Description: Fetches, processes, stores, and visualises
               real-time weather data using OpenWeatherMap.
============================================================

HOW TO RUN
----------
1. Install dependencies:
       pip install requests matplotlib

2. Get a free API key at: https://openweathermap.org/api
   (Free tier → "Current Weather Data")

3. Set your API key as an environment variable:
       Windows  : set OWM_API_KEY=your_key_here
       Mac/Linux: export OWM_API_KEY=your_key_here

   Alternatively, paste it directly into API_KEY below (not recommended for production).

4. Run the script:
       python weather_pipeline.py

5. To plot stored temperature trends:
       python weather_pipeline.py --plot
"""

# ── Standard library ────────────────────────────────────────────────────────
import os
import sys
import sqlite3
import logging
import argparse
from datetime import datetime

# ── Third-party libraries ────────────────────────────────────────────────────
try:
    import requests
except ImportError:
    sys.exit("❌  'requests' is not installed. Run: pip install requests")

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("⚠️  'matplotlib' not found – plotting disabled. Run: pip install matplotlib")


# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

# Pull the API key from the environment (recommended) or hard-code it here.
API_KEY: str = os.getenv("OWM_API_KEY", "e5be9fc639e5994e9fbc35694d8f1593")

# Base URL for OpenWeatherMap's Current Weather endpoint
BASE_URL: str = "https://api.openweathermap.org/data/2.5/weather"

# Cities to fetch weather data for (add or remove as you like)
CITIES: list[str] = ["Kuala Lumpur", "Klang", "Petaling Jaya"]

# SQLite database file path
DB_PATH: str = "weather_data.db"

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
#  DATABASE HELPERS
# ════════════════════════════════════════════════════════════════════════════

def init_database(db_path: str = DB_PATH) -> None:
    """
    Create the SQLite database and the `weather_data` table if they
    don't already exist.  Safe to call on every run.
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weather_data (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                city        TEXT    NOT NULL,
                temperature REAL    NOT NULL,   -- Celsius
                humidity    INTEGER NOT NULL,   -- %
                description TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL    -- ISO-8601
            )
        """)
        conn.commit()
    logger.info("Database ready: %s", db_path)


# ════════════════════════════════════════════════════════════════════════════
#  STEP 1 – FETCH
# ════════════════════════════════════════════════════════════════════════════

def fetch_weather_data(city: str, api_key: str = API_KEY) -> dict | None:
    """
    Call the OpenWeatherMap Current Weather API for *city*.

    Returns the raw JSON response as a dict, or None on failure.
    """
    if api_key == "YOUR_API_KEY_HERE" or not api_key:
        logger.error(
            "No API key configured. Set the OWM_API_KEY environment variable "
            "or edit API_KEY in the script."
        )
        return None

    params = {
        "q":     city,
        "appid": api_key,
        "units": "standard",   # Kelvin – we convert manually to show the step
    }

    try:
        logger.info("Fetching weather for '%s' …", city)
        response = requests.get(BASE_URL, params=params, timeout=10)

        # Raise an HTTPError for 4xx / 5xx status codes
        response.raise_for_status()

        data = response.json()
        logger.info("  ✓  Received data for '%s'", data.get("name", city))
        return data

    except requests.exceptions.ConnectionError:
        logger.error("  ✗  No internet connection or the API is unreachable.")
    except requests.exceptions.Timeout:
        logger.error("  ✗  Request timed out for '%s'.", city)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code
        if status == 401:
            logger.error("  ✗  Invalid API key (401). Check your OWM_API_KEY.")
        elif status == 404:
            logger.error("  ✗  City '%s' not found (404).", city)
        elif status == 429:
            logger.error("  ✗  Rate limit exceeded (429). Wait before retrying.")
        else:
            logger.error("  ✗  HTTP error %s for '%s': %s", status, city, exc)
    except requests.exceptions.RequestException as exc:
        logger.error("  ✗  Unexpected request error: %s", exc)

    return None


# ════════════════════════════════════════════════════════════════════════════
#  STEP 2 – PROCESS / CLEAN
# ════════════════════════════════════════════════════════════════════════════

def kelvin_to_celsius(kelvin: float) -> float:
    """Convert a temperature in Kelvin to Celsius, rounded to 2 d.p."""
    return round(kelvin - 273.15, 2)


def process_weather_data(raw: dict) -> dict | None:
    """
    Extract and clean the fields we care about from the raw API response.

    Returns a clean dict, or None if essential fields are missing.
    """
    try:
        city        = raw["name"]
        temp_k      = raw["main"]["temp"]
        humidity    = raw["main"]["humidity"]
        description = raw["weather"][0]["description"].capitalize()
        # Use the API's UNIX timestamp and convert to a readable ISO string
        timestamp   = datetime.utcfromtimestamp(raw["dt"]).strftime("%Y-%m-%d %H:%M:%S")

        cleaned = {
            "city":        city,
            "temperature": kelvin_to_celsius(temp_k),
            "humidity":    humidity,
            "description": description,
            "timestamp":   timestamp,
        }

        logger.info(
            "  Processed → %s | %.1f°C | %d%% humidity | %s | %s",
            cleaned["city"],
            cleaned["temperature"],
            cleaned["humidity"],
            cleaned["description"],
            cleaned["timestamp"],
        )
        return cleaned

    except (KeyError, IndexError, TypeError) as exc:
        logger.error("  ✗  Failed to parse API response: %s", exc)
        return None


# ════════════════════════════════════════════════════════════════════════════
#  STEP 3 – STORE
# ════════════════════════════════════════════════════════════════════════════

def store_weather_data(record: dict, db_path: str = DB_PATH) -> bool:
    """
    Insert a single cleaned weather record into the SQLite database.

    Returns True on success, False on failure.
    """
    sql = """
        INSERT INTO weather_data (city, temperature, humidity, description, timestamp)
        VALUES (:city, :temperature, :humidity, :description, :timestamp)
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(sql, record)
            conn.commit()
        logger.info("  ✓  Stored record for '%s'", record["city"])
        return True
    except sqlite3.Error as exc:
        logger.error("  ✗  Database error while storing data: %s", exc)
        return False


# ════════════════════════════════════════════════════════════════════════════
#  STEP 4 – VISUALISE
# ════════════════════════════════════════════════════════════════════════════

def plot_temperature_trends(db_path: str = DB_PATH, cities: list[str] | None = None) -> None:
    """
    Read temperature history from the database and draw a line chart
    with one series per city.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("⚠️  matplotlib is not installed; skipping plot.")
        return

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # If no cities specified, plot all cities found in the DB
        if not cities:
            rows = conn.execute("SELECT DISTINCT city FROM weather_data").fetchall()
            cities = [r["city"] for r in rows]

        if not cities:
            print("No data in the database yet. Run the pipeline first.")
            return

        fig, ax = plt.subplots(figsize=(12, 5))
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#16213e")

        colours = ["#e94560", "#0f3460", "#533483", "#e0a800", "#00b4d8"]

        plotted_any = False
        for i, city in enumerate(cities):
            rows = conn.execute(
                """
                SELECT timestamp, temperature
                FROM   weather_data
                WHERE  city = ?
                ORDER  BY timestamp
                """,
                (city,),
            ).fetchall()

            if not rows:
                logger.warning("No records found for '%s'. Skipping.", city)
                continue

            timestamps   = [datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S") for r in rows]
            temperatures = [r["temperature"] for r in rows]
            colour       = colours[i % len(colours)]

            ax.plot(
                timestamps, temperatures,
                marker="o", linewidth=2, markersize=5,
                color=colour, label=city,
            )
            plotted_any = True

        if not plotted_any:
            print("No temperature data to plot.")
            plt.close(fig)
            return

        # ── Formatting ──────────────────────────────────────────────────────
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
        fig.autofmt_xdate()

        for spine in ax.spines.values():
            spine.set_edgecolor("#444466")

        ax.tick_params(colors="#aaaacc")
        ax.yaxis.label.set_color("#aaaacc")
        ax.xaxis.label.set_color("#aaaacc")
        ax.title.set_color("#ffffff")

        ax.set_title("Temperature Trends", fontsize=16, pad=14)
        ax.set_ylabel("Temperature (°C)")
        ax.set_xlabel("Timestamp (UTC)")
        ax.grid(color="#2a2a4a", linestyle="--", linewidth=0.7)
        ax.legend(facecolor="#1a1a2e", labelcolor="#ccccee", framealpha=0.8)

        plt.tight_layout()
        plt.savefig("temperature_trends.png", dpi=150, facecolor=fig.get_facecolor())
        logger.info("Chart saved → temperature_trends.png")
        plt.show()


# ════════════════════════════════════════════════════════════════════════════
#  PIPELINE ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════

def run_pipeline(cities: list[str] = CITIES) -> None:
    """
    Full ETL cycle: fetch → process → store for every city in *cities*.
    Designed to be called by a scheduler (cron, APScheduler, etc.).
    """
    logger.info("=" * 60)
    logger.info("Pipeline run started: %s UTC", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Cities: %s", ", ".join(cities))
    logger.info("=" * 60)

    success_count = 0

    for city in cities:
        raw = fetch_weather_data(city)
        if raw is None:
            continue

        record = process_weather_data(raw)
        if record is None:
            continue

        if store_weather_data(record):
            success_count += 1

        print()  # Blank line between cities for readability

    logger.info("Pipeline complete: %d/%d cities stored successfully.", success_count, len(cities))


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """
    Parse command-line arguments and run the appropriate action.

    Usage:
        python weather_pipeline.py            # Run the ETL pipeline
        python weather_pipeline.py --plot     # Plot stored data
        python weather_pipeline.py --city "Johor Bahru" "Penang"  # Custom cities
    """
    parser = argparse.ArgumentParser(description="Weather Data Pipeline")
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Plot temperature trends from stored data instead of fetching new data.",
    )
    parser.add_argument(
        "--city",
        nargs="+",
        metavar="CITY",
        default=CITIES,
        help="One or more city names to fetch (default: %(default)s).",
    )
    args = parser.parse_args()

    # Always ensure the database + table exist before anything else
    init_database()

    if args.plot:
        plot_temperature_trends(cities=args.city if args.city != CITIES else None)
    else:
        run_pipeline(cities=args.city)


if __name__ == "__main__":
    main()