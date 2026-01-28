import os

from langfuse import get_client
from langfuse.langchain import CallbackHandler

from hephaestus.settings import settings

os.environ.update(settings.langfuse.model_dump())

langfuse = get_client()

langfuse_callback_handler = CallbackHandler()

