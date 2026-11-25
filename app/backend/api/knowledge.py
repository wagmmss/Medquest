"""Módulo de Data Store e Recuperação Médica (Grounding RAG).

Gerencia a base de conhecimento médico indexada (Fichas Resumo, Revisões Rápidas e Diretrizes)
utilizando SQLite FTS5 (BM25) de alta performance e latência ultrabaixa (< 5ms).
"""

import html
import json
import logging
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE_DB = os.environ.get(
    "MEDKNOWLEDGE_DB",
    str(BACKEND_DIR / "medknowledge.db")
)


def get_knowledge_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Retorna conexão SQLite configurada para o Data Store de conhecimento."""
    path = db_path or DEFAULT_KNOWLEDGE_DB
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_knowledge_schema(conn: sqlite3.Connection) -> None:
    """Inicializa as tabelas de chunks e o índice FTS5 para busca textual ultra-rápida."""
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                source_type TEXT NOT NULL,
                specialty TEXT NOT NULL DEFAULT '',
                topic TEXT NOT NULL DEFAULT '',
                subtopic TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                word_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kc_specialty_topic
            ON knowledge_chunks(specialty, topic)
        """)

        # Tabela virtual FTS5 para busca em linguagem natural e termos clínicos
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                title,
                content,
                specialty UNINDEXED,
                topic UNINDEXED,
                subtopic UNINDEXED,
                content='knowledge_chunks',
                content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            )
        """)

        # Triggers de sincronização automática entre a tabela física e o índice FTS5
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_kc_ai AFTER INSERT ON knowledge_chunks BEGIN
                INSERT INTO knowledge_fts(rowid, title, content, specialty, topic, subtopic)
                VALUES (new.id, new.title, new.content, new.specialty, new.topic, new.subtopic);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_kc_ad AFTER DELETE ON knowledge_chunks BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content, specialty, topic, subtopic)
                VALUES('delete', old.id, old.title, old.content, old.specialty, old.topic, old.subtopic);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_kc_au AFTER UPDATE ON knowledge_chunks BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content, specialty, topic, subtopic)
                VALUES('delete', old.id, old.title, old.content, old.specialty, old.topic, old.subtopic);
                INSERT INTO knowledge_fts(rowid, title, content, specialty, topic, subtopic)
                VALUES (new.id, new.title, new.content, new.specialty, new.topic, new.subtopic);
            END;
        """)


from .cache import SimpleTTLCache

_knowledge_cache = SimpleTTLCache(300, max_size=500)
_jurisprudence_cache = SimpleTTLCache(300, max_size=500)


_FTS5_RESERVED_OPERATORS = frozenset({"AND", "OR", "NOT", "NEAR"})


def _sanitize_fts_query(raw_query: str) -> str:
    """Sanitiza strings de busca para operadores válidos e seguros no SQLite FTS5."""
    without_commands = re.sub(r'(?:^|\s)/[a-zA-ZÀ-ÿ0-9_-]+', ' ', raw_query or "")
    cleaned = re.sub(r'[^\w\s]', ' ', without_commands, flags=re.UNICODE)
    tokens = [
        t.strip()
        for t in cleaned.split()
        if len(t.strip()) >= 3 and t.strip().upper() not in _FTS5_RESERVED_OPERATORS
    ]
    if not tokens:
        return ""
    # Envolve cada termo em aspas duplas para impedir erro de sintaxe no FTS5.
    # Prioriza os primeiros 8 termos para não sobrecarregar a árvore de busca.
    return " OR ".join(f'"{t}"' for t in tokens[:8])


def retrieve_medical_context(
    area: str = "",
    subtema: str = "",
    stem: str = "",
    user_question: str = "",
    top_k: int = 3,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Recupera os blocos de conhecimento médico mais relevantes com base na área, subtema e termos da dúvida.
    Retorna lista de dicionários contendo título, conteúdo e metadados das fontes.
    """
    db_file = db_path or DEFAULT_KNOWLEDGE_DB
    if not os.path.exists(db_file):
        logger.debug("[Grounding] Arquivo do knowledge store não existe ainda: %s", db_file)
        return []

    # Combina a dúvida do usuário com trechos do enunciado e subtema para extrair termos-chave
    search_seed = f"{user_question} {subtema} {stem[:200]}".strip()
    fts_query = _sanitize_fts_query(search_seed)

    if not fts_query:
        return []

    norm_area = area.strip()
    norm_subtema = subtema.strip()
    try:
        mtime_ns = os.stat(db_file).st_mtime_ns
    except OSError:
        mtime_ns = 0

    cache_key = (db_file, mtime_ns, norm_area, norm_subtema, fts_query, top_k)
    cached = _knowledge_cache.get(cache_key)
    if cached is not None:
        return list(cached)

    conn = None
    try:
        conn = get_knowledge_connection(db_file)
        results = []

        # Tentativa 1: Busca FTS5 filtrando por especialidade/área quando informada
        cursor = conn.cursor()
        if norm_area:
            cursor.execute(
                """
                SELECT kc.id, kc.source_file, kc.source_type, kc.specialty,
                       kc.topic, kc.subtopic, kc.title, kc.content, fts.rank
                FROM knowledge_fts fts
                JOIN knowledge_chunks kc ON fts.rowid = kc.id
                WHERE knowledge_fts MATCH ?
                  AND (kc.specialty LIKE ? OR kc.topic LIKE ? OR kc.subtopic LIKE ?)
                ORDER BY fts.rank
                LIMIT ?
                """,
                (fts_query, f"%{norm_area}%", f"%{norm_area}%", f"%{norm_subtema}%", top_k)
            )
            results = [dict(row) for row in cursor.fetchall()]

        # Tentativa 2: Fallback para busca global por ranking BM25 se filtragem for muito restritiva
        if not results:
            cursor.execute(
                """
                SELECT kc.id, kc.source_file, kc.source_type, kc.specialty,
                       kc.topic, kc.subtopic, kc.title, kc.content, fts.rank
                FROM knowledge_fts fts
                JOIN knowledge_chunks kc ON fts.rowid = kc.id
                WHERE knowledge_fts MATCH ?
                ORDER BY fts.rank
                LIMIT ?
                """,
                (fts_query, top_k)
            )
            results = [dict(row) for row in cursor.fetchall()]

        _knowledge_cache.set(cache_key, results)
        return results

    except Exception as exc:
        logger.warning("[Grounding] Erro na recuperação de contexto médico: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def retrieve_jurisprudence_context(
    db: Any,
    current_question_id: Optional[int] = None,
    area: str = "",
    subtema: str = "",
    stem: str = "",
    user_question: str = "",
    top_k: int = 2
) -> List[Dict[str, Any]]:
    """
    Recupera resoluções comentadas de questões semelhantes de provas anteriores (Jurisprudência das Bancas).
    Utiliza o índice FTS5 do banco de questões principal (questions_fts) com ranking BM25.
    """
    if db is None:
        return []

    # Extrai semente de busca combinando dúvida do aluno, subtema e palavras clínicas do enunciado
    search_seed = f"{user_question} {subtema} {stem[:200]}".strip()
    fts_query = _sanitize_fts_query(search_seed)

    if not fts_query:
        return []

    db_scope = os.environ.get("MEDQUEST_DB") or os.environ.get("TURSO_DATABASE_URL") or "default"
    cache_key = (db_scope, current_question_id or -1, fts_query, top_k)
    cached = _jurisprudence_cache.get(cache_key)
    if cached is not None:
        return list(cached)

    try:
        cur = db.execute(
            """
            SELECT q.id, q.institution_label, q.year, q.area, q.subtema,
                   q.stem, e.explanation_text, fts.rank
            FROM questions_fts fts
            JOIN questions q ON fts.rowid = q.id
            LEFT JOIN explanations e ON q.id = e.question_id
            WHERE questions_fts MATCH ?
              AND q.id != ?
              AND LENGTH(COALESCE(e.explanation_text, '')) > 60
            ORDER BY fts.rank
            LIMIT ?
            """,
            (fts_query, current_question_id or -1, top_k)
        )
        rows = cur.fetchall()
        results = []
        for r in rows:
            d = dict(r) if hasattr(r, "keys") else {
                "id": r[0], "institution_label": r[1], "year": r[2],
                "area": r[3], "subtema": r[4], "stem": r[5],
                "explanation_text": r[6], "rank": r[7]
            }
            stem_clean = (d.get("stem") or "").strip()
            expl_clean = (d.get("explanation_text") or "").strip()
            results.append({
                "id": d.get("id"),
                "institution": d.get("institution_label") or "Banca Oficial",
                "year": d.get("year") or "",
                "area": d.get("area") or "",
                "subtema": d.get("subtema") or "",
                "stem_excerpt": (stem_clean[:220] + "...") if len(stem_clean) > 220 else stem_clean,
                "explanation_excerpt": (expl_clean[:500] + "...") if len(expl_clean) > 500 else expl_clean
            })
        if results:
            _jurisprudence_cache.set(cache_key, results)
        return results
    except Exception as exc:
        logger.warning("[Grounding] Falha ao recuperar jurisprudência de bancas: %s", exc)
        return []



def format_jurisprudence_block(precedents: List[Dict[str, Any]]) -> str:
    """Formata precedentes de questões de residência para ancorar a jurisprudência das bancas no Preceptor."""
    if not precedents:
        return ""

    blocks = []
    for p in precedents:
        inst = p.get("institution") or "Banca Oficial"
        yr = f" ({p.get('year')})" if p.get("year") else ""
        area_info = f" | {p.get('area')}" if p.get("area") else ""
        sub_info = f" - {p.get('subtema')}" if p.get("subtema") else ""
        header = f"• [Questão #{p.get('id')} - {inst}{yr}{area_info}{sub_info}]"
        case_txt = f"  Caso Clínico: \"{p.get('stem_excerpt')}\""
        expl_txt = f"  Resolução Oficial da Banca / Pulo do Gato:\n  {p.get('explanation_excerpt')}"
        blocks.append(f"{header}\n{case_txt}\n{expl_txt}")

    joined = "\n\n".join(blocks)
    return f"""### JURISPRUDÊNCIA DE BANCAS MÉDICAS (PRECEDENTES E PEGADINHAS DE PROVAS REAIS):
As seguintes questões reais de concursos médicos anteriores abordaram casos e temas análogos:

{joined}

DIRETRIZ DE JURISPRUDÊNCIA:
Utilize estes precedentes oficiais para alertar o aluno sobre como examinadores de bancas médicas cobram o tema, destacando pegadinhas recorrentes e justificativas de bancas renomadas.
"""


def format_grounding_block(chunks: List[Dict[str, Any]]) -> str:
    """Formata os chunks recuperados em um bloco Markdown claro para ancorar o prompt da IA."""
    if not chunks:
        return ""

    blocks = []
    for c in chunks:
        src = c.get("source_file", "Diretriz Médica")
        topic = c.get("topic") or c.get("specialty") or "Clínica"
        sub = c.get("subtopic") or c.get("title") or ""
        header = f"[Fonte: {src} - {topic}"
        if sub and sub != topic:
            header += f" | {sub}"
        header += "]"

        content = c.get("content", "").strip()
        blocks.append(f"{header}\n{content}")

    joined = "\n\n---\n\n".join(blocks)
    return f"""### FICHAS DE APOIO LOCAL (DATA STORE — PODEM CONTER VERSÕES 2023–2025):
As informações abaixo foram extraídas das fichas de estudo locais. Use-as como apoio didático, MAS nunca acima de atualizações oficiais recentes (2024–2026) do Ministério da Saúde/SUS/PNI/CONITEC ou de busca web mais recente.

{joined}
"""


_RECENT_UPDATES_PATH = BACKEND_DIR / "data" / "diretrizes_atualizadas_2025_2026.json"
_recent_updates_cache: Optional[List[Dict[str, Any]]] = None
_web_search_cache = SimpleTTLCache(600, max_size=200)


def _load_recent_updates() -> List[Dict[str, Any]]:
    global _recent_updates_cache
    if _recent_updates_cache is not None:
        return _recent_updates_cache
    try:
        if _RECENT_UPDATES_PATH.exists():
            data = json.loads(_RECENT_UPDATES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _recent_updates_cache = data
                return _recent_updates_cache
    except Exception as exc:
        logger.warning("[Grounding] Falha ao carregar diretrizes_atualizadas_2025_2026.json: %s", exc)
    _recent_updates_cache = []
    return _recent_updates_cache


def retrieve_recent_guideline_updates(
    area: str = "",
    subtema: str = "",
    stem: str = "",
    user_question: str = "",
    top_k: int = 2,
) -> List[Dict[str, Any]]:
    """Recupera atualizações oficiais recentes (2024–2026) pertinentes à questão."""
    updates = _load_recent_updates()
    if not updates:
        return []

    haystack = " ".join(filter(None, [area, subtema, stem[:800], user_question])).lower()
    scored: List[tuple[int, Dict[str, Any]]] = []
    for item in updates:
        kws = item.get("keywords") or []
        hits = sum(1 for kw in kws if kw.lower() in haystack)
        if hits >= 2 or (hits == 1 and any(kw.lower() in (subtema or "").lower() for kw in kws)):
            scored.append((hits, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:top_k]]


def format_recent_updates_block(updates: List[Dict[str, Any]]) -> str:
    """Formata atualizações oficiais 2024–2026 com prioridade máxima sobre fichas antigas e gabarito histórico."""
    if not updates:
        return ""

    blocks = []
    for u in updates:
        blocks.append(
            f"• **{u.get('topic')} ({u.get('orgao')} — {u.get('ano')})**\n"
            f"  - Regra anterior (questões antigas): {u.get('regra_antiga')}\n"
            f"  - Regra VIGENTE ATUAL: {u.get('regra_atual')}\n"
            f"  - Impacto em provas: {u.get('impacto_provas')}"
        )

    joined = "\n\n".join(blocks)
    return f"""### 🚨 ATUALIZAÇÕES OFICIAIS DE DIRETRIZES (2024–2026) — PRIORIDADE MÁXIMA:
As mudanças oficiais abaixo PREVALECEM estritamente sobre o gabarito histórico da prova e sobre fichas locais antigas:

{joined}
"""


def search_web_guideline_snippets(query: str, max_results: int = 3, timeout: float = 4.0) -> List[Dict[str, str]]:
    """Busca leve e gratuita (DuckDuckGo HTML) para verificar mudanças recentes de diretrizes no Brasil."""
    clean_q = re.sub(r"\s+", " ", (query or "").strip())[:180]
    if not clean_q:
        return []

    cached = _web_search_cache.get(clean_q.lower())
    if cached is not None:
        return cached

    try:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": clean_q, "kl": "br-pt"})
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            page = resp.read().decode("utf-8", errors="ignore")

        results: List[Dict[str, str]] = []
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>[\s\S]*?(?:<a[^>]+class="result__snippet"[^>]*>([\s\S]*?)</a>|<div[^>]+class="result__snippet"[^>]*>([\s\S]*?)</div>)',
            page,
            re.IGNORECASE,
        )
        for href, raw_title, snip1, snip2 in blocks[:max_results]:
            title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            snippet = html.unescape(re.sub(r"<[^>]+>", "", snip1 or snip2 or "")).strip()
            uri = href
            if "uddg=" in href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if parsed.get("uddg"):
                    uri = parsed["uddg"][0]
            if title and snippet:
                results.append({"title": title[:160], "snippet": snippet[:320], "uri": uri[:300]})

        _web_search_cache.set(clean_q.lower(), results)
        return results
    except Exception as exc:
        logger.debug("[WebGrounding] Busca web auxiliar indisponível: %s", exc)
        return []


def format_web_snippets_block(snippets: List[Dict[str, str]]) -> str:
    if not snippets:
        return ""
    lines = [
        f"• **{s['title']}** ({s['uri']})\n  {s['snippet']}"
        for s in snippets
    ]
    return (
        "### 🌐 VERIFICAÇÃO WEB RECENTE (DIRETRIZES VIGENTES):\n"
        + "\n".join(lines)
        + "\n"
    )


