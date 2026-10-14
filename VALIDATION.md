# Validation and System Integrity Report

This document outlines the validation methodology, data sources, time-split integrity, reference truth, empirical headline metrics, and operational limitations for **Gagan Suraksha**.

---

## 1. Data Sources

- **Two-Line Element Sets (TLEs)**:
  - Source: CelesTrak public ephemeris archives and Space-Track GP history.
  - Orbit Regime: Low Earth Orbit (LEO), altitude 400 km to 900 km.
  - Scale: 28 LEO satellites (active payloads, rocket bodies, debris), generating 3,458 valid propagation pairs.
- **Space Weather Indices**:
  - Source: NOAA Space Weather Prediction Center (SWPC) / SpaceData archives (`SW-All.csv`).
  - Spanning 1957 to present: Daily solar radio flux ($F_{10.7}$), 81-day centered average solar flux ($F_{10.7,\text{81d}}$), planetary $K_p$ index, and geomagnetic $A_p$ index.
- **No Conjunction Data Messages (CDMs)**:
  - High-precision numerical CDMs from the 18th Space Defense Squadron / Space Surveillance Network are not publicly available for historical arbitrary conjunction sets. No CDM or classified radar tracking data is claimed or used.

---

## 2. Chronological Split Methodology (Zero Data Leakage)

- **Strict Time-Based Partitioning**:
  - Training, validation, and test sets are partitioned chronologically per satellite based on the target observation epoch ($t_B$).
  - Split ratios: **70% Train** (older months), **15% Validation** (middle period), **15% Test** (most recent period).
  - Train Period: 1986-02-22 to 2003-11-15 (2,421 pairs)
  - Validation Period: 1988-03-23 to 2003-11-19 (506 pairs)
  - Test Period: 1988-03-23 to 2004-03-04 (531 pairs)
- **Leakage Prevention**:
  - No random or stratified shuffling across time.
  - Observation pairs are deduplicated by `(norad_id, epoch_a_ts, epoch_b_ts)`.
  - Overlap between Train, Validation, and Test pair sets: **0 pairs** (confirmed by automated verification).
  - Satellites in the test set only evaluate on horizons strictly after their training epochs.

---

## 3. Reference Truth Definition

- In the absence of high-precision radar ephemeris or satellite laser ranging (SLR) observations, **reference truth is established using subsequent TLE epoch states** evaluated at epoch $t_B$ via SGP4 propagation.
- For each observation pair $(TLE_A, TLE_B)$ where $t_B > t_A$ across a prediction horizon of 12h to 168h:
  - Baseline state: Propagate $TLE_A$ from $t_A$ to $t_B$ using SGP4.
  - Reference truth state: Evaluate $TLE_B$ at its own epoch $t_B$ using SGP4.
  - Residuals are decomposed into the satellite's Radial, In-Track, and Cross-Track (RTN) coordinate frame.

---

## 4. Headline Metrics & Model Performance

The error-correction pipeline employs multi-target Quantile XGBoost regressors (10th, 50th, and 90th percentiles) trained on atmospheric drag, solar flux, geometry, and propagation horizon features.

### Propagation Error by Horizon (Day 1 to Day 7 on Held-Out Test Set, $N = 531$)

| Horizon | Sample Size ($N$) | SGP4 Baseline Median Error (km) | ML-Corrected Median Error (km) | Median Improvement | Baseline 90th Percentile (km) | ML 90th Percentile (km) | P90 Improvement |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Day 1** (12–36h) | 91 | 0.90 km | 2.52 km | -180.2% | 36.27 km | 27.16 km | **+25.1%** |
| **Day 2** (36–60h) | 86 | 2.12 km | 3.60 km | -69.9% | 67.51 km | 55.97 km | **+17.1%** |
| **Day 3** (60–84h) | 113 | 3.09 km | 3.04 km | **+1.6%** | 51.59 km | 55.08 km | -6.8% |
| **Day 4** (84–108h) | 96 | 4.42 km | 4.38 km | **+0.8%** | 264.31 km | 127.24 km | **+51.9%** |
| **Day 5** (108–132h) | 79 | 6.86 km | 8.94 km | -30.4% | 882.44 km | 158.31 km | **+82.1%** |
| **Day 6** (132–156h) | 51 | 124.81 km | 55.52 km | **+55.5%** | 1,961.67 km | 795.04 km | **+59.5%** |
| **Day 7** (156–180h) | 15 | 85.40 km | 38.70 km | **+54.7%** | 1,052.68 km | 359.88 km | **+65.8%** |

### Key Takeaways
1. **Short Horizons (Days 1–2)**: Fresh TLEs propagated with raw SGP4 have small median errors (< 1–2 km). Applying empirical ML corrections slightly increases median error, but compresses catastrophic 90th-percentile tails by 17–25%.
2. **Long Horizons (Days 6–7)**: Secular atmospheric drag error accumulation causes standard SGP4 drift to exceed 85–125 km. ML corrections with solar flux indices reduce Day 6 median error by **55.5%** and Day 7 median error by **54.7%**, cutting 90th-percentile errors by over 60%.

---

## 5. Assumptions and Known Limitations

1. **Analytical Propagation Baseline**: SGP4 is a general perturbations analytical model with Kozai mean motion conventions. It does not account for high-order gravity harmonics ($J_3+$, tesserals) or non-conservative radiation pressure beyond empirical $B^*$ drag terms.
2. **Reference Truth Precision**: Reference truth relies on later TLE epoch states rather than centimeter-level laser ranging (SLR) or radar ephemerides. TLEs have inherent fit noise (~1 km).
3. **Absence of Real Covariance in TLEs**: Standard TLEs do not contain uncertainty covariance matrices (unlike CDMs). Covariances in this system are constructed from quantile spread predictions ($\Delta q = q_{0.90} - q_{0.10}$) rather than sensor track fit covariance.
4. **Collision Probability ($P_c$)**: Foster 2D encounter plane probability assumes spherical combined hard-body radius, linear relative motion during encounter, and uncorrelated zero-mean Gaussian position errors.
5. **Operational Suitability**: This project is an engineering prototype and research system. Operational satellite collision avoidance maneuvers must be validated against official high-precision numerical orbit determination and official Space Surveillance Network tracks.
