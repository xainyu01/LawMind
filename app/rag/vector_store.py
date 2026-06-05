import os
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.rag.embedding import BgeEmbedding

_embedding: Optional[BgeEmbedding] = None
_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None


def _get_embedding() -> BgeEmbedding:
    global _embedding
    if _embedding is None:
        _embedding = BgeEmbedding()
    return _embedding


def _get_collection() -> chromadb.Collection:
    global _client, _collection
    if _client is None:
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    if _collection is None:
        _collection = _client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
        )
    return _collection


def add_documents(docs) -> None:
    collection = _get_collection()
    embedder = _get_embedding()

    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]
    ids = [
        f"{doc.metadata.get('source', 'unk')}_{doc.metadata.get('chunk_index', i)}"
        for i, doc in enumerate(docs)
    ]

    embeddings = embedder.embed_documents(texts)
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def search(query: str, top_k: int = 5) -> List[dict]:
    collection = _get_collection()
    embedder = _get_embedding()

    query_embedding = embedder.embed_query(query)

    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    hits = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
    return hits


def get_all_documents() -> dict:
    """Return all documents from the collection (ids, documents, metadatas)."""
    collection = _get_collection()
    return collection.get()


def get_collection_count() -> int:
    """Return the number of documents in the collection."""
    collection = _get_collection()
    return collection.count()


def clear_collection() -> None:
    global _collection, _client
    if _client is not None:
        _client.delete_collection(settings.CHROMA_COLLECTION_NAME)
        _collection = None
