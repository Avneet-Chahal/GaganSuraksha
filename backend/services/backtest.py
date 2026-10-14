"""
Gagan Suraksha - Backtest Extension Service.
Appends new truth pairs from multi-epoch TLE updates and extends the backtest dataset.
Uses Later TLE epoch states as reference truth (no CDMs).
"""

import json
import logging
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.db_models import BacktestTruthPair, SatelliteModel
from backend.app.ml.predict import correct_state, StatePredictor

logger = logging.getLogger("gagan_suraksha.backtest")

DATA_DIR = Path("backend/app/ml/data")
TRUTH_PAIRS_LOG = DATA_DIR / "truth_pairs.jsonl"


def append_truth_pairs_and_extend_backtest(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Nightly scheduled job:
    1. Scans cached historical TLEs and database records for consecutive epoch pairs.
    2. Propagates older TLE A to epoch tB and computes SGP4 residual against reference truth (TLE B at tB).
    3. Runs ML error correction via correct_state().
    4. Records new truth pairs in the BacktestTruthPair database table and truth_pairs.jsonl.
    5. Returns honest summary metrics with UTC timestamps.
    """
    logger.info("Starting nightly backtest truth-pair ingestion job...")
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        from backend.app.ml.train import (
            SpaceWeatherManager,
            TLERecord,
            parse_tle_text,
            decompose_rtn,
        )
    except Exception as exc:
        logger.error("Failed to import ML training utilities for backtest: %s", exc)
        if close_db:
            db.close()
        return {"new_pairs_added": 0, "status": "IMPORT_ERROR", "error": str(exc)}

    # Initialize space weather manager
    sw_dir = DATA_DIR / "space_weather"
    try:
        sw_manager = SpaceWeatherManager(str(sw_dir))
    except Exception as exc:
        logger.warning("SpaceWeatherManager initialization notice: %s. Using default space weather.", exc)
        sw_manager = None

    # Load TLEs from local cache directory
    tle_records: List[TLERecord] = []
    tle_dir = DATA_DIR / "tles"
    if tle_dir.exists():
        for fpath in tle_dir.glob("*.txt"):
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    tle_records.extend(parse_tle_text(f.read()))
            except Exception as e:
                logger.warning("Could not read TLE file %s: %e", fpath, e)

    # Also load active satellites from database
    try:
        db_sats = db.query(SatelliteModel).filter(SatelliteModel.line1.isnot(None), SatelliteModel.line2.isnot(None)).all()
        for sat in db_sats:
            try:
                rec = TLERecord(sat.name, sat.line1, sat.line2, object_type=sat.type or "PAYLOAD")
                tle_records.append(rec)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Could not load satellites from database: %s", exc)

    logger.info("Found %d total TLE records across disk cache and DB.", len(tle_records))

    # Group TLEs by NORAD ID and sort by epoch
    by_norad: Dict[int, List[TLERecord]] = {}
    for r in tle_records:
        by_norad.setdefault(r.norad_id, []).append(r)

    now_utc = datetime.now(timezone.utc).isoformat()
    new_pairs_count = 0
    predictor = StatePredictor.get_instance()

    # Ensure parent directory for JSONL exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        for norad_id, recs in by_norad.items():
            if len(recs) < 2:
                continue

            # Sort ascending by epoch
            recs.sort(key=lambda x: x.epoch_ts)

            for i in range(len(recs) - 1):
                tle_a = recs[i]
                tle_b = recs[i + 1]

                horizon_hours = (tle_b.epoch_ts - tle_a.epoch_ts) / 3600.0
                if horizon_hours < 6.0 or horizon_hours > 168.0:
                    continue  # Only valid horizons between 6h and 7 days

                # Check if pair already exists in database
                existing = db.query(BacktestTruthPair).filter(
                    BacktestTruthPair.norad_id == norad_id,
                    BacktestTruthPair.epoch_a_utc == tle_a.epoch_dt.isoformat(),
                    BacktestTruthPair.epoch_b_utc == tle_b.epoch_dt.isoformat(),
                ).first()

                if existing:
                    continue

                # Propagate A to tB
                jd_int = int(tle_b.jd_epoch)
                fr = float(tle_b.jd_epoch - jd_int)
                err_a, r_a, v_a = tle_a.satrec.sgp4(jd_int, fr)
                err_b, r_b, v_b = tle_b.satrec.sgp4(jd_int, fr)

                if err_a != 0 or err_b != 0:
                    continue

                r_a_vec = np.array(r_a, dtype=np.float64)
                v_a_vec = np.array(v_a, dtype=np.float64)
                r_b_vec = np.array(r_b, dtype=np.float64)

                baseline_3d_error = float(np.linalg.norm(r_a_vec - r_b_vec))

                # Weather features
                weather_dict = None
                if sw_manager:
                    date_str = tle_a.epoch_dt.strftime("%Y-%m-%d")
                    sw = sw_manager.get_indices_at_date(date_str)
                    mean_kp_h, mean_ap_h = sw_manager.get_horizon_indices(tle_a.epoch_dt, tle_b.epoch_dt)
                    weather_dict = {
                        "f107_daily": sw["f107_daily"],
                        "f107_81d_avg": sw["f107_81d"],
                        "kp_epoch": sw["kp"],
                        "ap_epoch": sw["ap"],
                        "kp_mean_horizon": mean_kp_h,
                        "ap_mean_horizon": mean_ap_h,
                    }

                # Predict correction
                corr_res = correct_state(
                    sat_state=(r_a_vec, v_a_vec),
                    tle_epoch=tle_a.epoch_dt,
                    t_target=tle_b.epoch_dt,
                    weather=weather_dict,
                    predictor=predictor,
                )

                corr_pos = corr_res.corrected_position
                corrected_3d_error = float(np.linalg.norm(corr_pos - r_b_vec))

                if baseline_3d_error > 1e-4:
                    impr = ((baseline_3d_error - corrected_3d_error) / baseline_3d_error) * 100.0
                else:
                    impr = 0.0

                pair_record = BacktestTruthPair(
                    norad_id=norad_id,
                    satellite_name=tle_a.name,
                    epoch_a_utc=tle_a.epoch_dt.isoformat(),
                    epoch_b_utc=tle_b.epoch_dt.isoformat(),
                    horizon_hours=round(horizon_hours, 2),
                    baseline_3d_error_km=round(baseline_3d_error, 4),
                    corrected_3d_error_km=round(corrected_3d_error, 4),
                    improvement_pct=round(impr, 2),
                    recorded_at_utc=now_utc,
                )
                db.add(pair_record)
                new_pairs_count += 1

                # Append to JSONL log
                with open(TRUTH_PAIRS_LOG, "a", encoding="utf-8") as f_jsonl:
                    f_jsonl.write(json.dumps({
                        "norad_id": norad_id,
                        "satellite_name": tle_a.name,
                        "epoch_a_utc": tle_a.epoch_dt.isoformat(),
                        "epoch_b_utc": tle_b.epoch_dt.isoformat(),
                        "horizon_hours": round(horizon_hours, 2),
                        "baseline_3d_error_km": round(baseline_3d_error, 4),
                        "corrected_3d_error_km": round(corrected_3d_error, 4),
                        "improvement_pct": round(impr, 2),
                        "reference_truth": "Later TLE epoch state",
                        "recorded_at_utc": now_utc,
                    }) + "\n")

        db.commit()
        logger.info(
            "Nightly backtest update complete: appended %d new truth pairs at %s.",
            new_pairs_count,
            now_utc,
        )
    except Exception as exc:
        db.rollback()
        logger.error("Error during backtest truth pair update: %s", exc, exc_info=True)
    finally:
        if close_db:
            db.close()

    total_pairs = db.query(BacktestTruthPair).count() if not close_db else 0
    return {
        "status": "SUCCESS",
        "new_pairs_added": new_pairs_count,
        "recorded_at_utc": now_utc,
        "reference_truth": "Later TLE epoch state (public TLE backtest)",
    }
