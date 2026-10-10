# Gagan Suraksha: Satellite Debris and Collision-Risk Predictor

[![Mission Control](https://img.shields.io/badge/ISRO-ISTRAC%20%7C%20NETRA%20SSA-0284c7?style=flat-square)](https://www.isro.gov.in)
[![Status](https://img.shields.io/badge/System-Operational-10b981?style=flat-square)](#)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178c6?style=flat-square)](#)
[![Three.js](https://img.shields.io/badge/3D%20Engine-React%20Three%20Fiber-047857?style=flat-square)](#)

**Gagan Suraksha** is an aerospace monitoring and collision-risk prediction platform engineered specifically for **ISRO ISTRAC** and **NETRA** (Network for Space Objects Tracking and Analysis) project teams. It tracks orbital debris populations, predicts close approaches (conjunctions) using ML-calibrated orbit covariance, and recommends fuel-optimal Collision Avoidance Maneuvers (CAM).

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
- **Instanced Debris & Spacecraft Layers**: High-performance instanced points rendering hundreds of debris fragments at 60 FPS, with distinct accent-highlighted Indian primary satellites.
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
- **Classical vs. NETRA ML Comparison**: Direct side-by-side contrast between classical Foster 2D probability and ISRO NETRA ML-calibrated probability (correcting for atmospheric drag variations and solar flux).
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
  1. **False Alarm Alerts Reduction**: Monthly comparisons showing 42% elimination of false positive alarms across Q2–Q3 2026.
  2. **Probability Calibration (Reliability Curve)**: Forecast risk vs. observed empirical collision frequency aligning with the 1:1 diagonal.
  3. **Orbit Propagation Error Horizon**: Standard SGP4 drift vs. NETRA ML drag-corrected error maintained below 2.0 km through Day 7.

### `/watchlist` (Asset Watchlist & Settings)
- Add or remove Indian space assets by NORAD ID, name, and orbital regime.
- Customize safety screening margins (default $P_c$ threshold and miss distance buffer).
- Configure automated alert dispatch feeds (Email, Telegram Bot, ISTRAC Mission Control Webhook).
- View live health status and ingestion latency of surveillance feeds (Mount Abu Optical Array, Sriharikota MOTR, Space-Track CDMs, SGP4 Engine, ML Covariance Service).

---

## 4. Getting Started

### Prerequisites
- Node.js 18+ (tested on Node v24)
- npm 9+

### Installation
```bash
# Clone or navigate to the project directory
cd hack4

# Install dependencies
npm install
```

### Development Server
```bash
npm run dev
```
Open `http://localhost:5173` in your browser. The landing route `/` opens directly into the 3D Simulator.

### Production Build
```bash
npm run build
npm run preview
```

---

## 5. API Integration & Environment Variables

Create a `.env` file in the project root to configure the backend connection:

```env
# Optional: backend API URL (defaults to http://localhost:8000/api)
VITE_API_URL=http://localhost:8000/api
```

### Transparent Mock & Demo Data Layer
If the backend service is offline or unreachable, **Gagan Suraksha** automatically and gracefully falls back to its bundled, high-fidelity ISRO/NETRA astrodynamics dataset and client-side SGP4 calculation engine.
A distinct **"Demo data"** badge is displayed in the top bar and toolbar so users are never misled.

---

## 6. Monitored Assets Catalog

Primary Indian operational assets pre-configured in the platform:
- **CARTOSAT-2F** (NORAD 43111, SSO / LEO ~505 km)
- **RISAT-2BR1** (NORAD 44857, LEO ~576 km, inclination 37.0°)
- **EOS-04 / RISAT-1A** (NORAD 51656, SSO ~529 km)
- **GSAT-30** (NORAD 45026, GEO ~35,787 km)
- **OCEANSAT-3 / EOS-06** (NORAD 54361, SSO ~721 km)
- **INSAT-3DR** (NORAD 41752, GEO ~35,786 km)
- **ASTROSAT** (NORAD 40930, LEO ~650 km, inclination 6.0°)
- **GSAT-7A** (NORAD 43865, GEO communications)

Tracked high-risk debris fragments:
- **SL-8 R/B DEB** (NORAD 38244)
- **COSMOS 2251 DEB** (NORAD 34120)
- **FENGYUN 1C DEB** (NORAD 30255)
- **CZ-4B DEBRIS** (NORAD 41920)
- **BREEZE-M R/B DEB** (NORAD 39430)
- Background population of 350+ simulated tracked objects across LEO, MEO, and GEO.

---

*Gagan Suraksha — Developed for ISRO ISTRAC & NETRA SSA Operations.*
