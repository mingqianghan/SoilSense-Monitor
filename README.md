# SoilSense Monitor

A PyQt6 desktop application for collecting and analyzing data from
distributed soil-moisture sensor nodes. Talks to a custom LoRa radio
MCU over UART, plots the sensor's frequency-response curves in real
time, and runs a calibrated permittivity model to estimate
volumetric water content (VWC), bulk EC, and pore EC per node.

The app pairs an interactive **Map View** (with weather panel and AI
agronomic summaries) with a **Collect Page** (serial port setup,
collection workflow, frequency-response plot, and serial log).

## Features

- **Per-node soil-property estimation** — VWC, bulk EC, pore EC, USDA
  salinity class, derived from a calibrated dielectric model.
- **Field map** with sensor pins, plot polygons, and weather forecast.
  Online via Leaflet + Google satellite tiles; offline via cached tiles
  (auto-downloaded on first online launch).
- **AI Crop Summary** — one-shot agronomic report from current sensor +
  weather data, via your choice of Claude / GPT / Gemini.
- **Per-user API key storage** in the OS credential store (Windows
  Credential Manager / macOS Keychain / Linux Secret Service).
- **Light + dark themes** with full QSS styling.

## Quick start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run the app
python AppMain.py
```

On first launch you'll be prompted to configure API keys for the AI
provider and OpenWeather. **All keys are optional** — skip and the app
runs with limited functionality; configure them later via the gear
buttons in the UI.

## Configuration

`config.json` at the project root defines the field markers, plot
polygons, and data folder paths. Edit it directly to point at your own
sensor nodes:

```jsonc
{
  "data_root": "data\\UG nodes",   // where to READ historical data
  "save_root": "data\\UG nodes",   // where to WRITE new collections
  "field": {
    "name":     "KSU Research Field",
    "location": "Manhattan, KS",
    "crop":     "Maize",
    "variety":  "P13050",
    "season":   "2026"
  },
  "markers": [ { "name": "S1", "latitude": …, "longitude": … }, … ],
  "plots":   [ { "name": "PD1", "planting_date": "…", "nodes": […],
                 "corners": [ … ] }, … ]
}
```

## API keys

The app uses two external APIs. Each end-user supplies their own key:

| Service | Free tier | Used for | Sign-up |
|---|---|---|---|
| **OpenWeather** (One Call 3.0) | ~1,000 calls/day | Weather panel + AI summary | [openweathermap.org/api/one-call-3](https://openweathermap.org/api/one-call-3) |
| **Anthropic Claude** *or* **OpenAI GPT** *or* **Google Gemini** | varies — Gemini Flash is free | AI Crop Summary | see provider docs |

> First-time OpenWeather users must subscribe to the
> **"All-in-one Weather API"** plan (One Call 3.0) before generating a key.

Keys are stored in your OS credential store via the `keyring` library —
**never written to disk in plain text** and never shipped with the app.

## Project layout

```
CommInterface_V2/
├── AppMain.py              # entry point
├── AppRoot.py              # main window + theme + tooltip system
├── HomeGui.py              # Map View page + weather panel
├── styles.py               # light + dark QSS
├── config.json
├── result.pkl              # calibrated soil model
│
├── comm/                   # UART + weather API clients (protected)
│   ├── serial_com_ctrl.py
│   ├── data_com_ctrl.py
│   └── weather_summary.py
│
├── ui/                     # Collect-page widgets
│   ├── CommCollectPage.py
│   ├── ComPanel.py
│   ├── DataCollectPanel.py
│   ├── LogPanel.py
│   ├── PlotPanel.py
│   └── SoilPropertiesPanel.py
│
├── adapters/               # Tkinter→Qt bridge proxies
│   └── bridge.py
│
├── ai/                     # AI Crop Summary + provider abstractions
│   ├── providers.py        # Claude / GPT / Gemini
│   ├── settings_dialog.py
│   └── summary_panel.py
│
├── soil/                   # Soil model + data loading
│   ├── node_loader.py
│   ├── model.py
│   ├── model_stub.py
│   └── dielectric.py
│
├── setup/                  # First-run + keys + offline-map downloader
│   ├── keys.py
│   ├── dialog.py
│   └── offline_map.py
│
└── assets/
    ├── app_icon.ico
    └── leaflet/            # Leaflet JS+CSS for offline map
```

## Development

```bash
# Reset all stored keys and clear .env (for testing first-run flow)
python -c "
import keyring, pathlib
for slot in ('openweather','anthropic','openai','gemini'):
    try: keyring.delete_password('SoilSenseMonitor', slot)
    except keyring.errors.PasswordDeleteError: pass
p = pathlib.Path.home() / '.soilsense' / 'ai_settings.json'
p.unlink(missing_ok=True)
"
```

## License & intellectual property

This repository is made public for transparency and reproducibility of
research results. **All rights reserved.** No license to copy, modify,
redistribute, or commercially exploit the software, the underlying soil
model, or the hardware design is granted by publication of this code.

Portions of the hardware design and possibly the calibration model are
the subject of pending patent applications. For licensing inquiries,
academic collaboration, or commercial use, please contact the author.

— Mingqiang Han, Kansas State University
