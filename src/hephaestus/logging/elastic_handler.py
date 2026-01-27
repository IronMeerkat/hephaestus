import asyncio
import atexit
import logging
import sys
import threading
from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch
from hephaestus.settings import settings

logger = logging.getLogger('hephaestus.logging')
es_logger = logging.getLogger('elasticsearch')

# Dedicated event loop for ES logging (runs in background thread)
_es_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
_es_thread = threading.Thread(target=_es_loop.run_forever, daemon=True, name="es-logging-thread")
_es_thread.start()

def _shutdown_es_loop():
    _es_loop.call_soon_threadsafe(_es_loop.stop)

atexit.register(_shutdown_es_loop)

es_client = AsyncElasticsearch(
    hosts=settings.ES_HOST,
    basic_auth=(settings.ES_USERNAME, settings.ES_PASSWORD),
    ca_certs=settings.ES_CA,
    verify_certs=True,
    ssl_show_warn=False,
    headers={"accept": "application/json", "content-type": "application/json"},
)


class ElasticHandler(logging.Handler):

    _IGNORE_FIELDS = [
        'asctime',
        'created',
        'filename',
        'msg',
        # 'stack_info',
        # 'exc_info',
        'args',
        'msecs',
        'module',
        "level_emoji"
    ]
    _RENAME_FIELDS = {
        'name': 'logger_name',
        'levelname': 'log_level',
        'lineno': 'line',
        'funcName': 'func',
        'pathname': 'path',
        'exc_text': 'traceback',
    }


    def emit(self, record):
        """Creates json from a log record and schedules its flush 📤"""
        self.format(record)

        log = {
            self._RENAME_FIELDS.get(key, key): value
            for key, value in record.__dict__.items()
            if key not in self._IGNORE_FIELDS
        }
        log['@timestamp'] = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()


        # Schedule on dedicated ES logging thread (always available)
        asyncio.run_coroutine_threadsafe(self._async_index(log), _es_loop)

    async def _async_index(self, log: dict):
        """Actually send the log to Elasticsearch 🔍"""
        try:
            await es_client.index(index=settings.ES_INDEX, body=log)
        except Exception as e:
            # Avoid recursive logging - print to stderr instead
            print(f"❌ Failed to index log to Elasticsearch: {e}", file=sys.stderr)
