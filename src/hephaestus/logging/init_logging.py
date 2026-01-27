import logging
import sys
import threading
from logging import PlaceHolder, getLogger
from logging.config import dictConfig

from hephaestus.settings import settings
from hephaestus.helpers import nested_update

logger = getLogger('hephaestus.logging')


def init_logger():
    logging_config = settings.logging.model_dump()

    handlers = logging_config['handlers']
    loggers = logging_config.get('loggers', {})

    used_handlers = set(logging_config['root']['handlers'])
    for logger_ in loggers.values():
        # Each logger can potentially have its own handlers
        more_handlers = logger_.get('handlers')
        if more_handlers:
            used_handlers.update(more_handlers)

    nested_update(loggers, parse_levels(logging_config['logger_levels']))

    default = logging_config['default_logger_level']
    for name, logger_ in logger.manager.loggerDict.items():
        if '.' in name:
            if isinstance(logger_, PlaceHolder):
                continue

            if name not in loggers:
                loggers[name] = {'level': 'NOTSET'}
            else:
                loggers[name].setdefault('level', 'NOTSET')

        else:
            if name not in loggers:
                loggers[name] = {'level': default}
            else:
                loggers[name].setdefault('level', default)

    for handler in list(handlers):  # iterate over a shallow copy of dict keys
        if handler not in used_handlers:
            # Avoid configuring handlers that are not in use, to avoid
            # files creation / sockets opening during handlers init.
            del handlers[handler]

    dictConfig(logging_config)
    logger.info(f"Logger configuration set.")


def parse_levels(levels):
    levels = {level: loggers for level, loggers in levels.items() if loggers}
    return {name: {'level': level}
            for level, loggers in levels.items()
            for name in loggers}


def hook_uncaught_exceptions(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        logger.info(f"KeyboardInterrupt occurred: {exc_value}")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical(f"Uncaught Exception occurred: {exc_value}",
                    exc_info=(exc_type, exc_value, exc_traceback))


def hook_uncaught_exceptions_in_threads(args):
    logger.critical(f'Uncaught Exception in thread: {args.exc_value}',
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


sys.excepthook = hook_uncaught_exceptions
threading.excepthook = hook_uncaught_exceptions_in_threads