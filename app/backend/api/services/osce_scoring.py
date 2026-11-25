"""Extração de evidências do candidato e motor heurístico determinístico do barema OSCE."""
from __future__ import annotations

from typing import Any, Optional

from .osce_safety_rules import (
    _clause_has_negation,
    _extract_clause_prefix,
    _find_term_matches,
    _has_affirmative_mention,
    _has_negated_mention,
    _normalize_text,
)

def collect_candidate_evidence(
    transcript: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extrai exclusivamente falas, prescrições e ações executadas pelo candidato."""
    spoken_texts: list[str] = []
    prescribed_texts: list[str] = []
    action_texts: list[str] = []
    segments: list[dict[str, Any]] = []

    for item in transcript:
        if item.get("sender") != "candidato":
            continue
        msg = str(item.get("message") or "").strip()
        if not msg:
            continue
        spoken_texts.append(msg)
        raw_elapsed = item.get("elapsed_seconds")
        segments.append({
            "elapsed_seconds": int(raw_elapsed) if raw_elapsed is not None else None,
            "text": msg,
            "norm_text": _normalize_text(msg),
            "source": "speech",
        })

    allowed_action_types = {
        "vitals",
        "physical_exam",
        "lab_imaging",
        "exam",
        "procedure",
        "cardioversion",
    }

    for act in actions:
        act_type = str(act.get("action_type") or "").strip()
        raw_elapsed = act.get("elapsed_seconds")
        elapsed_val = int(raw_elapsed) if raw_elapsed is not None else None

        if act_type == "prescription":
            for p in act.get("prescription_items", []):
                p_text = (
                    f"{p.get('drug_name', '')} {p.get('dose', '')} "
                    f"{p.get('unit', '')} {p.get('route', '')} {p.get('notes', '')}"
                ).strip()
                if p_text:
                    prescribed_texts.append(p_text)
                    segments.append({
                        "elapsed_seconds": elapsed_val,
                        "text": p_text,
                        "norm_text": _normalize_text(p_text),
                        "source": "prescription",
                    })
        elif act_type in allowed_action_types:
            target_raw = str(act.get("action_target", "") or "").strip()
            target_norm = _normalize_text(target_raw)
            alias_suffix = ""
            if act_type in ("lab_imaging", "exam"):
                if "ecg" in target_norm or "eletro" in target_norm:
                    alias_suffix = "eletrocardiograma ecg 12 derivacoes"
                elif target_norm in ("rx", "raio_x", "rx_torax", "radiografia"):
                    alias_suffix = "radiografia raio-x rx de torax"
                elif "gaso" in target_norm or "eletrolito" in target_norm:
                    alias_suffix = "gasometria eletrolitos potassio"
            a_text = (
                f"{act_type} {target_raw} "
                f"{act.get('procedure_type', '')} {act.get('anatomical_site', '')} {alias_suffix}"
            ).strip()
            if a_text:
                action_texts.append(a_text)
                segments.append({
                    "elapsed_seconds": elapsed_val,
                    "text": a_text,
                    "norm_text": _normalize_text(a_text),
                    "source": "action",
                })

    all_parts = spoken_texts + prescribed_texts + action_texts
    all_text = " ".join(all_parts)

    return {
        "spoken_texts": spoken_texts,
        "prescribed_texts": prescribed_texts,
        "action_texts": action_texts,
        "segments": segments,
        "all_text": all_text,
        "norm_all_text": _normalize_text(all_text),
        "norm_spoken": _normalize_text(" ".join(spoken_texts)),
        "norm_prescribed": _normalize_text(" ".join(prescribed_texts)),
        "norm_actions": _normalize_text(" ".join(action_texts)),
    }


def _segment_matches_term(seg: dict[str, Any], norm_term: str, expect_negated: bool = False) -> bool:
    """Verifica se um segmento individual de evidência contém o termo com polaridade compatível."""
    seg_norm = seg.get("norm_text", "")
    matches = _find_term_matches(seg_norm, norm_term)
    if not matches:
        return False
    if seg.get("source") != "speech":
        return not expect_negated
    for m in matches:
        is_neg = _clause_has_negation(_extract_clause_prefix(seg_norm, m.start()))
        if expect_negated and is_neg:
            return True
        if not expect_negated and not is_neg:
            return True
    return False


def score_checklist_items(
    checklist_items: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    """Calcula a pontuação item a item do barema respeitando palavra inteira, negação e itens inversos."""
    norm_spoken = evidence.get("norm_spoken", "")
    norm_prescribed_and_actions = " ".join(
        part for part in (evidence.get("norm_prescribed", ""), evidence.get("norm_actions", "")) if part
    ).strip()
    segments = evidence.get("segments", [])
    scored_items: list[dict[str, Any]] = []

    for item in checklist_items:
        is_optional = bool(item.get("optional", False)) or float(item.get("weight", 1.0)) <= 0.0
        weight = 0.0 if is_optional else float(item.get("weight", 1.0))
        clinical_note = str(item.get("clinical_note", "")).strip()
        keywords = item.get("keywords", [])
        negated_keywords = item.get("negated_keywords", [])
        is_inverse = bool(item.get("inverse", False))
        forbidden_terms = item.get("forbidden_terms", [])

        violated_inverse = False
        if is_inverse and forbidden_terms:
            for ft in forbidden_terms:
                if _has_affirmative_mention(norm_spoken, norm_prescribed_and_actions, [ft]):
                    violated_inverse = True
                    break

        matches: list[str] = []
        matched_polarity: list[tuple[str, bool]] = []

        if not violated_inverse:
            for kw in keywords:
                if _has_affirmative_mention(norm_spoken, norm_prescribed_and_actions, [kw]):
                    matches.append(kw)
                    matched_polarity.append((_normalize_text(kw), False))
            for nkw in negated_keywords:
                if _has_negated_mention(norm_spoken, [nkw]):
                    matches.append(f"não {nkw}")
                    matched_polarity.append((_normalize_text(nkw), True))
            if is_inverse and forbidden_terms:
                for ft in forbidden_terms:
                    if _has_negated_mention(norm_spoken, [ft]):
                        label = f"não {ft}"
                        if label not in matches:
                            matches.append(label)
                            matched_polarity.append((_normalize_text(ft), True))

        denominator = max(1, len(keywords))
        match_ratio = len(matches) / denominator

        if violated_inverse:
            earned = 0.0
            status_internal = "nao_cumprido"
            status_code = "NONE"
            evidence_desc = "Critério violado: conduta contraindicada mencionada ou executada pelo candidato."
        elif match_ratio >= 0.4 or len(matches) >= 2:
            earned = weight
            status_internal = "cumprido_total"
            status_code = "FULL"
            evidence_desc = f"Identificado na conduta do candidato: termos [{', '.join(matches[:4])}]."
        elif match_ratio > 0.15 or len(matches) == 1:
            earned = round(weight * 0.5, 2)
            status_internal = "cumprido_parcial"
            status_code = "PARTIAL"
            evidence_desc = f"Cumprimento parcial identificado com o termo [{matches[0]}]."
        else:
            earned = 0.0
            status_internal = "nao_cumprido"
            status_code = "NONE"
            evidence_desc = (
                clinical_note
                or (
                    "Item opcional/neutro (sem penalidade na nota)."
                    if is_optional
                    else "Critério não contemplado nas falas ou ações do candidato durante o tempo de prova."
                )
            )
        if status_code != "NONE" and clinical_note:
            evidence_desc = f"{evidence_desc} {clinical_note}"

        timestamp_achieved_sec: Optional[int] = None
        if status_code != "NONE" and matched_polarity:
            for seg in segments:
                if any(_segment_matches_term(seg, nm, expect_neg) for nm, expect_neg in matched_polarity):
                    if seg.get("elapsed_seconds") is not None:
                        timestamp_achieved_sec = int(seg["elapsed_seconds"])
                    break

        scored_items.append({
            "id": item.get("id"),
            "criterion_id": str(item.get("id", "")),
            "code": str(item.get("code", item.get("id", "ITEM"))),
            "title": item.get("title"),
            "description": item.get("description", item.get("title", "")),
            "category": item.get("category", "Geral"),
            "weight": weight,
            "max_score": weight,
            "optional": is_optional,
            "clinical_note": clinical_note,
            "score_earned": earned,
            "awarded_score": earned,
            "completed": status_code != "NONE",
            "status_internal": status_internal,
            "status": status_code,
            "matched_keywords": matches[:3],
            "timestamp_achieved_sec": timestamp_achieved_sec,
            "evidence": evidence_desc,
            "evidence_citation": evidence_desc,
        })

    return scored_items


def evaluate_live_barema_progress(
    checklist_items: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    elapsed_seconds: int = 0,
    duration_seconds: int = 480,
) -> dict[str, Any]:
    """Avalia o progresso em tempo real do barema para o Modo Treino com Preceptor Fantasma."""
    evidence = collect_candidate_evidence(transcript, actions)
    scored = score_checklist_items(checklist_items, evidence)

    items_status = []
    total_earned = 0.0
    total_weight = 0.0

    for it in scored:
        if not it.get("optional"):
            total_weight += float(it["weight"])
        total_earned += float(it["score_earned"])
        items_status.append({
            "id": it["id"],
            "title": it["title"],
            "category": it["category"],
            "weight": it["weight"],
            "optional": bool(it.get("optional", False)),
            "score_earned": it["score_earned"],
            "completed": it["completed"],
            "status": it["status_internal"],
            "matched_keywords": it["matched_keywords"],
        })

    # Dicas e Alertas Proativos do Preceptor Fantasma proporcionais ao tempo total da estação
    safe_duration = max(60, int(duration_seconds or 480))
    t1 = int(safe_duration * 0.375)
    t2 = int(safe_duration * 0.50)
    t3 = int(safe_duration * 0.625)

    proactive_hints = []
    uncompleted_categories = set(i["category"] for i in items_status if not i["completed"] and not i.get("optional"))

    if elapsed_seconds >= t1 and "exame_fisico" in uncompleted_categories:
        proactive_hints.append(f"⚠️ Preceptor Fantasma: Já se passaram {round(t1 / 60)} minutos! Não se esqueça de checar os sinais vitais e o exame físico segmentar.")
    if elapsed_seconds >= t2 and "exames_complementares" in uncompleted_categories:
        proactive_hints.append("⚠️ Preceptor Fantasma: Metade da estação decorrida! Lembre-se de solicitar o exame complementar essencial (ECG, Labs ou Imagem).")
    if elapsed_seconds >= t3 and ("conduta_tratamento" in uncompleted_categories or "tratamento" in uncompleted_categories):
        rem_min = max(1, round((safe_duration - t3) / 60))
        proactive_hints.append(f"🚨 Preceptor Fantasma: Faltam cerca de {rem_min} minutos! Inicie a prescrição de urgência na prancheta ou verbalize as medidas terapêuticas imediatas.")

    normalized_score = round(min(10.0, (total_earned / max(1.0, total_weight)) * 10.0), 1)

    return {
        "mode": "guided",
        "current_score": normalized_score,
        "max_score": 10.0,
        "raw_earned": round(total_earned, 2),
        "raw_weight": round(total_weight, 2),
        "percentage": round((total_earned / max(1.0, total_weight)) * 100),
        "items_status": items_status,
        "proactive_hints": proactive_hints
    }


def get_session_mode(actions: list[dict[str, Any]]) -> str:
    """Extrai o modo da sessão (blind ou guided) a partir do histórico de ações."""
    for a in actions:
        if a.get("action_type") == "session_init" and a.get("mode"):
            return str(a.get("mode"))
    return "blind"

