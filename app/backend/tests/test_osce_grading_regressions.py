"""Testes de regressão para auditoria e correção do motor de avaliação do OSCE (Bloco 0)."""
from __future__ import annotations

from pathlib import Path

from api import osce
from api.db import get_db
from api.osce_data import CANONICAL_STATIONS, FMRP_USP_TEMPLATES
from api.osce_evaluation import _normalize_text, evaluate_critical_safety_violations


def _start_station_by_code(db, code: str, user_id: str = "test_reg_user", mode: str = "blind") -> str:
    osce.seed_osce_stations(db)
    station = db.execute("SELECT id FROM osce_stations WHERE code = ?", (code,)).fetchone()
    assert station is not None, f"Estação {code} não encontrada"
    session = osce.start_osce_session(db, station["id"], user_id, mode=mode)
    return session["session_id"]


def test_spikes_all_refused_scores_at_most_one(app):
    """SPIKES com todas as condutas recusadas deve dar no máximo 1/10."""
    with app.app_context():
        db = get_db()
        user_id = "reg_spikes_user"
        session_id = _start_station_by_code(db, "UNIFESP-2023-PREV-SPIKES", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Não vou garantir privacidade nem chamar acompanhante, "
                "não quero saber a percepção dele nem se gostaria de saber detalhes, "
                "não faço aviso prévio de câncer em linguagem simples, "
                "não vou acolher em silêncio e não faço encaminhamento para oncologia."
            ),
        )
        assert res["final_score"] <= 1.0


def test_cad_negated_potassium_zeros_potassium_item(app):
    """CAD com negação explícita de potássio/KCl deve zerar o item de manejo do potássio."""
    with app.app_context():
        db = get_db()
        user_id = "reg_cad_neg_k"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Expansão com soro fisiológico 1000 ml na primeira hora. "
                "Não vou repor potássio nem usar KCl ou cloreto de potássio."
            ),
        )
        item_4 = next(it for it in res["evaluated_items"] if it.get("id") == "item_4")
        assert item_4["awarded_score"] == 0.0
        assert item_4["status"] == "NONE"


def test_cad_paraphrased_conduct_does_not_trigger_false_potassium_critical_error(app):
    """CAD com menção parafraseada de calemia/ionograma antes da insulina não pode disparar erro de K+."""
    with app.app_context():
        db = get_db()
        user_id = "reg_cad_para_k"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Verifiquei o ionograma e a calemia sérica (4,2 mEq/L) antes de iniciar insulina regular "
                "em bomba de infusão contínua e hidratação com soro fisiológico."
            ),
        )
        rf_texts = [str(rf.get("description", "")).lower() for rf in res.get("red_flags_triggered", [])]
        warn_texts = [str(w).lower() for w in res.get("preceptor_feedback", {}).get("critical_warnings", [])]
        for txt in rf_texts + warn_texts:
            assert not ("potássio" in txt or "potassio" in txt or "hipocalemia" in txt)


def test_queda_estado_geral_does_not_trigger_endoscopy_error(app):
    """'Queda do estado geral' não pode casar substring com 'eda' e disparar erro de endoscopia."""
    with app.app_context():
        db = get_db()
        user_id = "reg_queda_eda"
        session_id = _start_station_by_code(db, "UNICAMP-2023-CG-PERF", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Paciente com queda do estado geral e abdome em tábua por úlcera perfurada. "
                "Indico laparotomia exploradora de urgência, jejum, hidratação e antibiótico."
            ),
        )
        rf_texts = [str(rf.get("description", "")).lower() for rf in res.get("red_flags_triggered", [])]
        warn_texts = [str(w).lower() for w in res.get("preceptor_feedback", {}).get("critical_warnings", [])]
        for txt in rf_texts + warn_texts:
            assert "endoscopia" not in txt and "eda" not in txt


def test_polytrauma_negated_ct_not_penalized(app):
    """Politrauma dizendo 'não levar para tomografia' não pode ser punido por pedir tomografia."""
    with app.app_context():
        db = get_db()
        user_id = "reg_fast_no_ct"
        session_id = _start_station_by_code(db, "USP-RP-2023-CG-FAST", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes=(
                "Paciente instável com FAST positivo e hemoperitônio. "
                "Não levar para tomografia computadorizada, indico laparotomia exploradora imediata, "
                "ácido tranexâmico e transfusão maciça 1:1:1."
            ),
        )
        rf_texts = [str(rf.get("description", "")).lower() for rf in res.get("red_flags_triggered", [])]
        warn_texts = [str(w).lower() for w in res.get("preceptor_feedback", {}).get("critical_warnings", [])]
        for txt in rf_texts + warn_texts:
            assert "tomografia" not in txt


def test_sexual_violence_requiring_bo_triggers_critical_error_and_zeros_welcoming(app):
    """Exigir BO em violência sexual deve disparar erro crítico e zerar o acolhimento."""
    with app.app_context():
        db = get_db()
        user_id = "reg_pep_bo"
        session_id = _start_station_by_code(db, "REVALIDA-2023-GO-PEP", user_id=user_id)
        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes="Exijo o boletim de ocorrência policial como condição antes de realizar o atendimento médico.",
        )
        assert any("boletim de ocorrência" in str(rf.get("description", "")).lower() for rf in res["red_flags_triggered"])
        item_1 = next(it for it in res["evaluated_items"] if it.get("id") == "item_1")
        assert item_1["awarded_score"] == 0.0


def test_prescription_pad_only_scores_checklist_items(app):
    """Prescrição feita só na prancheta deve pontuar na nota final igual ao modo guiado."""
    with app.app_context():
        db = get_db()
        user_id = "reg_pad_only"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id, mode="guided")
        osce.prescribe_osce_drugs(
            db,
            session_id,
            user_id,
            [
                {
                    "drug_name": "Soro Fisiológico 0,9%",
                    "dose": "1000",
                    "unit": "ml",
                    "route": "EV",
                    "notes": "expansão na primeira hora",
                },
                {
                    "drug_name": "Cloreto de Potássio",
                    "dose": "20",
                    "unit": "mEq",
                    "route": "EV",
                    "notes": "repor potássio por litro de soro",
                },
                {
                    "drug_name": "Insulina Regular",
                    "dose": "0,1",
                    "unit": "U/kg/h",
                    "route": "EV",
                    "notes": "bomba de infusão contínua",
                },
            ],
            elapsed_seconds=120,
        )
        live = osce.get_osce_live_feedback(db, session_id, user_id, 120)
        fin = osce.finish_osce_session(db, session_id, user_id, conduct_notes="")
        assert fin["raw_score"] >= 5.0
        assert fin["raw_score"] == live["current_score"]


def test_empty_session_honest_radar_and_review(app):
    """Estação encerrada vazia deve gerar nota 0, radar sem números inventados e parecer sem elogios."""
    with app.app_context():
        db = get_db()
        user_id = "reg_empty_sess"
        session_id = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id=user_id)
        res = osce.finish_osce_session(db, session_id, user_id, conduct_notes="")
        assert res["final_score"] == 0.0
        assert res["competency_radar_5d"]["communication_empathy"] in (None, 0.0)
        assert res["competency_radar_5d"]["sus_time_efficiency"] == 0.0
        assert all(d["percentage"] in (None, 0.0) for d in res["competency_radar"]["dimensions"])
        assert res["chief_preceptor_review"]["what_went_well"] == []
        assert all(it["timestamp_achieved_sec"] is None for it in res["evaluated_items"])
        assert "Kussmaul" in res["chief_preceptor_review"]["gold_standard_canonical_conduct"]

        # Sessão exemplar 10/10 na mesma estação deve gerar parecer e forças distintos
        sess_gold = _start_station_by_code(db, "USP-RP-2024-CM-CAD", user_id="reg_gold_sess")
        osce.execute_osce_action(db, sess_gold, "reg_gold_sess", "vitals", "vitals", 15)
        osce.execute_osce_action(db, sess_gold, "reg_gold_sess", "lab_imaging", "gasometria_eletrólitos", 30)
        osce.execute_osce_action(db, sess_gold, "reg_gold_sess", "lab_imaging", "funcao_renal", 35)
        res_gold = osce.finish_osce_session(
            db,
            sess_gold,
            "reg_gold_sess",
            conduct_notes=(
                "Olá Lucas, sou o médico plantonista e vamos cuidar de você. Como suspendeu a insulina Glargina e Lispro há 2 dias no DM1, precisamos agir rápido. "
                "Solicito monitorização contínua, dois acessos venosos calibrosos e glicemia capilar imediata além de função renal e cetonúria. "
                "Paciente com respiração de Kussmaul, hálito cetônico e torpor. "
                "Diagnóstico de cetoacidose diabética grave com acidose metabólica e ânion gap elevado. "
                "Prescrevo soro fisiológico 0,9% 1000 ml na primeira hora para expansão. "
                "Avaliei potássio e prescrevo repor potássio com cloreto de potássio 20 mEq por litro. "
                "Inicio insulina regular em bomba de infusão contínua 0,1 U/kg/h. "
                "Quando atingir glicemia de 250 mg/dL, associar soro glicosado SG 5% para fechar ânion gap. "
                "Investigo fator desencadeante infeccioso com hemograma e culturas além da omissão da insulina. "
                "Mantenho glicemia horária e controle de eletrólitos a cada 2 horas, evitando não prescrever bicarbonato de rotina."
            ),
        )
        assert res_gold["final_score"] == 10.0
        assert len(res_gold["chief_preceptor_review"]["what_went_well"]) == 3
        assert res_gold["chief_preceptor_review"]["executive_summary"] != res["chief_preceptor_review"]["executive_summary"]
        assert res_gold["chief_preceptor_review"]["critical_corrections"] == []


def _build_trigger_phrase_for_error(err: str) -> str:
    """Constrói frase representativa de violação para testar cobertura determinística de cada erro crítico."""
    e = _normalize_text(err)
    if "bicarbonato" in e:
        return "Prescrevo bicarbonato de sódio venoso para corrigir o pH."
    if "potassio" in e and "insulina" in e:
        return "Inicio insulina regular em bomba imediatamente."
    if "suspender" in e and "insulina" in e:
        return "Vou suspender insulina assim que a glicemia baixar."
    if "trombolitico" in e or "fibrinolitico" in e:
        return "Prescrevo alteplase para trombólise química."
    if "estrategia invasiva" in e:
        return "Não indico cateterismo nem estratégia invasiva, sigo tratamento conservador exclusivo."
    if "tomografia" in e and ("instavel" in e or "fast" in e):
        return "Encaminho paciente para tomografia computadorizada agora."
    if "2 litros" in e or "coagulopatia dilucional" in e:
        return "Realizo ressuscitação agressiva com 3 litros de soro fisiológico."
    if ("corticosteroide" in e or "cortico" in e) and "bronquiolite" in e:
        return "Prescrevo prednisolona oral para esta bronquiolite."
    if ("antibiotico" in e or "antimicrobiano" in e) and ("bronquiolite" in e or "quadro viral" in e or "diarreia aquosa" in e):
        return "Prescrevo amoxicilina de rotina."
    if "alta" in e and ("hipoxemia" in e or "observacao" in e):
        return "Vou dar alta hospitalar para casa agora."
    if "hamilton" in e or "massagem bimanual" in e:
        return "Não realizo massagem bimanual nem manobra de Hamilton."
    if "atrasar" in e and "uterotonico" in e:
        return "Vou aguardar exames antes da ocitocina e não administro uterotônico agora."
    if "tudo psicologico" in e or "desmerecer" in e:
        return "Isso é tudo psicológico, a senhora não tem nada."
    if "bateria excessiva" in e or "prevencao quaternaria" in e:
        return "Solicito bateria de exames e tomografia de corpo inteiro."
    if "benzodiazepinico" in e or "polifarmacia" in e:
        return "Prescrevo clonazepam de uso contínuo."
    if "aguardar" in e and "troponina" in e:
        return "Vou aguardar troponina antes de definir reperfusão."
    if "nitrato" in e:
        return "Prescrevo isordil sublingual imediatamente."
    if "oxigenioterapia" in e:
        return "Prescrevo cateter de O2 de rotina para a paciente."
    if "nao indicar cirurgia" in e:
        return "Não indico cirurgia, vou manter tratamento conservador."
    if "endoscopia" in e or "eda" in e:
        return "Solicito endoscopia digestiva alta imediata."
    if ("corticoide" in e or "anti-histaminico" in e) and "adrenalina" in e:
        return "Prescrevo hidrocortisona e prometazina apenas."
    if "adrenalina" in e and ("subcutanea" in e or "intravenosa pura" in e):
        return "Administro adrenalina subcutânea agora."
    if "nao prescrever sulfato" in e:
        return "Não vou prescrever sulfato de magnésio neste caso."
    if "diazepam" in e or "fenitoina" in e:
        return "Prescrevo diazepam e fenitoína para profilaxia de convulsão."
    if "reduzir abruptamente" in e or "120 mmhg" in e:
        return "Vou reduzir abruptamente a PA para valores menores que 120 mmHg."
    if "abrupta" in e or "em pe" in e:
        return "Comunico em pé no corredor de forma abrupta sem aviso prévio."
    if "jargoes" in e or "adenocarcinoma" in e:
        return "Você tem adenocarcinoma invasivo moderadamente diferenciado."
    if "nao ha nada a fazer" in e:
        return "Infelizmente não há nada a fazer neste caso."
    if "amiodarona" in e:
        return "Administro amiodarona 300 mg venosa antes do choque."
    if "sincronizacao" in e:
        return "Vou chocar sem sincronizar com desfibrilação imediata."
    if "atrasar o antibiotico" in e:
        return "Vou esperar hemocultura sair antes de iniciar antibiótico."
    if "dopamina" in e:
        return "Inicio dopamina em bomba como vasopressor inicial."
    if ("radiografia" in e or "tomografia" in e) and "pneumotorax" in e:
        return "Solicito radiografia de tórax antes de descomprimir."
    if "intubacao" in e and "descomprimir" in e:
        return "Vou intubar antes de descomprimir o tórax."
    if "plano a ou b" in e or "reidratacao oral" in e:
        return "Vou manter apenas terapia de reidratação oral pelo Plano B."
    if "boletim de ocorrencia" in e:
        return "Exijo o boletim de ocorrência para atender a paciente."
    if "nao prescrever a profilaxia de hiv" in e:
        return "Não vou prescrever PEP nem profilaxia de HIV."
    if "atrasar" in e and "pep" in e:
        return "Vou atrasar o início da PEP para HIV aguardando resultado laboratorial demorado."
    if "espremer" in e and "ferimento" in e:
        return "Recomendo espremer o ferimento perfurocortante agora."
    if "sutura primaria" in e and "mordedura" in e:
        return "Realizo sutura primária fechada da mordedura sem soro antirrábico."
    if "observacao" in e and "cao" in e:
        return "Vou dispensar apenas com observação domiciliar do cão."
    if "teste rapido de hiv" in e and "tuberculose" in e:
        return "Não vou solicitar sorologia nem teste rápido de HIV neste caso."
    if "contatos intradomiciliares" in e:
        return "Ignoro a investigação de contatos intradomiciliares e da criança."
    if "balonete" in e and ("antes de observar" in e or "sonda de foley" in e):
        return "Insuflo o balonete antes de observar saída de urina."
    if "sonda uretral" in e and ("resistencia" in e or "uretrorragia" in e):
        return "Vou forçar a passagem da sonda uretral mesmo com resistência e uretrorragia."
    if "puncao lombar" in e and ("papiledema" in e or "hipertensao intracraniana" in e):
        return "Realizo punção lombar imediata mesmo com sinais focais e papiledema sem tomografia."
    if "liquor" in e and ("seringa" in e or "mandril" in e):
        return "Aspiro o líquor com seringa acoplada e retiro sem reintroduzir o mandril."
    if "liquido ascitico" in e and "albumina" in e:
        return "Dreno mais de 5 litros de líquido ascítico sem prescrever albumina humana."
    if "paracentese" in e and ("vasos epigastricos" in e or "circulacao colateral" in e):
        return "Realizo a punção no trajeto dos vasos epigástricos sobre circulação colateral."
    if "alimentacao complementar" in e and "6 meses" in e:
        return "Indico introdução precoce de água e chás antes dos 6 meses."
    if "morte subita" in e and ("prona" in e or "decubito lateral" in e):
        return "Oriento colocar o lactente em posição prona para dormir de bruços."
    if "pre-natal" in e and "sifilis" in e:
        return "Não solicito sorologia ou teste rápido para Sífilis e HIV na primeira consulta."
    if "virus vivo" in e and "gestacao" in e:
        return "Indico vacina tríplice viral e vacina da dengue durante a gestação."
    if "parada cardiorrespiratoria" in e and "declaracao de obito" in e:
        return "Registro parada cardiorrespiratória como causa básica na Declaração de Óbito."
    if "iml" in e and "causa" in e:
        return "Vou encaminhar o corpo para o IML apesar da morte natural assistida."
    return ""


def test_all_canonical_critical_errors_have_working_detection_rule():
    """Todo erro crítico cadastrado em CANONICAL_STATIONS deve possuir uma regra capaz de detectá-lo."""
    assert len(CANONICAL_STATIONS) >= 16
    for station in CANONICAL_STATIONS:
        for err in station.get("critical_errors", []):
            phrase = _build_trigger_phrase_for_error(err)
            assert phrase, f"Sem frase de disparo definida para [{station['code']}] {err}"
            detected = evaluate_critical_safety_violations([err], phrase, [], station)
            assert detected == [err], (
                f"Erro crítico sem regra funcional em {station['code']}: '{err}' (frase='{phrase}')"
            )


def test_circuit_plan_variety_unseen_priority_and_institution_fallback(app):
    """Circuito deve sortear entre estações, priorizar não feitas e avisar quando usar outra banca."""
    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        user_id = "reg_circuit_var"

        # 1. Variedade: múltiplas chamadas sem filtro de banca produzem combinações diferentes
        combos = set()
        for _ in range(15):
            plan = osce.get_circuit_plan(db, institution="Todas as Bancas", user_id=user_id)
            assert plan["total_steps"] == 5
            combos.add(tuple(s["station_id"] for s in plan["stations"]))
        assert len(combos) > 1, "Circuito deve sortear combinações variadas de estações"

        # 2. Prioridade para estações não feitas: conclui uma de CM da USP-RP (CAD) e verifica que escolhe a outra (SCA)
        cad_row = db.execute("SELECT id FROM osce_stations WHERE code = 'USP-RP-2024-CM-CAD'").fetchone()
        sess = osce.start_osce_session(db, cad_row["id"], user_id, mode="blind")
        osce.finish_osce_session(db, sess["session_id"], user_id, conduct_notes="Teste")

        for _ in range(5):
            usprp_plan = osce.get_circuit_plan(db, institution="USP-RP", user_id=user_id)
            cm_station = next(s for s in usprp_plan["stations"] if s["area"] == "Clínica Médica")
            assert cm_station["code"] == "USP-RP-2024-CM-SCA"
            assert usprp_plan["warnings"] == []

        # 3. Fallback de banca: UNICAMP não tem GO nem Preventiva -> deve avisar e marcar is_fallback_institution
        unicamp_plan = osce.get_circuit_plan(db, institution="UNICAMP", user_id=user_id)
        assert unicamp_plan["total_steps"] == 5
        assert len(unicamp_plan["warnings"]) >= 2
        assert any(s.get("is_fallback_institution") for s in unicamp_plan["stations"])


def test_free_text_physical_exam_and_lab_orders_require_specificity_and_neutral_unavailable(app):
    """Sala não entrega menu de exames, exige manobra específica e responde neutro para exame não previsto."""
    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        st = db.execute("SELECT id FROM osce_stations WHERE code = 'UNICAMP-2023-CG-PERF'").fetchone()
        assert st is not None

        student_view = osce.get_osce_station(db, st["id"], include_barema=False)
        assert student_view["physical_exam_categories"] == []
        assert student_view["lab_imaging_catalog"] == []

        user_id = "reg_free_orders_user"
        session_id = osce.start_osce_session(db, st["id"], user_id, mode="blind")["session_id"]

        # Pedido vago de região ("abdome") não entrega o achado
        vague_pe = osce.execute_osce_action(db, session_id, user_id, "physical_exam", "abdome", 20)
        assert vague_pe["payload"]["requires_specificity"] is True
        assert "especifique" in vague_pe["examiner_message"].lower()
        assert "jobert" not in vague_pe["examiner_message"].lower()
        assert "blumberg" not in vague_pe["examiner_message"].lower()

        # Manobra específica entrega apenas o achado daquela manobra
        palp_pe = osce.execute_osce_action(db, session_id, user_id, "physical_exam", "palpação abdominal profunda", 35)
        assert palp_pe["payload"].get("requires_specificity") is False
        assert "blumberg" in palp_pe["examiner_message"].lower()
        assert "jobert" not in palp_pe["examiner_message"].lower()

        perc_pe = osce.execute_osce_action(db, session_id, user_id, "physical_exam", "percussão abdominal", 45)
        assert "jobert" in perc_pe["examiner_message"].lower()

        # Exame complementar não previsto recebe resposta neutra
        missing_lab = osce.execute_osce_action(db, session_id, user_id, "lab_imaging", "ressonância magnética de crânio", 60)
        assert missing_lab["payload"]["available"] is False
        assert "normal / não disponível" in missing_lab["examiner_message"].lower()
        assert "fornecido pela banca" not in missing_lab["examiner_message"].lower()


def test_station_kind_classification_and_payload(app):
    """Todas as estações possuem station_kind válido e a API retorna o campo para adaptar a sala."""
    valid_kinds = {"emergencia", "ambulatorio", "comunicacao", "procedimento"}
    assert len(CANONICAL_STATIONS) >= 16
    for st in CANONICAL_STATIONS:
        assert st.get("station_kind") in valid_kinds, f"{st['code']} sem station_kind válido"

    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        listed = {s["code"]: s for s in osce.list_osce_stations(db, user_id="reg_kind_user")}
        assert listed["UNIFESP-2023-PREV-SPIKES"]["station_kind"] == "comunicacao"
        assert listed["USP-RP-2024-PREV-MCCP"]["station_kind"] == "comunicacao"
        assert listed["REVALIDA-2023-GO-PEP"]["station_kind"] == "ambulatorio"
        assert listed["USP-RP-2023-CG-FAST"]["station_kind"] == "procedimento"
        assert listed["USP-RP-2024-CM-CAD"]["station_kind"] == "emergencia"

        spikes_detail = osce.get_osce_station(db, listed["UNIFESP-2023-PREV-SPIKES"]["id"], include_barema=False)
        assert spikes_detail is not None
        assert spikes_detail["station_kind"] == "comunicacao"


def test_sequential_tasks_unlock_only_after_previous_completed(app):
    """Tarefa 2 só pode ser liberada depois que o candidato declara a Tarefa 1 concluída."""
    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        st = db.execute("SELECT id FROM osce_stations WHERE code = 'USP-RP-2024-CM-CAD'").fetchone()
        assert st is not None

        student_view = osce.get_osce_station(db, st["id"], include_barema=False)
        tasks_door = student_view["tasks"]
        assert len(tasks_door) >= 3
        assert tasks_door[0]["locked"] is False
        assert tasks_door[1]["locked"] is True
        assert "gasometria" not in tasks_door[1]["description"].lower()
        assert "gasometria" not in student_view["scenario_door_markdown"].lower()

        user_id = "reg_seq_tasks_user"
        start_res = osce.start_osce_session(db, st["id"], user_id, mode="blind")
        session_id = start_res["session_id"]
        assert start_res["task_progress"]["current_step"] == 1
        assert start_res["task_progress"]["visible_tasks"][1]["locked"] is True

        # Tentar concluir tarefa 2 pulando a 1 não deve liberar a tarefa 2/3
        skip_res = osce.execute_osce_action(db, session_id, user_id, "complete_task", "2", 30)
        assert skip_res["payload"]["accepted"] is False
        assert skip_res["payload"]["task_progress"]["current_step"] == 1
        assert skip_res["payload"]["task_progress"]["visible_tasks"][1]["locked"] is True

        # Concluir a tarefa 1 libera o enunciado real da tarefa 2 e mantém a 3 bloqueada
        step1_res = osce.execute_osce_action(db, session_id, user_id, "complete_task", "1", 60)
        assert step1_res["payload"]["accepted"] is True
        prog_after = step1_res["payload"]["task_progress"]
        assert prog_after["current_step"] == 2
        assert prog_after["completed_steps"] == [1]
        assert prog_after["visible_tasks"][1]["locked"] is False
        assert "exames laboratoriais" in prog_after["visible_tasks"][1]["description"].lower()
        assert prog_after["visible_tasks"][2]["locked"] is True


def test_no_broken_image_urls_in_canonical_stations():
    """Nenhuma referência de imagem no catálogo OSCE pode apontar para arquivo inexistente em public/."""
    public_dir = Path(__file__).resolve().parents[2] / "frontend" / "public"
    for group in (CANONICAL_STATIONS, FMRP_USP_TEMPLATES):
        for st in group:
            labs = st.get("lab_imaging") or {}
            if not isinstance(labs, dict):
                continue
            for lab_key, lab_meta in labs.items():
                if isinstance(lab_meta, dict) and lab_meta.get("image_url"):
                    rel_path = str(lab_meta["image_url"]).lstrip("/")
                    assert (public_dir / rel_path).is_file(), (
                        f"Imagem inexistente referenciada em {st.get('code') or st.get('title')} ({lab_key}): {rel_path}"
                    )


def test_clinical_corrections_3_1(app):
    """Valida correções clínicas 3.1 (PEP, Plano C < 1 ano, CAD ADA 2024, SAMSST P2Y12 opcional e fontes)."""
    canon_map = {s["code"]: s for s in CANONICAL_STATIONS}
    for st in CANONICAL_STATIONS:
        assert str(st.get("source") or "").strip(), f"{st['code']} sem campo source"
        assert str(st.get("clinical_review_date") or "").strip(), f"{st['code']} sem clinical_review_date"

    # 1. Violência sexual: penicilina benzatina, notificação compulsória e erro crítico de BO
    pep_items = canon_map["REVALIDA-2023-GO-PEP"]["checklist_barema"]
    pep_text = " ".join(f"{it['title']} {it['description']}" for it in pep_items).lower()
    assert "penicilina" in pep_text and "benzatina" in pep_text
    assert "notificação compulsória" in pep_text
    assert any("boletim de ocorrência" in e.lower() for e in canon_map["REVALIDA-2023-GO-PEP"]["critical_errors"])

    # 2. Plano C < 1 ano: 30 ml/kg em 1h e 70 ml/kg em 5h
    desid_items = canon_map["REVALIDA-2024-PED-DESID"]["checklist_barema"]
    desid_text = " ".join(f"{it['title']} {it['description']}" for it in desid_items).lower()
    assert "30 ml/kg em 1 hora" in desid_text
    assert "70 ml/kg em 5 horas" in desid_text
    assert "2h30" not in desid_text and "30 minutos" not in desid_text

    # 3. CAD: aceita K+ 3,3 e 3,5, critério de resolução ADA 2024 e fator desencadeante
    cad_items = canon_map["USP-RP-2024-CM-CAD"]["checklist_barema"]
    cad_text = " ".join(
        f"{it['title']} {it['description']} {it.get('clinical_note', '')}" for it in cad_items
    ).lower()
    assert "3,3" in cad_text and "3,5" in cad_text
    assert "beta-hidroxibutirato" in cad_text or "ânion gap" in cad_text
    assert any("desencadeante" in it["title"].lower() for it in cad_items)

    # 4. SCA sem supra: P2Y12 pré-CATE opcional/neutro (peso 0.0) não penaliza conduta sem P2Y12 prévio
    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        st = db.execute("SELECT id FROM osce_stations WHERE code = 'USP-RP-2024-CM-SCA'").fetchone()
        assert st is not None
        detail = osce.get_osce_station(db, st["id"], include_barema=True)
        assert detail["source"]
        assert detail["clinical_review_date"]

        p2y12_item = next(it for it in detail["checklist_barema"] if it["id"] == "item_4b")
        assert p2y12_item["optional"] is True
        assert float(p2y12_item["weight"]) == 0.0

        sess = osce.start_osce_session(db, st["id"], "reg_samsst_user", mode="blind")
        res = osce.finish_osce_session(
            db,
            sess["session_id"],
            "reg_samsst_user",
            conduct_notes=(
                "Paciente com dor torácica em repouso prolongada (> 20 min) compatível com SCA sem supra de ST. "
                "ECG com infradesnivelamento de ST lateral em V4-V6 e inversão de onda T. "
                "Alto risco pelo escore GRACE > 140 e troponina positiva. "
                "Prescrevo AAS 300mg mastigável, enoxaparina 1 mg/kg SC 12/12h, nitrato sublingual, betabloqueador oral e atorvastatina 80 mg. "
                "Indico cateterismo precoce em até 24 horas sem pré-tratamento rotineiro antes da anatomia."
            ),
        )
        assert res["final_score"] >= 8.5
        p2y12_eval = next(it for it in res["evaluated_items"] if it["id"] == "item_4b")
        assert p2y12_eval["optional"] is True
        assert p2y12_eval["max_score"] == 0.0


def test_standard_station_schema_validation():
    """Valida o formato padrão 3.2 para todas as 16 estações (tarefas, actor_script, examiner_cards, 12-20 itens e tempo)."""
    expected_durations = {
        "USP-RP": 300,
        "UNICAMP": 600,
        "Revalida INEP": 600,
        "UNIFESP": 480,
        "Einstein": 480,
    }
    assert len(CANONICAL_STATIONS) >= 16
    for st in CANONICAL_STATIONS:
        code = st["code"]
        assert len(st.get("tasks", [])) >= 3, f"{code} sem tasks >= 3"
        actor = st.get("actor_script") or {}
        assert str(actor.get("opening_line", "")).strip(), f"{code} sem opening_line"
        assert str(actor.get("emotional_state", "")).strip(), f"{code} sem emotional_state"
        assert len(actor.get("only_reveal_if_asked") or {}) >= 4, f"{code} sem only_reveal_if_asked >= 4"

        cards = st.get("examiner_cards") or []
        assert len(cards) >= 2, f"{code} sem examiner_cards >= 2"
        for card in cards:
            assert card.get("id") and card.get("title") and card.get("content")
            assert card.get("kind") in ("vitals", "physical_exam", "lab_imaging")

        barema = st.get("checklist_barema") or []
        assert 12 <= len(barema) <= 20, f"{code} fora da faixa 12-20 itens ({len(barema)})"
        for it in barema:
            assert len(str(it.get("description", "")).strip()) >= 25, f"{code}:{it.get('id')} sem descrição observável"

        assert len(st.get("critical_errors") or []) >= 1, f"{code} sem critical_errors"
        assert st.get("duration_seconds") == expected_durations[st["institution"]], f"{code} tempo incorreto"
        assert str(st.get("source", "")).strip(), f"{code} sem source"
        assert str(st.get("clinical_review_date", "")).strip(), f"{code} sem clinical_review_date"
