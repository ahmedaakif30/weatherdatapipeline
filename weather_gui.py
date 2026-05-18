"""
============================================================
  Weather Data Pipeline — GUI Edition
  Run: python weather_gui.py
  Requires: pip install requests matplotlib
============================================================
"""

# ── Standard library ─────────────────────────────────────
import os
import sys
import sqlite3
import logging
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# ── Third-party ───────────────────────────────────────────
try:
    import requests
except ImportError:
    sys.exit("Missing library. Run:  pip install requests matplotlib")

try:
    import matplotlib
    matplotlib.use("TkAgg")                          # embed in tkinter
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False


# ════════════════════════════════════════════════════════
#  COLOUR PALETTE  (change these to retheme the whole app)
# ════════════════════════════════════════════════════════
C = {
    "bg":        "#0f172a",   # main window background
    "panel":     "#1e293b",   # card / panel background
    "border":    "#334155",   # subtle borders
    "accent":    "#38bdf8",   # blue highlight
    "accent2":   "#818cf8",   # purple highlight
    "success":   "#4ade80",   # green status
    "warning":   "#fb923c",   # orange warning
    "danger":    "#f87171",   # red error
    "text":      "#f1f5f9",   # primary text
    "muted":     "#94a3b8",   # secondary / dim text
    "entry_bg":  "#1e293b",   # input background
    "btn":       "#0ea5e9",   # button colour
    "btn_hover": "#38bdf8",   # button hover
    "card1":     "#1e3a5f",
    "card2":     "#1a3a2f",
    "card3":     "#2d1f3d",
    "card4":     "#3a2a1a",
}

# Weather emoji map (condition word → emoji)
WEATHER_ICONS = {
    "clear":      "☀️",
    "sun":        "☀️",
    "cloud":      "☁️",
    "rain":       "🌧️",
    "drizzle":    "🌦️",
    "thunder":    "⛈️",
    "storm":      "⛈️",
    "snow":       "❄️",
    "mist":       "🌫️",
    "fog":        "🌫️",
    "haze":       "🌫️",
    "smoke":      "🌫️",
    "overcast":   "☁️",
}

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
DB_PATH  = "weather_data.db"


# ════════════════════════════════════════════════════════
#  PIPELINE LOGIC  (same as weather_pipeline.py)
# ════════════════════════════════════════════════════════

def init_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weather_data (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                city        TEXT    NOT NULL,
                temperature REAL    NOT NULL,
                humidity    INTEGER NOT NULL,
                description TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL
            )
        """)
        conn.commit()


def kelvin_to_celsius(k: float) -> float:
    return round(k - 273.15, 2)


def fetch_weather_data(city: str, api_key: str) -> dict | None:
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        return {"error": "no_key"}
    params = {"q": city, "appid": api_key, "units": "standard"}
    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"error": "no_connection"}
    except requests.exceptions.Timeout:
        return {"error": "timeout"}
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code
        if code == 401: return {"error": "bad_key"}
        if code == 404: return {"error": "city_not_found", "city": city}
        if code == 429: return {"error": "rate_limit"}
        return {"error": f"http_{code}"}
    except Exception as e:
        return {"error": str(e)}


def process_weather_data(raw: dict) -> dict | None:
    try:
        return {
            "city":        raw["name"],
            "temperature": kelvin_to_celsius(raw["main"]["temp"]),
            "humidity":    raw["main"]["humidity"],
            "description": raw["weather"][0]["description"].capitalize(),
            "timestamp":   datetime.utcfromtimestamp(raw["dt"]).strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception:
        return None


def store_weather_data(record: dict) -> bool:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO weather_data (city,temperature,humidity,description,timestamp) "
                "VALUES (:city,:temperature,:humidity,:description,:timestamp)",
                record,
            )
            conn.commit()
        return True
    except sqlite3.Error:
        return False


def load_history() -> list[dict]:
    """Return all rows from the DB as a list of dicts, newest first."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM weather_data ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_icon(description: str) -> str:
    desc_lower = description.lower()
    for keyword, icon in WEATHER_ICONS.items():
        if keyword in desc_lower:
            return icon
    return "🌡️"


# ════════════════════════════════════════════════════════
#  GUI APPLICATION
# ════════════════════════════════════════════════════════

class WeatherApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # ── Window setup ─────────────────────────────────
        self.title("🌤  Weather Data Pipeline")
        self.geometry("1100x780")
        self.minsize(900, 650)
        self.configure(bg=C["bg"])

        # Make the window scale nicely
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        init_database()
        self._build_ui()
        self._refresh_table()

    # ────────────────────────────────────────────────────
    #  UI BUILDER
    # ────────────────────────────────────────────────────
    def _build_ui(self):
        """Construct every widget in the window."""

        # ── Root grid ────────────────────────────────────
        root_frame = tk.Frame(self, bg=C["bg"])
        root_frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(2, weight=1)   # table row expands

        # ── HEADER ───────────────────────────────────────
        header = tk.Frame(root_frame, bg=C["bg"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(
            header, text="🌤  Weather Data Pipeline",
            font=("Segoe UI", 20, "bold"),
            fg=C["accent"], bg=C["bg"],
        ).pack(side="left")
        tk.Label(
            header, text="OpenWeatherMap  •  SQLite  •  Real-time",
            font=("Segoe UI", 10), fg=C["muted"], bg=C["bg"],
        ).pack(side="left", padx=12, pady=6)

        # ── CONFIG PANEL (API key + cities) ──────────────
        config_frame = tk.LabelFrame(
            root_frame, text="  Configuration  ",
            font=("Segoe UI", 10, "bold"),
            fg=C["accent"], bg=C["panel"],
            bd=1, relief="flat", padx=12, pady=8,
        )
        config_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        config_frame.columnconfigure(1, weight=1)
        config_frame.columnconfigure(3, weight=2)

        # API key
        tk.Label(config_frame, text="API Key:", font=("Segoe UI", 10),
                 fg=C["muted"], bg=C["panel"]).grid(row=0, column=0, sticky="w", padx=(0,6))
        self.api_key_var = tk.StringVar(value=os.getenv("OWM_API_KEY", ""))
        api_entry = tk.Entry(
            config_frame, textvariable=self.api_key_var,
            font=("Segoe UI", 10), show="•",
            bg=C["entry_bg"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", bd=4,
        )
        api_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        # Show/hide key toggle
        self.show_key = False
        def toggle_key():
            self.show_key = not self.show_key
            api_entry.config(show="" if self.show_key else "•")
            toggle_btn.config(text="🙈 Hide" if self.show_key else "👁 Show")
        toggle_btn = self._btn(config_frame, "👁 Show", toggle_key, width=7)
        toggle_btn.grid(row=0, column=2, padx=(0, 16))

        # Cities
        tk.Label(config_frame, text="Cities:", font=("Segoe UI", 10),
                 fg=C["muted"], bg=C["panel"]).grid(row=0, column=3, sticky="w", padx=(0,6))
        self.cities_var = tk.StringVar(value="Kuala Lumpur, Klang, Petaling Jaya")
        tk.Entry(
            config_frame, textvariable=self.cities_var,
            font=("Segoe UI", 10),
            bg=C["entry_bg"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", bd=4,
        ).grid(row=0, column=4, sticky="ew", padx=(0, 10))
        config_frame.columnconfigure(4, weight=3)

        # Fetch button
        self.fetch_btn = self._btn(
            config_frame, "⬇  Fetch Weather", self._on_fetch,
            width=16, accent=True,
        )
        self.fetch_btn.grid(row=0, column=5, padx=(0, 4))

        # ── WEATHER CARDS ROW ─────────────────────────────
        self.cards_frame = tk.Frame(root_frame, bg=C["bg"])
        self.cards_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self._show_placeholder_cards()

        # ── NOTEBOOK (Table + Chart tabs) ─────────────────
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",         background=C["bg"],   borderwidth=0)
        style.configure("TNotebook.Tab",     background=C["panel"],
                        foreground=C["muted"], padding=[14, 5],
                        font=("Segoe UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", C["bg"])])

        notebook = ttk.Notebook(root_frame)
        notebook.grid(row=3, column=0, sticky="nsew", pady=(0, 6))
        root_frame.rowconfigure(3, weight=2)

        # ── TAB 1 : History table ─────────────────────────
        table_tab = tk.Frame(notebook, bg=C["panel"])
        notebook.add(table_tab, text="  📋  Data History  ")
        self._build_table(table_tab)

        # ── TAB 2 : Chart ─────────────────────────────────
        chart_tab = tk.Frame(notebook, bg=C["panel"])
        notebook.add(chart_tab, text="  📈  Temperature Chart  ")
        self._build_chart_tab(chart_tab)

        # ── STATUS BAR ────────────────────────────────────
        status_bar = tk.Frame(root_frame, bg=C["border"], height=1)
        status_bar.grid(row=4, column=0, sticky="ew")

        self.status_var = tk.StringVar(value="Ready — enter your API key and click Fetch Weather.")
        self.status_colour = tk.StringVar(value=C["muted"])
        self.status_label = tk.Label(
            root_frame, textvariable=self.status_var,
            font=("Segoe UI", 9), fg=C["muted"], bg=C["bg"], anchor="w",
        )
        self.status_label.grid(row=5, column=0, sticky="ew", pady=(2, 0))

    # ────────────────────────────────────────────────────
    #  WEATHER CARDS
    # ────────────────────────────────────────────────────
    def _show_placeholder_cards(self):
        """Show empty placeholder cards before data is fetched."""
        for w in self.cards_frame.winfo_children():
            w.destroy()
        for i, label in enumerate(["City 1", "City 2", "City 3"]):
            colours = [C["card1"], C["card2"], C["card3"]]
            card = tk.Frame(self.cards_frame, bg=colours[i % len(colours)],
                            padx=18, pady=14, bd=0)
            card.pack(side="left", expand=True, fill="x", padx=6)
            tk.Label(card, text="—", font=("Segoe UI", 28),
                     fg=C["muted"], bg=colours[i % len(colours)]).pack()
            tk.Label(card, text=label, font=("Segoe UI", 11, "bold"),
                     fg=C["muted"], bg=colours[i % len(colours)]).pack()
            tk.Label(card, text="Fetch data to see weather",
                     font=("Segoe UI", 9), fg=C["border"],
                     bg=colours[i % len(colours)]).pack()

    def _render_weather_cards(self, records: list[dict]):
        """Replace placeholder cards with real weather data cards."""
        for w in self.cards_frame.winfo_children():
            w.destroy()

        card_colours = [C["card1"], C["card2"], C["card3"], C["card4"]]
        self.cards_frame.columnconfigure(list(range(len(records))), weight=1)

        for i, rec in enumerate(records):
            bg = card_colours[i % len(card_colours)]
            card = tk.Frame(self.cards_frame, bg=bg, padx=18, pady=14)
            card.pack(side="left", expand=True, fill="x", padx=6)

            icon = get_icon(rec["description"])
            tk.Label(card, text=icon, font=("Segoe UI", 32),
                     bg=bg).pack()
            tk.Label(card, text=rec["city"],
                     font=("Segoe UI", 13, "bold"), fg=C["text"], bg=bg).pack()
            tk.Label(card, text=f"{rec['temperature']} °C",
                     font=("Segoe UI", 22, "bold"), fg=C["accent"], bg=bg).pack(pady=2)
            tk.Label(card, text=rec["description"],
                     font=("Segoe UI", 10), fg=C["muted"], bg=bg).pack()

            # Humidity bar
            tk.Label(card, text=f"💧  Humidity  {rec['humidity']}%",
                     font=("Segoe UI", 9), fg=C["muted"], bg=bg).pack(pady=(6, 2))
            bar_bg = tk.Frame(card, bg=C["border"], height=6)
            bar_bg.pack(fill="x", padx=4)
            bar_fill_width = int(bar_bg.winfo_reqwidth() * rec["humidity"] / 100)
            tk.Frame(bar_bg, bg=C["accent2"], height=6,
                     width=bar_fill_width).place(x=0, y=0, relwidth=rec["humidity"]/100, relheight=1)

            tk.Label(card, text=f"🕐  {rec['timestamp']} UTC",
                     font=("Segoe UI", 8), fg=C["border"], bg=bg).pack(pady=(6, 0))

    # ────────────────────────────────────────────────────
    #  DATA TABLE
    # ────────────────────────────────────────────────────
    def _build_table(self, parent):
        cols = ("id", "city", "temperature", "humidity", "description", "timestamp")
        headers = ("#", "City", "Temp (°C)", "Humidity (%)", "Description", "Timestamp (UTC)")
        widths   = (40,  160,    90,           100,           200,           160)

        style = ttk.Style()
        style.configure("Weather.Treeview",
                        background=C["panel"], foreground=C["text"],
                        fieldbackground=C["panel"], rowheight=28,
                        font=("Segoe UI", 10))
        style.configure("Weather.Treeview.Heading",
                        background=C["border"], foreground=C["accent"],
                        font=("Segoe UI", 10, "bold"))
        style.map("Weather.Treeview", background=[("selected", C["accent"])])

        frame = tk.Frame(parent, bg=C["panel"])
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(
            frame, columns=cols, show="headings",
            style="Weather.Treeview",
        )
        for col, header, w in zip(cols, headers, widths):
            self.tree.heading(col, text=header)
            self.tree.column(col, width=w, anchor="center" if col != "description" else "w")

        # Alternating row colours
        self.tree.tag_configure("even", background="#162032")
        self.tree.tag_configure("odd",  background=C["panel"])

        vsb = ttk.Scrollbar(frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # Toolbar below table
        toolbar = tk.Frame(parent, bg=C["panel"])
        toolbar.pack(fill="x", padx=10, pady=(0, 8))
        self._btn(toolbar, "🔄  Refresh Table", self._refresh_table).pack(side="left", padx=4)
        self._btn(toolbar, "🗑  Clear All Data", self._clear_data, danger=True).pack(side="left", padx=4)
        self.row_count_label = tk.Label(
            toolbar, text="", font=("Segoe UI", 9),
            fg=C["muted"], bg=C["panel"],
        )
        self.row_count_label.pack(side="right", padx=8)

    def _refresh_table(self):
        """Reload all rows from SQLite into the treeview."""
        for row in self.tree.get_children():
            self.tree.delete(row)
        rows = load_history()
        for i, rec in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                rec["id"], rec["city"], f"{rec['temperature']:.1f}",
                f"{rec['humidity']}%", rec["description"], rec["timestamp"],
            ), tags=(tag,))
        count = len(rows)
        self.row_count_label.config(text=f"{count} record{'s' if count != 1 else ''} stored")

    def _clear_data(self):
        if not messagebox.askyesno(
            "Clear All Data",
            "This will DELETE every record from the database.\nAre you sure?",
        ):
            return
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM weather_data")
            conn.commit()
        self._refresh_table()
        self._show_placeholder_cards()
        self._set_status("All records deleted.", C["warning"])

    # ────────────────────────────────────────────────────
    #  CHART TAB
    # ────────────────────────────────────────────────────
    def _build_chart_tab(self, parent):
        toolbar = tk.Frame(parent, bg=C["panel"])
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        self._btn(toolbar, "📈  Refresh Chart", self._draw_chart).pack(side="left", padx=4)
        tk.Label(toolbar, text="Shows temperature trends for all stored cities.",
                 font=("Segoe UI", 9), fg=C["muted"], bg=C["panel"]).pack(side="left", padx=8)

        # Placeholder frame where the chart canvas will live
        self.chart_frame = tk.Frame(parent, bg=C["panel"])
        self.chart_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tk.Label(
            self.chart_frame,
            text="Fetch some weather data, then click  📈 Refresh Chart",
            font=("Segoe UI", 12), fg=C["muted"], bg=C["panel"],
        ).pack(expand=True)

    def _draw_chart(self):
        if not MATPLOTLIB_OK:
            messagebox.showwarning("matplotlib missing",
                                   "Run:  pip install matplotlib")
            return

        rows = load_history()
        if not rows:
            messagebox.showinfo("No Data", "No records found. Fetch weather first.")
            return

        # Group by city
        city_data: dict[str, tuple[list, list]] = {}
        for r in rows:
            city = r["city"]
            if city not in city_data:
                city_data[city] = ([], [])
            city_data[city][0].append(datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S"))
            city_data[city][1].append(r["temperature"])

        # ── Build figure ─────────────────────────────────
        fig, ax = plt.subplots(figsize=(9, 4))
        fig.patch.set_facecolor(C["bg"])
        ax.set_facecolor("#0d1b2a")

        palette = [C["accent"], C["accent2"], C["success"], C["warning"], C["danger"]]
        for i, (city, (times, temps)) in enumerate(city_data.items()):
            colour = palette[i % len(palette)]
            sorted_pairs = sorted(zip(times, temps))
            t, v = zip(*sorted_pairs)
            ax.plot(t, v, marker="o", linewidth=2, markersize=6,
                    color=colour, label=city)

        # Format axes
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
        fig.autofmt_xdate()
        for spine in ax.spines.values():
            spine.set_edgecolor(C["border"])
        ax.tick_params(colors=C["muted"])
        ax.yaxis.label.set_color(C["muted"])
        ax.xaxis.label.set_color(C["muted"])
        ax.set_title("Temperature Trends", color=C["text"], fontsize=13, pad=10)
        ax.set_ylabel("Temperature (°C)", color=C["muted"])
        ax.grid(color=C["border"], linestyle="--", linewidth=0.6)
        ax.legend(facecolor=C["panel"], labelcolor=C["text"], framealpha=0.85)
        plt.tight_layout()

        # ── Embed in tkinter ──────────────────────────────
        for w in self.chart_frame.winfo_children():
            w.destroy()

        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        plt.close(fig)   # prevent memory leak

    # ────────────────────────────────────────────────────
    #  FETCH HANDLER  (runs pipeline in a background thread)
    # ────────────────────────────────────────────────────
    def _on_fetch(self):
        api_key = self.api_key_var.get().strip()
        raw_cities = self.cities_var.get().strip()

        # Basic validation
        if not api_key:
            self._set_status("⚠  Please enter your OpenWeatherMap API key.", C["warning"])
            return
        if not raw_cities:
            self._set_status("⚠  Please enter at least one city name.", C["warning"])
            return

        cities = [c.strip() for c in raw_cities.split(",") if c.strip()]

        # Disable button while fetching
        self.fetch_btn.config(state="disabled", text="⏳  Fetching…")
        self._set_status(f"Fetching data for: {', '.join(cities)} …", C["accent"])

        # Run in a separate thread so the UI stays responsive
        threading.Thread(
            target=self._fetch_worker,
            args=(cities, api_key),
            daemon=True,
        ).start()

    def _fetch_worker(self, cities: list[str], api_key: str):
        """Background thread: fetch → process → store → update UI."""
        results = []
        errors  = []

        for city in cities:
            raw = fetch_weather_data(city, api_key)

            if raw is None or "error" in raw:
                err = (raw or {}).get("error", "unknown")
                errors.append(self._error_message(err, city))
                continue

            record = process_weather_data(raw)
            if record is None:
                errors.append(f"Could not parse data for '{city}'.")
                continue

            if store_weather_data(record):
                results.append(record)
            else:
                errors.append(f"Database error while saving '{city}'.")

        # Schedule UI updates back on the main thread
        self.after(0, self._on_fetch_done, results, errors)

    def _on_fetch_done(self, results: list[dict], errors: list[str]):
        """Called on the main thread after fetching completes."""
        self.fetch_btn.config(state="normal", text="⬇  Fetch Weather")

        if results:
            # Show latest result per city as cards
            latest: dict[str, dict] = {}
            for rec in results:
                latest[rec["city"]] = rec
            self._render_weather_cards(list(latest.values()))
            self._refresh_table()

        if errors:
            err_text = "\n".join(errors)
            messagebox.showwarning("Fetch Issues", err_text)
            self._set_status(f"Done with {len(errors)} error(s). See popup for details.", C["warning"])
        elif results:
            self._set_status(
                f"✓  Successfully fetched & stored {len(results)} city record(s).   "
                f"Last updated: {datetime.utcnow().strftime('%H:%M:%S')} UTC",
                C["success"],
            )
        else:
            self._set_status("No data was saved. Check your API key and city names.", C["danger"])

    # ────────────────────────────────────────────────────
    #  HELPERS
    # ────────────────────────────────────────────────────
    def _set_status(self, msg: str, colour: str = C["muted"]):
        self.status_var.set(msg)
        self.status_label.config(fg=colour)

    @staticmethod
    def _error_message(error_code: str, city: str = "") -> str:
        messages = {
            "no_key":        "No API key provided. Please enter your OpenWeatherMap key.",
            "bad_key":       "Invalid API key (401). Double-check your key on openweathermap.org.",
            "no_connection": "No internet connection. Check your network.",
            "timeout":       "Request timed out. Try again in a moment.",
            "rate_limit":    "Rate limit reached (429). Wait a minute before retrying.",
            "city_not_found": f"City '{city}' not found. Check the spelling.",
        }
        return messages.get(error_code, f"Unexpected error ({error_code}) for '{city}'.")

    @staticmethod
    def _btn(parent, text: str, command, width=None, accent=False, danger=False) -> tk.Button:
        """Factory for consistently styled buttons."""
        if danger:
            bg, fg, hover = C["danger"], C["bg"], "#fca5a5"
        elif accent:
            bg, fg, hover = C["btn"], C["bg"], C["btn_hover"]
        else:
            bg, fg, hover = C["panel"], C["text"], C["border"]

        btn = tk.Button(
            parent, text=text, command=command,
            font=("Segoe UI", 10, "bold"),
            bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            width=width,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn


# ════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = WeatherApp()
    app.mainloop()