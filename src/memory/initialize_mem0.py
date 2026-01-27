import asyncio
import os

from mem0 import AsyncMemory
from mem0.configs.base import MemoryConfig, RerankerConfig, VectorStoreConfig, EmbedderConfig, LlmConfig
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain import BaseChatModel
from pathlib import Path

persistent_path = Path(os.getcwd()) / "persistent_mem0"
persistent_path.mkdir(parents=True, exist_ok=True)

embeddings = OllamaEmbeddings(model="mxbai-embed-large")

# ✅ Chroma supports in-memory mode and dict-based filters (officially supported by mem0)
vector_store = Chroma(
    collection_name="mem0_memories",
    embedding_function=embeddings,
    persist_directory=persistent_path
)

async def _setup_memory(model: BaseChatModel):

    config = MemoryConfig(
        llm=LlmConfig(
            provider="langchain",
            config={
                "model": model,
            }
        ),
        vector_store=VectorStoreConfig(
            provider="langchain",
            config={
                "client": vector_store,
            }
        ),
        embedder=EmbedderConfig(
            provider="langchain",
            config={
                "model": embeddings,
            }
        ),
        reranker=RerankerConfig(
            provider="huggingface",
            config={
                "model": "BAAI/bge-reranker-large",
                "device": "cuda",
                "top_n": 15  # 🎯 Set to highest limit needed (for DM)
            }),
    )

    memory = AsyncMemory(config=config)

