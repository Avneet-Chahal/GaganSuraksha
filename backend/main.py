import logging
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.database import Base, engine, SessionLocal
from backend.seed_data import seed_database
from backend.routers import (
    satellites,
    trajectories,
    conjunctions,
    maneuver,
    metrics,
    sources,
    watchlist,
    alert_settings,
)

logger = logging.getLogger("gagan_suraksha.main")


def _run_initial_screening() -> None:
    """Runs conjunction screening for all watchlist satellites in a background thread at startup."""
    screening_logger = logging.getLogger("gagan_suraksha.screening")
    screening_logger.info("Lifespan background thread: starting initial conjunction screening...")
    db = SessionLocal()
    try:
        from backend.services.screening import screen_all_watchlist_pairs
        results = screen_all_watchlist_pairs(db)
        screening_logger.info("Lifespan initial screening completed: found %d conjunctions.", len(results))
    except Exception as exc:
        screening_logger.error("Lifespan initial screening failed: %s", exc, exc_info=True)
    finally:
        db.close()


def _refresh_celestrak_and_screen(force: bool = False) -> None:
    """Scheduled/startup job: refreshes CelesTrak TLEs and space weather, and re-screens if ingestion succeeds."""
    job_logger = logging.getLogger("gagan_suraksha.scheduler")
    job_logger.info("Starting CelesTrak & weather refresh and screening pipeline (force=%s)...", force)
    db = SessionLocal()
    try:
        from services.celestrak import refresh_celestrak_data
        from services.screening import screen_all_watchlist_pairs

        # Refresh space weather if available
        try:
            from backend.app.ml.train import SpaceWeatherManager
            sw_mgr = SpaceWeatherManager(cache_dir="backend/app/ml/data/space_weather")
            sw_mgr.download_space_weather()
            job_logger.info("Space weather refresh completed.")
        except Exception as sw_exc:
            job_logger.debug("Space weather refresh skipped or failed: %s", sw_exc)

        success, msg = refresh_celestrak_data(db, force=force)
        job_logger.info("CelesTrak refresh finished: %s (success=%s)", msg, success)
        if success:
            job_logger.info("Triggering orbital conjunction screening after CelesTrak update...")
            results = screen_all_watchlist_pairs(db)
            job_logger.info("Post-refresh screening completed: found %d conjunctions.", len(results))
    except Exception as exc:
        job_logger.error("CelesTrak refresh/screening pipeline failed: %s", exc, exc_info=True)
    finally:
        db.close()


def _run_nightly_backtest() -> None:
    """Nightly scheduled job: appends new truth pairs from multi-epoch TLE updates and extends backtest."""
    job_logger = logging.getLogger("gagan_suraksha.scheduler")
    job_logger.info("Starting scheduled nightly backtest truth-pair update...")
    db = SessionLocal()
    try:
        from backend.services.backtest import append_truth_pairs_and_extend_backtest
        res = append_truth_pairs_and_extend_backtest(db)
        job_logger.info("Nightly backtest update complete: %s", res)
    except Exception as exc:
        job_logger.error("Nightly backtest update failed: %s", exc, exc_info=True)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle handler for database initialization and scheduler."""
    # Create all database tables
    Base.metadata.create_all(bind=engine)

    # Seed initial satellites, sources, and metrics
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    scheduler = None
    import os
    if not os.getenv("PYTEST_CURRENT_TEST"):
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime, timezone, timedelta
        from backend.models.db_models import IngestionStatusModel

        # Initialize APScheduler for 6-hour recurring refresh and nightly backtest
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _refresh_celestrak_and_screen,
            "interval",
            hours=6,
            id="celestrak_6h_refresh",
            replace_existing=True,
        )
        scheduler.add_job(
            _run_nightly_backtest,
            "cron",
            hour=2,
            minute=0,
            id="nightly_backtest_job",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("APScheduler started: 6-hour CelesTrak refresh & nightly backtest active.")

        # Check if data is older than 6 hours or never fetched
        db_check = SessionLocal()
        needs_startup_refresh = True
        try:
            status = db_check.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
            if status and status.last_success_utc:
                try:
                    last_success = datetime.fromisoformat(status.last_success_utc.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) - last_success < timedelta(hours=6):
                        needs_startup_refresh = False
                except Exception:
                    pass
        finally:
            db_check.close()

        if needs_startup_refresh:
            logger.info("CelesTrak data older than 6 hours or missing: running background refresh...")
            threading.Thread(
                target=_refresh_celestrak_and_screen,
                kwargs={"force": False},
                name="startup-celestrak-refresh-thread",
                daemon=True,
            ).start()
        else:
            threading.Thread(
                target=_run_initial_screening,
                name="initial-screening-thread",
                daemon=True,
            ).start()

    yield

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Gagan Suraksha: Satellite Debris & Conjunction-Risk Prediction API for ISRO ISTRAC & NETRA.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["Health"])
def health_check() -> dict:
    """Service health probe."""
    return {"status": "ONLINE", "system": "Gagan Suraksha Core API"}


@app.get("/api/health/ml", tags=["Health"])
def health_ml_check() -> dict:
    """ML Model health, version, and training status probe."""
    try:
        from backend.app.ml.predict import StatePredictor
        predictor = StatePredictor.get_instance()
        training_dates = predictor.metadata.get("training_date_bounds") or {
            "trained_at_utc": predictor.metadata.get("trained_at_utc")
        }
        return {
            "status": "ONLINE" if predictor.ml_available else "UNAVAILABLE",
            "model_version": predictor.model_version or "v1.0.0",
            "training_dates": training_dates,
            "ml_available": predictor.ml_available,
            "reference_truth": predictor.metadata.get(
                "reference_truth", "Later TLE epoch state (SGP4 propagation at epoch tB)"
            ),
            "data_source": predictor.metadata.get(
                "data_source", "public TLE backtest"
            ),
        }
    except Exception as exc:
        logger.warning("Error querying ML health: %s", exc)
        return {
            "status": "UNAVAILABLE",
            "model_version": None,
            "training_dates": None,
            "ml_available": False,
            "error": str(exc),
        }


# Mount routers strictly once under the /api prefix
api_router = APIRouter(prefix=settings.API_V1_PREFIX)
api_router.include_router(satellites.router)
api_router.include_router(trajectories.router)
api_router.include_router(conjunctions.router)
api_router.include_router(maneuver.router)
api_router.include_router(metrics.router)
api_router.include_router(sources.router)
api_router.include_router(watchlist.router)
api_router.include_router(alert_settings.router)

app.include_router(api_router)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)
