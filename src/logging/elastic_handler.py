import logging


from elasticsearch import AsyncElasticsearch
from src.settings import settings

logger = logging.getLogger('hephaestus.logging')
es_logger = logging.getLogger('elasticsearch')

es_client = AsyncElasticsearch(
    hosts=settings.ES_HOST,
    basic_auth=(settings.ES_USER, settings.ES_PASSWORD),
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
        'stack_info',
        'exc_info',
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


    async def emit(self, record):
        """ Creates json from a log record and schedules its flush """
        self.format(record)

        log = {
            self._RENAME_FIELDS.get(key, key): value
            for key, value in record.__dict__.items()
            if key not in self._IGNORE_FIELDS
        }

        await es_client.index(index=settings.ES_INDEX, body=log)
