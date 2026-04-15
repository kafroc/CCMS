from arq.connections import RedisSettings
from app.core.config import settings
from app.worker.tasks import (
    file_process_task,
    st_parse_task,
    threat_scan_task,
    threat_import_task,
    objective_import_task,
    objective_gen_task,
    sfr_library_import_task,
    sfr_match_task,
    sfr_stpp_validate_task,
    test_gen_task,
    st_export_task,
    risk_summary_task,
    blind_spot_suggestions_task,
)


async def startup(ctx):
    """Initialize resources when the worker starts."""
    from app.core.database import init_db
    await init_db()


async def shutdown(ctx):
    """Clean up resources when the worker shuts down."""
    from app.core.database import close_db
    await close_db()


class WorkerSettings:
    functions = [
        file_process_task,
        st_parse_task,
        threat_scan_task,
        threat_import_task,
        objective_import_task,
        objective_gen_task,
        sfr_library_import_task,
        sfr_match_task,
        sfr_stpp_validate_task,
        test_gen_task,
        st_export_task,
        risk_summary_task,
        blind_spot_suggestions_task,
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 600       # Single task max 10 minutes
    keep_result = 3600      # Keep result for 1 hour
