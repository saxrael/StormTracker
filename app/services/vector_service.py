from sqlalchemy import text

from app.services.database import async_session


async def hybrid_search_chat_history(
    db_user_id: str, query: str, embedding: list[float], limit: int = 5
) -> list[dict]:
    vector_str = f"[{','.join(map(str, embedding))}]"
    sql = """
    WITH dense AS (
        SELECT id, chunk_text, embedding <=> CAST(:vector AS vector) AS distance,
               row_number() OVER (
                   ORDER BY embedding <=> CAST(:vector AS vector)
               ) as dense_rank
        FROM chat_history_chunks
        WHERE user_id = CAST(:user_id AS uuid)
          AND embedding <=> CAST(:vector AS vector) < 0.75
        LIMIT 20
    ),
    sparse AS (
        SELECT id, chunk_text,
               ts_rank(search_tsvector, plainto_tsquery('english', :query)) AS rank,
               row_number() OVER (
                   ORDER BY ts_rank(
                       search_tsvector, plainto_tsquery('english', :query)
                   ) DESC
               ) as sparse_rank
        FROM chat_history_chunks
        WHERE user_id = CAST(:user_id AS uuid)
          AND search_tsvector @@ plainto_tsquery('english', :query)
        LIMIT 20
    )
    SELECT
        COALESCE(dense.id, sparse.id) AS chunk_id,
        COALESCE(dense.chunk_text, sparse.chunk_text) AS chunk_text,
        COALESCE(1.0 / (60 + dense.dense_rank), 0.0) +
        COALESCE(1.0 / (60 + sparse.sparse_rank), 0.0) AS rrf_score
    FROM dense
    FULL OUTER JOIN sparse ON dense.id = sparse.id
    ORDER BY rrf_score DESC
    LIMIT :limit
    """

    async with async_session() as session:
        result = await session.execute(
            text(sql),
            {
                "user_id": db_user_id,
                "query": query,
                "vector": vector_str,
                "limit": limit,
            },
        )
        rows = result.fetchall()

    return [
        {"chunk_id": str(row.chunk_id), "text": row.chunk_text, "score": row.rrf_score}
        for row in rows
    ]
