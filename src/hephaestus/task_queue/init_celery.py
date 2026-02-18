
import asyncio
import nest_asyncio
import signal
import sys
import time

from celery import Celery, shared_task as _shared_task
from celery import signals
from celery.signals import setup_logging as celery_setup_logging

from hephaestus.settings import settings
from hephaestus.logging import get_logger

from .cleanup_old_workers import cleanup_old_workers

logger = get_logger(__name__)

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

app = Celery("task_queue")

app.conf.update(**settings.celery.model_dump())

app.autodiscover_tasks()


# Global flag to track shutdown state
_shutdown_requested = False

def handle_shutdown_signal(signum, frame):
    """Handle shutdown signals gracefully"""
    global _shutdown_requested
    if not _shutdown_requested:
        _shutdown_requested = True
        logger.info(f"Received signal {signum}. Initiating graceful shutdown...")

        # Give running tasks time to complete
        logger.debug("Waiting 2 seconds for running tasks to complete...")
        time.sleep(2)

        # Terminate the app
        if hasattr(app, 'control'):
            try:
                logger.debug("Shutting down Celery app...")
                app.control.shutdown()
            except Exception as e:
                logger.error(f"Error during app shutdown: {e}")

        # cleanup_old_workers()

        sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, handle_shutdown_signal)
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGQUIT, handle_shutdown_signal)


def shared_task(*args, **kwargs):

    """
    Decorator to make a celery's shared_task decorator async-friendly.
    With nest_asyncio applied, we can safely use asyncio.run() even in nested contexts.
    Includes proper signal handling for graceful task termination.
    """

    def decorator(task_func):

        def inner(*a, **k):
            # Check if shutdown was requested
            if _shutdown_requested:
                logger.warning("Task execution cancelled due to shutdown request")
                return None

            try:
                if asyncio.iscoroutinefunction(task_func):
                    return asyncio.run(task_func(*a, **k))
                return task_func(*a, **k)
            except KeyboardInterrupt:
                logger.warning(f"Task {task_func.__name__} interrupted by user")
                raise
            except Exception as e:
                logger.exception(f"Task {task_func.__name__} failed with error: {e}")
                raise

        return _shared_task(*args, **kwargs)(inner)

    return decorator


