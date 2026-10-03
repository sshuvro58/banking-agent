# observability/logger.py
"""
Structured console logging + system metrics.
Traces and costs are already in PostgreSQL (observability_repo).
This handles the console/stdout side.
"""
import logging
import psutil
from config import app_config

logging.basicConfig(
    level=logging.DEBUG if app_config.is_dev else logging.INFO,
    format="%(asctime)s | %(name)-18s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_system_metrics() -> dict:
    """CPU, memory, disk snapshot for the /admin/metrics endpoint."""
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / 1e9, 2),
            "used_percent": psutil.virtual_memory().percent,
        },
        "disk": {
            "total_gb": round(psutil.disk_usage("/").total / 1e9, 2),
            "used_percent": psutil.disk_usage("/").percent,
        },
    }