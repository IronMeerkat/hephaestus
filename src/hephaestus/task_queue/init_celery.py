import asyncio
from functools import wraps
from logging import getLogger as get_logger

import nest_asyncio
from celery import Celery, shared_task as _shared_task

from hephaestus.settings import settings

logger = get_logger(__name__)

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

app = Celery("task_queue")

app.conf.update(**settings.celery.model_dump())

app.autodiscover_tasks()


def shared_task(*args, **kwargs):
    """Support sync/async tasks and both decorator forms; Celery owns worker shutdown."""
    if len(args) == 1 and callable(args[0]):
        return shared_task(**kwargs)(args[0])

    def decorator(task_func):
        @wraps(task_func)
        def inner(*a, **k):
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
