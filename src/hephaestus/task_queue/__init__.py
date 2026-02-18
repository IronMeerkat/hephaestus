from .init_celery import app as task_queue, shared_task


__all__ = ["task_queue", "shared_task"]