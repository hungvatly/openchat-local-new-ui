"""
OpenChat Local — RAG Engine
ChromaDB-backed retrieval-augmented generation pipeline.
Supports multiple named collections (one per knowledge folder) plus a shared default.
"""
import hashlib
import time
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings
from utils.document_loader import chunk_text, load_document, load_folder
from utils.graph_rag import graph_rag
import threading
import asyncio


def _make_collection_name(folder_path: str) -> str:
    """Create a safe ChromaDB collection name from a folder path."""
    h = hashlib.sha256(folder_path.encode()).hexdigest()[:16]
    return f"folder_{h}"


class RAGEngine:
    """Manages a single ChromaDB collection for document retrieval."""

    def __init__(self, collection_name: str = "documents"):
        self._collection_name = collection_name
        self._client = None
        self._collection = None
        self._embedding_fn = None
        self._initialized = False

    def _ensure_init(self):
        if self._initialized:
            return
        self._client = chromadb.Client(ChromaSettings(
            anonymized_telemetry=False,
            is_persistent=True,
            persist_directory=settings.CHROMA_PERSIST_DIR,
        ))
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._initialized = True

    @property
    def collection(self):
        self._ensure_init()
        return self._collection

    def _make_id(self, text: str, source: str) -> str:
        h = hashlib.md5(f"{source}:{text[:200]}".encode()).hexdigest()
        return h

    def ingest_file(self, filepath: str) -> Dict:
        """Ingest a single file into the vector store."""
        doc = load_document(filepath)
        if not doc.get("text"):
            return {"status": "error", "message": f"Could not read {filepath}"}

        chunks = chunk_text(doc["text"], settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        if not chunks:
            return {"status": "error", "message": "No text content found"}

        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(chunks):
            cid = self._make_id(chunk, doc["filename"])
            ids.append(cid)
            documents.append(chunk)
            metadatas.append({
                "source": doc["filename"],
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        # Trigger background GraphRAG extraction (only for global collection)
        if self._collection_name == "documents":
            def _extract_graph():
                from utils.local_llm import local_llm
                text_preview = doc["text"][:3000]
                prompt = f"Extract up to 5 major (Entity -> Relationship -> Entity) facts from the following text:\n\n{text_preview}\n\nReturn EXACTLY in this format, one per line: Entity1 | Relationship | Entity2"
                try:
                    # Create a fresh, thread-local event loop (don't overwrite the global one)
                    loop = asyncio.new_event_loop()
                    async def _run():
                        res = ""
                        async for token in local_llm.stream_chat(prompt, model=None, context=None, history=[], system_prompt="You are a GraphRAG knowledge extractor. Strictly follow the prompt format."):
                            res += token
                        return res
                    output = loop.run_until_complete(_run())
                    loop.close()
                    for line in output.split('\n'):
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) == 3:
                            graph_rag.add_relationship(parts[0], parts[2], parts[1], doc["filename"])
                except Exception as e:
                    print(f"[!] GraphRAG extraction failed: {e}")
            threading.Thread(target=_extract_graph, daemon=True).start()

        return {
            "status": "ok",
            "filename": doc["filename"],
            "chunks": len(chunks),
            "size": doc.get("size", 0),
        }

    def ingest_folder(self, folder_path: str) -> List[Dict]:
        """Ingest all documents in a folder."""
        docs = load_folder(folder_path)
        results = []
        for doc in docs:
            chunks = chunk_text(doc["text"], settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
            if not chunks:
                continue

            ids = []
            documents = []
            metadatas = []
            for i, chunk in enumerate(chunks):
                cid = self._make_id(chunk, doc["filename"])
                ids.append(cid)
                documents.append(chunk)
                metadatas.append({
                    "source": doc["filename"],
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                })

            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            results.append({
                "filename": doc["filename"],
                "chunks": len(chunks),
            })

        return results

    def ingest_text(self, text: str, source_name: str = "pasted_text") -> Dict:
        """Ingest raw text."""
        chunks = chunk_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        if not chunks:
            return {"status": "error", "message": "No content"}

        ids = [self._make_id(c, source_name) for c in chunks]
        metadatas = [{"source": source_name, "chunk_index": i, "total_chunks": len(chunks)} for i, c in enumerate(chunks)]

        self.collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
        return {"status": "ok", "source": source_name, "chunks": len(chunks)}

    def query(self, question: str, top_k: int = None) -> List[Dict]:
        """Retrieve relevant chunks for a question."""
        k = top_k or settings.TOP_K_RESULTS
        count = self.collection.count()
        if count == 0:
            return []

        k = min(k, count)
        results = self.collection.query(query_texts=[question], n_results=k)

        retrieved = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 0
                retrieved.append({
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "score": round(1 - dist, 4),
                    "chunk_index": meta.get("chunk_index"),
                    "collection": self._collection_name,
                })

        return retrieved

    def build_context(self, question: str) -> str:
        """Build a context string from retrieved documents."""
        results = self.query(question)
        if not results:
            return ""

        context_parts = []
        for r in results:
            context_parts.append(f"[Source: {r['source']}]\n{r['text']}")

        # Append Multi-Hop GraphRAG relationships (only for global collection)
        if self._collection_name == "documents":
            graph_context = graph_rag.build_related_context(question)
            if graph_context:
                context_parts.append(graph_context)

        return "\n\n---\n\n".join(context_parts)

    def get_stats(self) -> Dict:
        """Return stats about the current vector store."""
        count = self.collection.count()
        return {
            "total_chunks": count,
            "collection_name": self._collection_name,
            "persist_dir": settings.CHROMA_PERSIST_DIR,
        }

    def clear(self) -> Dict:
        """Clear all documents from the store."""
        self._ensure_init()
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return {"status": "ok", "message": "All documents cleared"}


class RAGRegistry:
    """
    Manages multiple RAGEngine instances — one global (for uploaded files) 
    and one per watched folder.
    """

    def __init__(self):
        self._global = RAGEngine("documents")
        self._engines: Dict[str, RAGEngine] = {}  # collection_name -> RAGEngine

    @property
    def global_engine(self) -> RAGEngine:
        return self._global

    def get_or_create(self, collection_name: str) -> RAGEngine:
        """Get an engine for a specific collection, creating it if needed."""
        if collection_name not in self._engines:
            self._engines[collection_name] = RAGEngine(collection_name)
        return self._engines[collection_name]

    def get_engine_for_folder(self, folder_path: str) -> RAGEngine:
        """Get the RAGEngine for a specific folder path."""
        col_name = _make_collection_name(folder_path)
        return self.get_or_create(col_name)

    def query_collections(self, question: str, collection_names: List[str], top_k: int = None) -> List[Dict]:
        """Query one or more specific collections, deduplicating results."""
        all_results = []
        seen_ids = set()

        for col_name in collection_names:
            if col_name == "documents":
                engine = self._global
            elif col_name in self._engines:
                engine = self._engines[col_name]
            else:
                engine = self.get_or_create(col_name)

            results = engine.query(question, top_k)
            for r in results:
                key = f"{r['source']}:{r['text'][:50]}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    all_results.append(r)

        # Sort by score descending
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        k = top_k or settings.TOP_K_RESULTS
        return all_results[:k]

    def build_context_for_collections(self, question: str, collection_names: List[str]) -> tuple:
        """Build context from selected collections. Returns (context_str, sources_list)."""
        results = self.query_collections(question, collection_names)
        if not results:
            return "", []

        context_parts = []
        for r in results:
            context_parts.append(f"[Source: {r['source']}]\n{r['text']}")

        # GraphRAG only for global collection
        if "documents" in collection_names:
            graph_context = graph_rag.build_related_context(question)
            if graph_context:
                context_parts.append(graph_context)

        return "\n\n---\n\n".join(context_parts), results


# Singletons
rag_engine = RAGEngine("documents")  # backwards-compatible global engine
rag_registry = RAGRegistry()
