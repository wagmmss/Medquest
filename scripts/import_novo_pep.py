#!/usr/bin/env python3
"""Importador CLI idempotente de backup v2 do Novo-PEP para a Central 6º Ano do MedQuest.

Uso:
    uv run python scripts/import_novo_pep.py --user-id user_xxx --file backup.json --dry-run
    uv run python scripts/import_novo_pep.py --user-id user_xxx --file backup.json --apply
    NOVO_PEP_SYNC_PASSWORD=... uv run python scripts/import_novo_pep.py --user-id user_xxx --worker-url https://... --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "app" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from api.db import db_transaction  # noqa: E402
from api.services.planner_store import _get_user_internato_blocks  # noqa: E402
from api.services.six_year_routine import (  # noqa: E402
    block_for_date,
    load_plan_row,
    local_today,
    ritual_cycle_key,
    week_iso_of,
)

# Mapa canônico de migração de IDs de currículo do Novo-PEP (central6ano_data.ts).
CURRICULUM_ID_MIGRATION_MAP: dict[str, str] = {
    "inst_docentes_cr": "inst_sus_rede",
}

VALID_PROOF_STATUSES = frozenset({"falta", "em_andamento", "pdf_pronto"})
VALID_MILESTONE_CATEGORIES = frozenset({"curriculo", "estudo", "graduacao", "prova", "ingresso"})
VALID_MARCHAS = frozenset({"4_sprint", "3_normal", "2_pesada", "1_sobrevivencia"})
VALID_ITEM_ID_RE = re.compile(r"^[a-z0-9_]{1,80}$")
VALID_MILESTONE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

SHIFT_SCHEDULE_TO_SHIFT: dict[str, str] = {
    "plantao_12h": "plantao_12h_dia",
    "plantao_12h_dia": "plantao_12h_dia",
    "plantao_noturno": "plantao_noturno",
    "plantao_24h": "plantao_24h",
}

SHIFT_SCHEDULE_TO_OVERRIDE: dict[str, str] = {
    "pos_plantao": "pos_plantao",
    "dia_cheio": "integral",
    "pe_vespera": "meio_periodo",
}

IGNORED_SHIFT_MODES = frozenset({"fds", "ferias_4h"})


@dataclass
class EntityDiff:
    novos: int = 0
    alterados: int = 0
    iguais: int = 0


@dataclass
class ImportReport:
    diffs: dict[str, EntityDiff] = field(default_factory=lambda: {
        "plan": EntityDiff(),
        "marcha": EntityDiff(),
        "shifts": EntityDiff(),
        "overrides": EntityDiff(),
        "curriculum": EntityDiff(),
        "milestones": EntityDiff(),
    })
    warnings: list[str] = field(default_factory=list)
    applied: bool = False


def _valid_iso_date(raw: Any) -> str | None:
    if not isinstance(raw, str) or len(raw) != 10:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.isoformat() == raw else None


def _extract_backup_payload(raw_data: Any) -> dict[str, Any]:
    if not isinstance(raw_data, dict):
        raise ValueError("Payload inválido: objeto JSON esperado na raiz.")
    if "payload" in raw_data and isinstance(raw_data["payload"], dict):
        if raw_data.get("exists") is False:
            raise ValueError("Worker retornou exists=false (nenhum backup salvo).")
        payload = raw_data["payload"]
    else:
        payload = raw_data

    version = payload.get("version")
    if version != 2:
        raise ValueError(f"Versão de backup não suportada: {version!r} (esperado: 2).")
    central = payload.get("central6AnoState")
    if not isinstance(central, dict):
        raise ValueError("Backup v2 não contém objeto 'central6AnoState'.")
    return payload


def fetch_worker_payload(worker_url: str, password: str) -> dict[str, Any]:
    """Lê o backup v2 do Cloudflare Worker do Novo-PEP (GET /sync com Bearer)."""
    url = f"{worker_url.rstrip('/')}/sync"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {password}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Erro HTTP {exc.code} ao consultar o Worker do Novo-PEP.") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de rede ao consultar o Worker do Novo-PEP: {exc.reason}") from None

    if status != 200:
        raise RuntimeError(f"Worker retornou status inesperado: HTTP {status}.")
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise RuntimeError("Resposta do Worker não é JSON válido.") from exc
    return _extract_backup_payload(parsed)


def load_file_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return _extract_backup_payload(raw)


def _has_weekly_night_shift(weekly_schedule: Any) -> bool:
    if isinstance(weekly_schedule, dict):
        for v in weekly_schedule.values():
            if isinstance(v, str) and "noturno" in v.lower():
                return True
            if isinstance(v, dict) and any(
                isinstance(inner, str) and "noturno" in inner.lower()
                for inner in v.values()
            ):
                return True
    elif isinstance(weekly_schedule, list):
        for item in weekly_schedule:
            if isinstance(item, str) and "noturno" in item.lower():
                return True
            if isinstance(item, dict) and any(
                isinstance(inner, str) and "noturno" in inner.lower()
                for inner in item.values()
            ):
                return True
    return False


def _iter_shift_schedule_entries(raw_schedule: Any) -> list[tuple[str, str, str]]:
    """Normaliza shiftSchedule (lista de dicts ou dict dateIso->mode) em (date_iso, mode, note)."""
    out: list[tuple[str, str, str]] = []
    if isinstance(raw_schedule, list):
        for item in raw_schedule:
            if not isinstance(item, dict):
                continue
            d_iso = _valid_iso_date(item.get("dateIso") or item.get("date_iso") or item.get("date"))
            raw_mode = str(
                item.get("mode") or item.get("shiftType") or item.get("type") or item.get("kind") or ""
            ).strip()
            note = str(item.get("note") or item.get("nota") or "").strip()[:200]
            if d_iso and raw_mode:
                out.append((d_iso, raw_mode, note))
    elif isinstance(raw_schedule, dict):
        for key, val in raw_schedule.items():
            d_iso = _valid_iso_date(key)
            if not d_iso:
                continue
            if isinstance(val, str):
                out.append((d_iso, val.strip(), ""))
            elif isinstance(val, dict):
                raw_mode = str(
                    val.get("mode") or val.get("shiftType") or val.get("type") or val.get("kind") or ""
                ).strip()
                note = str(val.get("note") or val.get("nota") or "").strip()[:200]
                if raw_mode:
                    out.append((d_iso, raw_mode, note))
    return out


def import_novo_pep_payload(
    db,
    user_id: str,
    raw_payload: dict[str, Any],
    *,
    since_iso: str = "2026-11-30",
    apply: bool = False,
    today_local: date | None = None,
) -> ImportReport:
    """Calcula diff e opcionalmente aplica de forma idempotente o backup v2 do Novo-PEP."""
    payload = _extract_backup_payload(raw_payload)
    since_valid = _valid_iso_date(since_iso)
    if not since_valid:
        raise ValueError(f"--since inválido: {since_iso!r} (esperado YYYY-MM-DD).")

    today = today_local if today_local is not None else local_today()
    central = payload["central6AnoState"]
    report = ImportReport(applied=apply)

    if _has_weekly_night_shift(central.get("weeklySchedule")):
        report.warnings.append(
            "weeklySchedule contém 'plantao_noturno' e foi ignorado; cadastre os plantões noturnos por data no Calendário de Plantões."
        )

    # 1) Currículo (com CURRICULUM_ID_MIGRATION_MAP)
    raw_curr = central.get("curriculumEntries")
    target_curr: dict[str, tuple[float, str, str]] = {}
    if isinstance(raw_curr, dict):
        # Processar legados primeiro para que chaves canônicas tenham precedência se ambas existirem
        ordered_items = sorted(
            raw_curr.items(),
            key=lambda kv: 0 if kv[0] in CURRICULUM_ID_MIGRATION_MAP else 1,
        )
        for raw_id, entry in ordered_items:
            if not isinstance(entry, dict):
                continue
            mapped_id = CURRICULUM_ID_MIGRATION_MAP.get(str(raw_id), str(raw_id))
            if not VALID_ITEM_ID_RE.fullmatch(mapped_id):
                report.warnings.append(f"Item de currículo ignorado (ID inválido): {raw_id!r}")
                continue
            try:
                val = float(entry.get("value", 0) or 0)
            except (TypeError, ValueError):
                val = 0.0
            val = max(0.0, min(1000.0, val))
            proof = str(entry.get("proofStatus") or entry.get("proof_status") or "falta").strip()
            if proof not in VALID_PROOF_STATUSES:
                proof = "falta"
            note = str(entry.get("notes") if "notes" in entry else entry.get("note", "") or "")[:2000]
            target_curr[mapped_id] = (val, proof, note)

    # 2) Marcos R1
    raw_milestones = central.get("r1Milestones")
    target_milestones: dict[str, tuple[str, str, str, int, str]] = {}
    if isinstance(raw_milestones, list):
        for idx, ms in enumerate(raw_milestones):
            if not isinstance(ms, dict):
                continue
            titulo = str(ms.get("titulo") or ms.get("title") or "").strip()[:200]
            d_iso = _valid_iso_date(ms.get("dateIso") or ms.get("data_iso"))
            if not titulo or not d_iso:
                report.warnings.append(f"Marco R1 ignorado no índice {idx} (título ou data inválida).")
                continue
            raw_mid = str(ms.get("id") or f"pep_ms_{idx + 1}").strip()
            mid = raw_mid if VALID_MILESTONE_ID_RE.fullmatch(raw_mid) else f"pep_ms_{idx + 1}"
            cat = str(ms.get("categoria") or "prova").strip()
            if cat not in VALID_MILESTONE_CATEGORIES:
                cat = "prova"
            note = str(ms.get("nota") if "nota" in ms else ms.get("note", "") or "")[:2000]
            done = 1 if bool(ms.get("done", False)) else 0
            target_milestones[mid] = (titulo, d_iso, cat, done, note)

    # 3) Marcha da semana atual
    target_marcha: tuple[str, str] | None = None
    raw_marcha = central.get("marchaId")
    if isinstance(raw_marcha, str) and raw_marcha in VALID_MARCHAS:
        target_marcha = (week_iso_of(today), raw_marcha)

    # 4) Plantões e overrides (>= since_iso)
    target_shifts: dict[tuple[str, str], str] = {}
    target_overrides: dict[str, str] = {}
    for d_iso, raw_mode, note in _iter_shift_schedule_entries(central.get("shiftSchedule")):
        if d_iso < since_valid:
            continue
        if raw_mode in IGNORED_SHIFT_MODES:
            continue
        if raw_mode in SHIFT_SCHEDULE_TO_SHIFT:
            target_shifts[(d_iso, SHIFT_SCHEDULE_TO_SHIFT[raw_mode])] = note
        elif raw_mode in SHIFT_SCHEDULE_TO_OVERRIDE:
            target_overrides[d_iso] = SHIFT_SCHEDULE_TO_OVERRIDE[raw_mode]
        else:
            report.warnings.append(f"shiftSchedule[{d_iso}] com modo desconhecido ignorado: {raw_mode!r}")

    # treinoClinico.internato.posPlantaoByDate (pode estar em central6AnoState ou na raiz do payload)
    treino = payload.get("treinoClinico") or central.get("treinoClinico")
    if isinstance(treino, dict):
        internato = treino.get("internato")
        if isinstance(internato, dict) and isinstance(internato.get("posPlantaoByDate"), dict):
            for raw_date, flag in internato["posPlantaoByDate"].items():
                if not flag:
                    continue
                d_iso = _valid_iso_date(raw_date)
                if d_iso and d_iso >= since_valid:
                    target_overrides[d_iso] = "pos_plantao"

    # 5) Plano (ENAMED, foco_override do rodízio atual se diferir do padrão, ritual_done do ciclo atual)
    existing_plan = load_plan_row(db, user_id)
    enamed_val = existing_plan["enamed_concept"] if existing_plan else 5
    raw_enamed = central.get("curriculumEnamedConcept")
    if raw_enamed in (3, 4, 5):
        enamed_val = int(raw_enamed)

    foco_override = dict(existing_plan["foco_override"]) if existing_plan else {}
    blocks = _get_user_internato_blocks(db, user_id)
    active_block = block_for_date(today, blocks)
    if active_block and active_block.get("id"):
        rid = str(active_block["id"])
        raw_anc = str(central.get("focoSemanalAncora70") or "").strip()
        raw_tri = str(central.get("focoSemanalTrilha30") or "").strip()
        default_anc = str(active_block.get("ancora70") or "").strip()
        default_tri = str(active_block.get("trilha30") or "").strip()
        ov_entry = dict(foco_override.get(rid) or {})
        if raw_anc and raw_anc != default_anc:
            ov_entry["ancora70"] = raw_anc
        if raw_tri and raw_tri != default_tri:
            ov_entry["trilha30"] = raw_tri
        if ov_entry:
            foco_override[rid] = ov_entry

    ritual_done = dict(existing_plan["ritual_done"]) if existing_plan else {}
    current_cycle = ritual_cycle_key(today)
    raw_cycle = central.get("ritualDomingoCycleIso")
    raw_done_ids = central.get("ritualDomingoDoneIds")
    if raw_cycle == current_cycle and isinstance(raw_done_ids, list) and raw_done_ids:
        cycle_map = dict(ritual_done.get(current_cycle) or {})
        for item_id in raw_done_ids:
            if isinstance(item_id, str) and item_id.strip():
                cycle_map[item_id.strip()] = True
        if cycle_map:
            ritual_done[current_cycle] = cycle_map

    plan_needs_write = (
        raw_enamed in (3, 4, 5)
        or foco_override != (existing_plan["foco_override"] if existing_plan else {})
        or ritual_done != (existing_plan["ritual_done"] if existing_plan else {})
    )
    if existing_plan is None:
        if plan_needs_write:
            report.diffs["plan"].novos = 1
    else:
        same_plan = (
            existing_plan["enamed_concept"] == enamed_val
            and existing_plan["foco_override"] == foco_override
            and existing_plan["ritual_done"] == ritual_done
        )
        if same_plan:
            report.diffs["plan"].iguais = 1
        else:
            report.diffs["plan"].alterados = 1

    # Diff Marcha
    if target_marcha is not None:
        w_iso, m_id = target_marcha
        row = db.execute(
            "SELECT marcha_id FROM user_week_marcha WHERE user_id = ? AND week_iso = ?",
            (user_id, w_iso),
        ).fetchone()
        if not row:
            report.diffs["marcha"].novos = 1
        elif str(row["marcha_id"]) == m_id:
            report.diffs["marcha"].iguais = 1
        else:
            report.diffs["marcha"].alterados = 1

    # Diff Shifts
    existing_shifts = {
        (str(r["date_iso"]), str(r["kind"])): str(r["note"] or "")
        for r in db.execute(
            "SELECT date_iso, kind, note FROM user_shifts WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    }
    for key, note in target_shifts.items():
        if key not in existing_shifts:
            report.diffs["shifts"].novos += 1
        elif existing_shifts[key] == note:
            report.diffs["shifts"].iguais += 1
        else:
            report.diffs["shifts"].alterados += 1

    # Diff Overrides
    existing_overrides = {
        str(r["date_iso"]): str(r["mode"])
        for r in db.execute(
            "SELECT date_iso, mode FROM user_day_overrides WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    }
    for d_iso, mode in target_overrides.items():
        if d_iso not in existing_overrides:
            report.diffs["overrides"].novos += 1
        elif existing_overrides[d_iso] == mode:
            report.diffs["overrides"].iguais += 1
        else:
            report.diffs["overrides"].alterados += 1

    # Diff Curriculum
    existing_curr = {
        str(r["item_id"]): (float(r["value"]), str(r["proof_status"]), str(r["note"] or ""))
        for r in db.execute(
            "SELECT item_id, value, proof_status, note FROM user_curriculum_entries WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    }
    for item_id, vals in target_curr.items():
        if item_id not in existing_curr:
            report.diffs["curriculum"].novos += 1
        elif existing_curr[item_id] == vals:
            report.diffs["curriculum"].iguais += 1
        else:
            report.diffs["curriculum"].alterados += 1

    # Diff Milestones
    existing_ms = {
        str(r["id"]): (
            str(r["titulo"]),
            str(r["data_iso"]),
            str(r["categoria"]),
            int(r["done"]),
            str(r["note"] or ""),
        )
        for r in db.execute(
            "SELECT id, titulo, data_iso, categoria, done, note FROM user_r1_milestones WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    }
    for mid, vals in target_milestones.items():
        if mid not in existing_ms:
            report.diffs["milestones"].novos += 1
        elif existing_ms[mid] == vals:
            report.diffs["milestones"].iguais += 1
        else:
            report.diffs["milestones"].alterados += 1

    if not apply:
        return report

    now_iso = datetime.now(UTC).isoformat()
    with db_transaction(db, immediate=True):
        if plan_needs_write or existing_plan is not None:
            routine_flag = 1 if (existing_plan and existing_plan["routine_mode_enabled"]) else 0
            db.execute(
                """
                INSERT INTO user_six_year_plan (
                    user_id, routine_mode_enabled, enamed_concept,
                    foco_override_json, ritual_done_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    enamed_concept = excluded.enamed_concept,
                    foco_override_json = excluded.foco_override_json,
                    ritual_done_json = excluded.ritual_done_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    routine_flag,
                    enamed_val,
                    json.dumps(foco_override, ensure_ascii=False),
                    json.dumps(ritual_done, ensure_ascii=False),
                    now_iso,
                ),
            )

        if target_marcha is not None:
            w_iso, m_id = target_marcha
            db.execute(
                """
                INSERT INTO user_week_marcha (user_id, week_iso, marcha_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, week_iso) DO UPDATE SET
                    marcha_id = excluded.marcha_id,
                    updated_at = excluded.updated_at
                """,
                (user_id, w_iso, m_id, now_iso),
            )

        for (d_iso, kind), note in target_shifts.items():
            db.execute(
                """
                INSERT INTO user_shifts (user_id, date_iso, kind, note, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date_iso, kind) DO UPDATE SET
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (user_id, d_iso, kind, note, now_iso),
            )

        for d_iso, mode in target_overrides.items():
            db.execute(
                """
                INSERT INTO user_day_overrides (user_id, date_iso, mode, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, date_iso) DO UPDATE SET
                    mode = excluded.mode,
                    updated_at = excluded.updated_at
                """,
                (user_id, d_iso, mode, now_iso),
            )

        for item_id, (val, proof, note) in target_curr.items():
            db.execute(
                """
                INSERT INTO user_curriculum_entries (user_id, item_id, value, proof_status, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, item_id) DO UPDATE SET
                    value = excluded.value,
                    proof_status = excluded.proof_status,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (user_id, item_id, val, proof, note, now_iso),
            )

        for mid, (titulo, d_iso, cat, done, note) in target_milestones.items():
            db.execute(
                """
                INSERT INTO user_r1_milestones (
                    user_id, id, titulo, data_iso, categoria, done, note, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, id) DO UPDATE SET
                    titulo = excluded.titulo,
                    data_iso = excluded.data_iso,
                    categoria = excluded.categoria,
                    done = excluded.done,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (user_id, mid, titulo, d_iso, cat, done, note, now_iso),
            )

    return report


def format_report(report: ImportReport) -> str:
    mode_label = "APLICADO" if report.applied else "DRY-RUN (sem escrita)"
    lines = [
        f"Importação Novo-PEP -> MedQuest [{mode_label}]",
        f"{'entidade':<14} | {'novos':>6} | {'alterados':>9} | {'iguais':>6}",
        "-" * 44,
    ]
    for name, diff in report.diffs.items():
        lines.append(f"{name:<14} | {diff.novos:>6} | {diff.alterados:>9} | {diff.iguais:>6}")
    if report.warnings:
        lines.append("")
        lines.append("Avisos:")
        for w in report.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importa backup v2 do Novo-PEP para a Central 6º Ano do MedQuest."
    )
    parser.add_argument("--user-id", required=True, help="Clerk user_id de destino no MedQuest.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Caminho para o JSON de backup v2 do Novo-PEP.")
    source.add_argument("--worker-url", help="URL base do Worker de Cloud Sync do Novo-PEP.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Apenas simula e exibe o diff (padrão).")
    mode.add_argument("--apply", action="store_true", help="Persiste os dados no banco via api/db.py.")
    parser.add_argument(
        "--since",
        default="2026-11-30",
        help="Importa plantões/overrides a partir desta data YYYY-MM-DD (padrão: 2026-11-30).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        if args.file:
            payload = load_file_payload(args.file)
        else:
            password = os.environ.get("NOVO_PEP_SYNC_PASSWORD", "").strip()
            if not password:
                print(
                    "Erro: defina a variável de ambiente NOVO_PEP_SYNC_PASSWORD para usar --worker-url.",
                    file=sys.stderr,
                )
                return 2
            payload = fetch_worker_payload(args.worker_url, password)
    except Exception as exc:
        print(f"Erro ao carregar backup: {exc}", file=sys.stderr)
        return 1

    from api import create_app
    from api.db import get_db

    app = create_app(testing=False, initialize_db=True)
    with app.app_context():
        db = get_db()
        try:
            report = import_novo_pep_payload(
                db,
                args.user_id,
                payload,
                since_iso=args.since,
                apply=bool(args.apply),
            )
        except Exception as exc:
            print(f"Erro durante a importação: {exc}", file=sys.stderr)
            return 1

    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
