"""
MedQuest - Serviço de Taxonomia Canônica dos 170 Temas
Single Source of Truth para metadados taxonômicos em tempo de execução.
"""
from __future__ import annotations

import json
import os
import threading
import unicodedata
from typing import Dict, List, Optional

PREVENTIVA_AREA_ALIASES = ("Preventiva", "Medicina Preventiva", "Medicina Preventiva e Social")
CIRURGIA_AREA_ALIASES = ("Cirurgia", "Cirurgia Geral")

_TAXONOMY_LOCK = threading.Lock()
_TAXONOMY_CACHE: Optional[Dict[str, List[str]]] = None
_SUBTEMA_TO_AREA: Optional[Dict[str, str]] = None
_TREE_CACHE: dict[str, object] = {"mtime": None, "path": None, "data": None}


def get_normalized_area(raw_area: Optional[str]) -> str:
    """Normaliza variações de nome de Grande Área para a chave canônica do sistema."""
    if not raw_area:
        return "Outros"
    if "Cirurgia" in raw_area:
        return "Cirurgia"
    if "nica" in raw_area:
        return "Clínica Médica"
    if "Ginecologia" in raw_area:
        return "Ginecologia e Obstetrícia"
    if "Preventiva" in raw_area:
        return "Preventiva"
    if "Pediatria" in raw_area:
        return "Pediatria"
    return "Outros"


def area_filter_values(area: Optional[str]) -> list[str]:
    """Expande uma área para os aliases conhecidos em consultas SQL exatas."""
    raw = (area or "").strip()
    if not raw:
        return []
    if raw in PREVENTIVA_AREA_ALIASES:
        return list(PREVENTIVA_AREA_ALIASES)
    if raw in CIRURGIA_AREA_ALIASES:
        return list(CIRURGIA_AREA_ALIASES)
    return [raw]


def expand_area_aliases(area: Optional[str]) -> list[str]:
    """Expande uma Grande Área incluindo seu nome normalizado e sinônimos conhecidos."""
    raw = (area or "").strip()
    if not raw:
        return []
    aliases = [raw]
    norm = get_normalized_area(raw)
    if norm == "Preventiva" or raw in PREVENTIVA_AREA_ALIASES:
        for alias in ("Medicina Preventiva", "Medicina Preventiva e Social", "Preventiva"):
            if alias not in aliases:
                aliases.append(alias)
    elif norm != "Outros" and norm not in aliases:
        aliases.append(norm)
    return aliases


def get_canonical_taxonomy_tree() -> Optional[dict]:
    """Lê canonical_taxonomy.json em memória com lock e invalidação automática por mtime."""
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    tax_path = os.path.join(backend_dir, "data", "canonical_taxonomy.json")
    try:
        mtime = os.path.getmtime(tax_path)
    except OSError:
        return None
    with _TAXONOMY_LOCK:
        if (
            _TREE_CACHE["data"] is not None
            and _TREE_CACHE["path"] == tax_path
            and _TREE_CACHE["mtime"] == mtime
        ):
            return _TREE_CACHE["data"]  # type: ignore[return-value]
        with open(tax_path, "r", encoding="utf-8") as f:
            tax = json.load(f)
        _TREE_CACHE["path"] = tax_path
        _TREE_CACHE["mtime"] = mtime
        _TREE_CACHE["data"] = tax
        return tax


def _load_raw_taxonomy() -> Dict[str, List[str]]:
    """Carrega o JSON oficial dos 170 temas."""
    global _TAXONOMY_CACHE, _SUBTEMA_TO_AREA
    with _TAXONOMY_LOCK:
        if _TAXONOMY_CACHE is not None:
            return _TAXONOMY_CACHE

        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates = [
            os.path.join(backend_dir, "data", "canonical_taxonomy_170.json"),
            os.path.join(backend_dir, "data", "canonical_taxonomy.json"),
            os.path.join(backend_dir, "data", "taxonomy.json"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and len(data) > 0:
                            _TAXONOMY_CACHE = data
                            _SUBTEMA_TO_AREA = {}
                            for area, subtemas in _TAXONOMY_CACHE.items():
                                for s in subtemas:
                                    _SUBTEMA_TO_AREA[s] = area
                            return _TAXONOMY_CACHE
                except Exception:
                    continue

        _TAXONOMY_CACHE = {}
        _SUBTEMA_TO_AREA = {}
        return _TAXONOMY_CACHE


def get_taxonomy() -> Dict[str, List[str]]:
    """Retorna o dicionário completo da taxonomia canônica {área: [subtemas]}."""
    return _load_raw_taxonomy()


def get_areas() -> List[str]:
    """Retorna a lista das 5 Grandes Áreas médicas."""
    return list(get_taxonomy().keys())


def get_subtemas(area: Optional[str] = None) -> List[str]:
    """Retorna os subtemas de uma grande área específica ou todos os 170 se area=None."""
    tax = get_taxonomy()
    if area:
        return list(tax.get(area, []))
    all_sub = []
    for subtemas in tax.values():
        all_sub.extend(subtemas)
    return all_sub


def is_valid_subtema(area: str, subtema: str) -> bool:
    """Verifica se o subtema pertence legitimamente à área informada."""
    tax = get_taxonomy()
    return subtema in tax.get(area, [])


def find_area_for_subtema(subtema: str) -> Optional[str]:
    """Descobre a grande área correspondente a um subtema canônico."""
    _load_raw_taxonomy()
    if _SUBTEMA_TO_AREA is not None:
        return _SUBTEMA_TO_AREA.get(subtema)
    return None


def search_subtemas(query: str, area: Optional[str] = None) -> List[str]:
    """Busca subtemas por substring normalizada."""
    def norm(t: str) -> str:
        r = unicodedata.normalize('NFD', t)
        return ''.join(c for c in r if unicodedata.category(c) != 'Mn').lower().strip()

    q_norm = norm(query)
    candidates = get_subtemas(area)
    if not q_norm:
        return candidates
    return [s for s in candidates if q_norm in norm(s)]
