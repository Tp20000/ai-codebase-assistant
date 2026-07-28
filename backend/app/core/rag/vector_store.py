import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_chroma_client = None


def get_chroma_client():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    _chroma_client = _make_client()
    return _chroma_client


def _make_client():
    import chromadb
    from app.config import settings

    host = getattr(settings, 'CHROMA_HOST', 'chromadb')
    port = int(getattr(settings, 'CHROMA_PORT', 8000))
    ver = chromadb.__version__
    logger.info(f'ChromaDB client version: {ver}')

    # Strategy 1: chromadb.HttpClient with v2 settings (chromadb 0.6+)
    try:
        client = chromadb.HttpClient(
            host=host,
            port=port,
            tenant='default_tenant',
            database='default_database',
        )
        client.list_collections()
        logger.info(f'ChromaDB HTTP v2 connected: {host}:{port}')
        return client
    except Exception as e1:
        logger.warning(f'HTTP v2 failed: {e1}')

    # Strategy 2: Use chromadb.HttpClient but create tenant first
    try:
        import httpx
        base = f'http://{host}:{port}'
        # Create tenant via v2 API directly
        r = httpx.post(f'{base}/api/v2/tenants', json={'name': 'default_tenant'}, timeout=5)
        logger.info(f'Tenant create: {r.status_code}')
        r2 = httpx.post(f'{base}/api/v2/tenants/default_tenant/databases', json={'name': 'default_database'}, timeout=5)
        logger.info(f'Database create: {r2.status_code}')
        client = chromadb.HttpClient(host=host, port=port)
        client.list_collections()
        logger.info(f'ChromaDB HTTP connected after tenant create')
        return client
    except Exception as e2:
        logger.warning(f'Tenant create failed: {e2}')

    # Strategy 3: PersistentClient (local file storage)
    try:
        persist = getattr(settings, 'CHROMA_PERSIST_DIR', '/app/chroma_db')
        client = chromadb.PersistentClient(path=persist)
        logger.info(f'ChromaDB PersistentClient: {persist}')
        return client
    except Exception as e3:
        logger.warning(f'PersistentClient failed: {e3}')

    # Strategy 4: EphemeralClient (in-memory, non-persistent)
    client = chromadb.EphemeralClient()
    logger.warning('ChromaDB EphemeralClient (in-memory)')
    return client


def _collection_name(project_id):
    clean = str(project_id).replace('-', '')[:40]
    return f'project_{clean}'


class VectorStore:
    def __init__(self):
        self.client = get_chroma_client()

    def get_or_create_collection(self, project_id):
        name = _collection_name(project_id)
        try:
            return self.client.get_or_create_collection(
                name=name,
                metadata={'project_id': project_id, 'hnsw:space': 'cosine'},
            )
        except Exception as exc:
            logger.error(f'Collection error {name}: {exc}')
            raise

    def add_chunks(self, project_id, chunks):
        collection = self.get_or_create_collection(project_id)
        valid = [c for c in chunks if c.get('embedding') and len(c['embedding']) > 0]
        if not valid:
            return 0

        ids, embeddings, documents, metadatas = [], [], [], []
        for chunk in valid:
            chunk_id = chunk.get('chunk_id', '')
            if not chunk_id:
                continue
            ids.append(chunk_id)
            embeddings.append(chunk['embedding'])
            documents.append(chunk.get('content', '')[:10000])
            metadatas.append({
                'file_id':    str(chunk.get('file_id', '')),
                'file_path':  str(chunk.get('file_path', '')),
                'language':   str(chunk.get('language', '')),
                'chunk_type': str(chunk.get('chunk_type', '')),
                'name':       str(chunk.get('name', '')),
                'line_start': int(chunk.get('line_start', 0)),
                'line_end':   int(chunk.get('line_end', 0)),
                'char_count': int(chunk.get('char_count', 0)),
            })

        if not ids:
            return 0

        try:
            collection.upsert(ids=ids, embeddings=embeddings,
                               documents=documents, metadatas=metadatas)
            logger.info(f'Stored {len(ids)} chunks')
            return len(ids)
        except Exception as exc:
            logger.error(f'Upsert failed: {exc}')
            return 0

    def search(self, project_id, query_embedding, n_results=5, where_filter=None):
        collection = self.get_or_create_collection(project_id)
        count = collection.count()
        if count == 0:
            return []
        try:
            params = {
                'query_embeddings': [query_embedding],
                'n_results': min(n_results, count),
                'include': ['documents', 'metadatas', 'distances'],
            }
            if where_filter:
                params['where'] = where_filter
            results = collection.query(**params)
            if not results or not results.get('ids') or not results['ids'][0]:
                return []
            formatted = []
            for i, chunk_id in enumerate(results['ids'][0]):
                dist = float(results['distances'][0][i]) if results.get('distances') else 0.0
                formatted.append({
                    'chunk_id': chunk_id,
                    'content':  results['documents'][0][i] if results.get('documents') else '',
                    'metadata': results['metadatas'][0][i] if results.get('metadatas') else {},
                    'score':    round(1.0 - dist, 4),
                    'distance': round(dist, 4),
                })
            return formatted
        except Exception as exc:
            logger.error(f'Search failed: {exc}')
            return []

    def delete_collection(self, project_id):
        name = _collection_name(project_id)
        try:
            self.client.delete_collection(name)
            return True
        except Exception:
            return False

    def get_collection_stats(self, project_id):
        name = _collection_name(project_id)
        try:
            col = self.client.get_or_create_collection(name=name)
            return {'name': name, 'count': col.count(), 'project_id': project_id}
        except Exception as exc:
            return {'name': name, 'count': 0, 'error': str(exc), 'project_id': project_id}

    def health_check(self):
        try:
            start = time.time()
            cols = self.client.list_collections()
            latency = round((time.time() - start) * 1000, 2)
            return {
                'status': 'healthy',
                'latency_ms': latency,
                'total_collections': len(cols),
            }
        except Exception as exc:
            return {'status': 'unhealthy', 'error': str(exc)}

    def query(self, **kwargs):
        """Compatibility alias for search(). Accepts any keyword arguments
        and maps them to search() parameters.
        
        The retriever may call with: collection_name, query_embeddings,
        query_embedding, n_results, where, where_filter, etc.
        """
        # Map retriever's kwargs to our search() signature
        project_id = kwargs.get("project_id") or kwargs.get("collection_name", "")
        query_embedding = kwargs.get("query_embedding") or kwargs.get("query_embeddings")
        if isinstance(query_embedding, list) and query_embedding and isinstance(query_embedding[0], list):
            query_embedding = query_embedding[0]  # unwrap [[embedding]] -> [embedding]
        n_results = kwargs.get("n_results", 5)
        where_filter = kwargs.get("where_filter") or kwargs.get("where")
        
        return self.search(
            project_id=project_id,
            query_embedding=query_embedding,
            n_results=n_results,
            where_filter=where_filter,
        )


# Module-level alias for backward compatibility
VectorStoreService = VectorStore
