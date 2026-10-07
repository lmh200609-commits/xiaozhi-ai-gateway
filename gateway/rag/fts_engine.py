"""
SQLite FTS5 Full-Text Search Engine with Jieba Chinese Tokenization.
Provides native C-level BM25 scoring with microsecond execution latency (< 1ms).
"""
import re
import sqlite3
from typing import List, Dict, Tuple
import jieba

# Suppress jieba logging output
jieba.setLogLevel(20)

# Pre-register Chinese Da'an Railway Theme Park domain vocabulary
RAILWAY_DOMAIN_WORDS = [
    "中国大安机车博览园", "大安机车博览园", "大安机车园", "大安火车园区", "白城火车园区",
    "大安北", "机车封存基地", "三场两馆一线一平台", "火车头广场", "内燃机车广场", "蒸汽机车广场",
    "朱德号", "毛泽东号", "黄继光号", "前进型", "建设型", "上游型", "胜利型", "解造型",
    "东风4", "东风4D", "东风5", "东风7", "东风8", "东方红2", "东方红5", "德制V100",
    "韶山1型", "韶山3型", "韶山4型", "和谐号", "复兴号", "观光小火车", "全景观景台",
    "记忆馆", "体验馆", "JF1191", "JF304", "QJ", "DF4D"
]
for w in RAILWAY_DOMAIN_WORDS:
    jieba.add_word(w)

class Fts5SearchEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_fts()

    def get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_fts(self):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                title,
                content
            );
            """)
            conn.commit()

    @staticmethod
    def segment_text(text: str) -> str:
        """Segments Chinese & alphanumeric text into space-separated terms for FTS5 indexing."""
        clean = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
        words = jieba.cut_for_search(clean)
        return " ".join([w.strip() for w in words if w.strip()])

    def index_chunk(self, chunk_id: str, title: str, content: str, conn: sqlite3.Connection = None):
        """Indexes or updates a single chunk into FTS5 virtual table."""
        seg_content = self.segment_text(content)
        seg_title = self.segment_text(title)
        if conn is not None:
            c = conn.cursor()
            c.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
            c.execute(
                "INSERT INTO chunks_fts (chunk_id, title, content) VALUES (?, ?, ?)",
                (chunk_id, seg_title, seg_content)
            )
        else:
            with self.get_conn() as connection:
                c = connection.cursor()
                c.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
                c.execute(
                    "INSERT INTO chunks_fts (chunk_id, title, content) VALUES (?, ?, ?)",
                    (chunk_id, seg_title, seg_content)
                )
                connection.commit()

    def delete_chunk(self, chunk_id: str, conn: sqlite3.Connection = None):
        if conn is not None:
            c = conn.cursor()
            c.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
        else:
            with self.get_conn() as connection:
                c = connection.cursor()
                c.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
                connection.commit()

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        Executes native SQLite FTS5 BM25 search.
        Returns list of (chunk_id, bm25_score) sorted descending by relevance.
        Execution latency is typically under 1ms.
        """
        terms = [t.strip() for t in jieba.cut_for_search(query) if len(t.strip()) > 0]
        if not terms:
            return []

        # Build FTS5 OR match query with word quotes to prevent syntax errors
        # e.g., '"毛泽东号" OR "机车" OR "历史"'
        clean_terms = [re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "", t) for t in terms]
        match_expr = " OR ".join(f'"{t}"' for t in clean_terms if t.strip())
        if not match_expr.strip():
            return []

        with self.get_conn() as conn:
            c = conn.cursor()
            try:
                # bm25() in SQLite FTS5 returns negative values (more negative = better match)
                # We negate it so that higher score = better match
                rows = c.execute(
                    """
                    SELECT chunk_id, -bm25(chunks_fts, 2.0, 1.0) AS score
                    FROM chunks_fts
                    WHERE chunks_fts MATCH ?
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    (match_expr, top_k)
                ).fetchall()
                return [(r["chunk_id"], float(r["score"])) for r in rows]
            except Exception as e:
                print(f"[FTS5] Search error for '{query}': {e}")
                return []
