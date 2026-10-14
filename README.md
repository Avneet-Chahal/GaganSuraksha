# Gagan Suraksha: Satellite Debris and Collision-Risk Predictor

[![Mission Control](https://img.shields.io/badge/SSA-Space%20Domain%20Awareness-0284c7?style=flat-square)](#)
[![Status](https://img.shields.io/badge/System-Operational-10b981?style=flat-square)](#)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178c6?style=flat-square)](#)
[![Three.js](https://img.shields.io/badge/3D%20Engine-React%20Three%20Fiber-047857?style=flat-square)](#)

**Gagan Suraksha** is an aerospace monitoring and collision-risk prediction platform engineered for satellite situational awareness (SSA). It tracks orbital debris populations, predicts close approaches (conjunctions) using ML-corrected orbit covariance, and recommends fuel-optimal Collision Avoidance Maneuvers (CAM).

---

## 1. Design Philosophy

- **Mission-Control Feel**: Built with a calm, confident, professional aerospace interface adhering to near-black deep space navy (`#070B12`), dark slate surfaces (`#0D131D`), hairline borders (`1px, low-contrast`), and restrained cyan accents (`#38BDF8`).
- **Data First & Progressive Disclosure**: Every metric includes units, timestamps in UTC, and sensor sources. Labels remain hidden until selected or hovered to avoid visual clutter.
- **Strict Color Semantics**: Amber and red are used **strictly** for risk status badges and critical alert vectors, paired with textual labels (`Nominal`, `Warning`, `Critical Risk`).
- **Aerospace Typography**: Inter for user interface labels; JetBrains Mono for coordinates, velocities, timestamps (UTC), and NORAD catalog identifiers.
- **Subtle Motion**: 150–200 ms restrained transitions; no neon blooms, heavy shadows, or decorative gradients.

---

## 2. System Architecture & Tech Stack

- **Core Framework**: React 19 + TypeScript + Vite 8
- **Styling**: Tailwind CSS v4 with custom aerospace design tokens
- **3D Visualization**: React Three Fiber + `@react-three/drei` + Three.js
- **Astrodynamics & SGP4**: `satellite.js` Keplerian / SGP4 propagation engine + Greenwich Mean Sidereal Time (GMST) Earth orientation
- **State Management**: Zustand (simulation clock, playback rate, camera targets, filter states)
- **Data Layer**: `@tanstack/react-query` + Axios with 30-second live polling and transparent mock fallback
- **Data Visualization**: Recharts (clean, high-contrast bar and line performance curves)

---

## 3. Key Features & Page Structure

### `/simulator` (3D Orbit Simulator — Centrepiece)
- **Dominant 3D Viewport**: Earth globe with procedural high-resolution ocean/continental mapping, equatorial guide, and custom atmosphere Fresnel rim shader.
- **Physical GMST Earth Rotation**: Earth rotates in accordance with true sidereal time ($GMST$), not arbitrary frame rates, aligning ECI coordinates with ground tracks.
- **Instanced Debris & Spacecraft Layers**: High-performance instanced points rendering hundreds of debris fragments at 60 FPS, with distinct accent-highlighted primary satellites.
- **Object Picking & Tooltips**: Throttled raycasting on hover reveals asset name and NORAD ID; click opens the collapsible telemetry panel.
- **Close Approach (Conjunction) Visualizer**: When a close approach is selected, both orbital planes are drawn in contrast colors, the exact TCA point is pinned, and a connecting miss-distance vector line is drawn with relative velocity geometry.
- **Left 48px Compact Toolbar**: Camera focus, reset view, toggle orbit lines (Watchlist / All / Off), toggle debris/satellite layers, cycle orbit regimes (LEO, MEO, GEO, ALL), and demo mode badge.
- **Right Collapsible Telemetry Panel**: Altitude, speed, inclination, orbital period, operator, TLE epoch, and close approach metrics with direct links to the maneuver planner.
- **Bottom Playback Bar**: Play/pause, reset to mission epoch, speed selector (1x, 10x, 60x, 600x), live UTC simulation clock, and scrubbable 7-day timeline with close approach event ticks.

### `/conjunctions` (Conjunction Assessment Table)
- Single mission table displaying object pairs, TCA (UTC), miss distance (km), relative velocity (km/s), calibrated collision probability ($P_c$), and risk badges.
- Search by satellite name or NORAD catalog number.
- Filter by risk level (`ALL`, `CRITICAL`, `WARNING`, `NOMINAL`) or watchlist filter.
- Sortable by TCA, miss distance, and collision probability.
- Auto-refreshes with a 30-second polling interval with quiet data freshness indicators.

### `/conjunctions/:id` (Event Detail & Maneuver Planner)
- **Left Column**: Summary of miss distance (radial, in-track, cross-track decomposition), relative velocity, and 1σ covariance position uncertainty.
- **Classical vs. ML-Corrected Comparison**: Direct side-by-side contrast between classical Foster 2D probability and ML-calibrated probability (correcting for atmospheric drag variations and solar flux).
- **Interactive Maneuver Planner**:
  - Impulsive Delta-V ($\Delta V$) slider (0.00 to 1.50 m/s).
  - Burn lead time selector (TCA - 24h, 12h, 6h, 2h).
  - Thrust vector direction (Prograde, Retrograde, Radial, Normal).
  - Live preview of new miss distance, new $P_c$, and propellant mass consumption computed via the Tsiolkovsky rocket equation.
  - Clear recommendation line (*"Maneuver recommended: 0.38 m/s, 0.42 kg fuel"* or *"Wait and monitor"*).
  - Collapsible spacecraft mass and $I_{sp}$ assumptions.
  - Dispatches burn telemetry via `POST /api/maneuver`.

### `/analytics` (Model Performance & Validation)
- Three large, clean validation charts with plain-language captions:
  1. **Alerts per month: baseline vs ML-corrected**: Monthly comparisons showing reduction in alerts alongside missed real events count.
  2. **Probability Calibration (Reliability Curve)**: Forecast risk vs. observed empirical collision frequency aligning with the 1:1 diagonal.
  3. **Orbit Propagation Error Horizon**: Standard SGP4 drift vs. ML drag-corrected error maintained below Day 7 horizons.

### `/watchlist` (Asset Watchlist & Settings)
- Add or remove monitored space assets by NORAD ID, name, and orbital regime.
- Customize safety screening margins (default $P_c$ threshold and miss distance buffer).
- Configure automated alert dispatch feeds (Email, Telegram Bot, Webhook).
- View live health status and ingestion latency of surveillance feeds (Space-Track Public TLEs, CelesTrak Archive, NOAA Space Weather, SGP4 Engine, ML Error Correction Service).

---

## 4. Getting Started & Run Steps

### Option A: Local Development

#### 1. Backend (FastAPI + Python 3.11+)
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run FastAPI server
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
The Core API will be available at `http://127.0.0.1:8000/api` with interactive OpenAPI Swagger docs at `http://127.0.0.1:8000/docs`.

#### 2. Frontend (React 19 + Vite 8)
```bash
# Install frontend dependencies
npm install

# Start Vite development server
npm run dev
```
Open `http://localhost:5174` (or `http://localhost:5173`) in your browser.

---

### Option B: Docker & Docker Compose

Launch the containerized backend with persistent SQLite volume storage:

```bash
# Build and run API container
docker compose up --build

# Run in background detached mode
docker compose up -d
```
The SQLite database file is mounted persistently to the named volume `gagan_suraksha_sqlite_data` under `/app/data/gagan_suraksha.db`.

---

## 5. Test Suite & Quality Verification

Run the full Python test suite (48 tests covering SGP4 propagation, Foster 2D collision probability, Tsiolkovsky rocket dynamics, SSRF webhook protection, alert deduplication, and REST endpoints):

```bash
# Run backend pytest suite
pytest -v

# Run frontend linting and typechecking
npm run lint
npm run build
```

---

## 6. Complete API Endpoint Reference

All endpoints return JSON responses with `camelCase` field names conforming to the frontend schema contracts. All endpoints are mounted strictly under the `/api` prefix.

| Method | Endpoint | Parameters / Body | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | None | Operational health probe (`ONLINE`). |
| `GET` | `/api/satellites` | `regime`, `is_indian`, `is_watchlist`, `type`, `limit` | Returns tracked satellites, orbital elements, and TLEs (`SatelliteRecord[]`). |
| `GET` | `/api/trajectories` | `ids` (max 20), `start`, `end` (max 7d), `step` (sec) | High-precision SGP4 ECI propagation points with velocities. |
| `GET` | `/api/conjunctions` | `risk_level`, `min_pc`, `max_miss_km`, `watchlist_only` | Screened close approach events sorted chronologically by TCA. |
| `GET` | `/api/conjunctions/{id}` | Path: `id` | Single conjunction event details, RTN vector decomposition, and covariance. |
| `POST` | `/api/maneuver` | Body: `ManeuverRequest` (`conjunctionId`, `deltaVMs`, `burnTimeUtc`, `direction`, `spacecraftMassKg`, `ispSeconds`) | CAM planner: Tsiolkovsky fuel cost, CW along-track separation gain, recomputed $P_c$, and clearance classification (`OPTIMAL`, `ACCEPTABLE`, `SUBOPTIMAL`). |
| `GET` | `/api/watchlist` | Query: `active_only` (optional) | Monitored space assets under active surveillance (`WatchlistItemRecord[]`). |
| `POST` | `/api/watchlist` | Body: `WatchlistItemCreate` (`noradId`, `name`, `regime`, `customPcThreshold`, `customMissDistanceKm`) | Adds/updates asset on watchlist and marks satellite `isWatchlist = true`. |
| `DELETE` | `/api/watchlist/{id}` | Path: `id` or Query: `id`, `norad_id` | Removes asset from collision watchlist and updates satellite record. |
| `GET` | `/api/alert-settings` | None | Collision alert thresholds and dispatch channel configuration. |
| `PUT` | `/api/alert-settings` | Body: `AlertSettingsUpdate` | Updates alert thresholds. Validates webhook URL with strict **SSRF safety**. |
| `GET` | `/api/metrics` | None | Model performance metrics: false alarm reduction, reliability curve, error horizon. Returns `"isDemo": true` for sample data. |
| `GET` | `/api/sources` | None | Real operational feed status: **CelesTrak TLE Ingestion** and **SGP4 Engine** (no invented sources). |

---

## 7. Security & SSRF Protection

Outgoing alert notifications implement strict security safeguards:
- **SSRF Prevention**: Webhook URLs must use HTTPS. Target hostnames are resolved via DNS and verified against private (RFC 1918 / RFC 4193), loopback (`127.0.0.1`, `::1`), link-local (`169.254.0.0/16`), and cloud metadata (`169.254.169.254`, `metadata.google.internal`) blacklists. Invalid targets return **HTTP 422**.
- **Credential Protection**: Webhook URLs containing embedded user credentials (`user:pass@`) are strictly rejected.
- **DNS-Rebinding Mitigation**: Webhook URLs and destination IPs are re-validated immediately before dispatch.
- **Masked Logging**: Authorization secrets, Telegram bot tokens, passwords, and full webhook URLs with query parameters are **never logged**.
- **Timeouts**: All external network requests enforce a strict **5-second timeout**.
- **Alert Deduplication**: Conjunction IDs are tracked in `sent_alerts` to prevent duplicate dispatches across repeated screening runs.

---

## 8. Machine Learning TLE Error-Correction Pipeline

Gagan Suraksha includes a physics-informed gradient boosted quantile regression pipeline to predict and correct SGP4 orbital propagation drift over 1-day to 7-day horizons.

### Architecture & Physics
- **Orbit Error Decomposition**: Satellite position residuals $\Delta \vec{r} = \vec{r}_{\text{prop}} - \vec{r}_{\text{ref}}$ are mapped directly into the satellite's orbital **RTN (Radial, In-track / Along-track, Cross-track / Normal)** reference frame:
  $$\hat{r} = \frac{\vec{r}}{\|\vec{r}\|}, \quad \hat{n} = \frac{\vec{r} \times \vec{v}}{\|\vec{r} \times \vec{v}\|}, \quad \hat{t} = \hat{n} \times \hat{r}$$
- **Atmospheric Drag & Space Weather Features**:
  - Orbit state: Horizon ($\Delta t$ hours), altitude ($h$ km), Kozai mean motion ($n$), inclination ($i$), eccentricity ($e$), and ballistic drag coefficient ($B^*$).
  - Space Weather: Daily $10.7\text{ cm}$ solar flux ($F_{10.7}$), 81-day centered solar flux average ($F_{10.7, 81\text{d}}$), geomagnetic planetary index at epoch ($K_p, A_p$), and mean geomagnetic indices over the propagation interval.
- **Quantile XGBoost Models**:
  - Independent gradient boosted tree ensembles for each spatial target (`residual_radial_km`, `residual_in_track_km`, `residual_cross_track_km`).
  - Quantiles evaluated at $\alpha = 0.10$, $\alpha = 0.50$ (median state correction), and $\alpha = 0.90$ (upper $1\sigma$ equivalent uncertainty bound) using native pinball loss (`reg:quantileerror`).
- **Leak-Free Temporal Split**:
  - Strictly chronological time-based split: for each satellite, earlier lifespan records form the **Train set (70%)**, middle periods form the **Validation set (15%)**, and most recent periods form the **Test set (15%)**.
  - **Zero temporal leakage**: No test sample contains future data leaking backward into training.
- **Evaluation & Artifacts**:
  - Model serialization: `backend/app/ml/models/tle_error_xgb_v1.0.0.joblib`
  - Real computed metadata: `backend/app/ml/models/metadata.json` (real Day 1 to Day 7 medians, 90th percentiles, and sample sizes).
  - Colab Notebook: `notebooks/tle_error_correction_training.ipynb` (interactive training, visualization, and error horizon curves).

### Running Model Training
```bash
# Execute ML pipeline locally with disk caching
python backend/app/ml/train.py

# Optional: provide Space-Track credentials to supplement CelesTrak archives
python backend/app/ml/train.py --spacetrack-user <USER> --spacetrack-password <PASS>
```

---

## 9. Data Sources and Limitations

> [!IMPORTANT]
> **Prototype Disclaimer**: Gagan Suraksha is an engineering prototype and research platform. It is **not affiliated with, endorsed by, or officially operated by the Indian Space Research Organisation (ISRO)**.

1. **Orbital Ephemeris & TLEs**:
   - Two-Line Element (TLE) sets are retrieved from the public **CelesTrak GP API** and historical archives (`https://celestrak.org`).
   - TLE data represent general perturbations mean elements intended for SGP4 analytical propagation. They are subject to atmospheric drag uncertainties and orbital decay modeling limits.
2. **Reference Truth for ML Evaluation**:
   - In the absence of classified Space Surveillance Network (SSN) radar observations or high-precision numerical Conjunction Data Messages (CDMs), **reference truth is established using subsequent TLE epoch states** evaluated with SGP4.
   - SGP4 itself possesses an intrinsic noise floor of $\sim 1\text{ km}$; ML corrections are most effective over multi-day horizons (Day 4 to 7) where unmodeled atmospheric drag causes hundreds to thousands of kilometers of along-track drift.
3. **Covariance Estimation**:
   - Standard public TLEs **do not include state covariance matrices** (unlike operational Space-Track / ISRO Conjunction Data Messages).
   - Position uncertainty ($\sigma_R, \sigma_T, \sigma_N$) is estimated via an empirical uncertainty growth model factoring in TLE epoch age and forecast lead time to TCA. Values are explicitly flagged as estimates in the `dataQualityNote` field.
4. **Collision Probability ($P_c$)**:
   - Collision probability is computed using the **Foster 2D encounter plane model** assuming spherical hard-body radius (default 10 m) and Gaussian positional uncertainty.
   - Values are approximations for screening prioritization and should not replace high-precision numerical ephemeris / Special Perturbations (SP) covariance analysis in real operational mission control.

---

*Gagan Suraksha — Prototype Satellite Debris & Conjunction-Risk Prediction System.*

