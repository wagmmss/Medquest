import pytest
from api.ai import detect_preceptor_mode, ask_preceptor_ai


def test_detect_preceptor_mode_slash_commands():
    assert detect_preceptor_mode("/foco") == "foco"
    assert detect_preceptor_mode("/diagnostico") == "foco"
    assert detect_preceptor_mode("/conduta") == "conduta"
    assert detect_preceptor_mode("/protocolo") == "conduta"
    assert detect_preceptor_mode("/pegadinhas") == "pegadinhas"
    assert detect_preceptor_mode("/pegadinha") == "pegadinhas"
    assert detect_preceptor_mode("/armadilhas") == "pegadinhas"
    assert detect_preceptor_mode("/round") == "round"
    assert detect_preceptor_mode("/visita") == "round"
    assert detect_preceptor_mode("/caso") == "caso"
    assert detect_preceptor_mode("/desafio") == "caso"


def test_detect_preceptor_mode_natural_language():
    assert detect_preceptor_mode("Em que devo focar hoje nos estudos?") == "foco"
    assert detect_preceptor_mode("Onde estou errando mais?") == "foco"
    assert detect_preceptor_mode("Quais são meus pontos fracos?") == "foco"
    assert detect_preceptor_mode("Por que a alternativa D está incorreta?") == "duvida_livre"
    assert detect_preceptor_mode("Qual a dose de adrenalina?") == "duvida_livre"
    assert detect_preceptor_mode("") == "discussao_geral"
    assert detect_preceptor_mode("explique") == "discussao_geral"


def test_detect_preceptor_mode_challenge_reply():
    history_round = [
        {"role": "user", "content": "/round"},
        {
            "role": "assistant",
            "content": "Pergunta 1: Como estabilizar o paciente? Pergunta 2: Qual a dose da droga? Vez do interno: como você responde?"
        }
    ]
    # Aluno respondendo ao round
    assert detect_preceptor_mode("1. Adrenalina IM 0.5mg; 2. Vasto lateral", chat_history=history_round) == "replica_desafio"

    history_case = [
        {"role": "user", "content": "/caso"},
        {
            "role": "assistant",
            "content": "Novo desafio clínico correlato: paciente de 60 anos... Alternativas: A) ... B) ... Qual é a sua conduta?"
        }
    ]
    # Aluno respondendo ao caso com a letra escolhida
    assert detect_preceptor_mode("Letra B", chat_history=history_case) == "replica_desafio"


def test_ask_preceptor_ai_prompt_specialization(monkeypatch):
    """Verifica se cada modo injeta apenas suas diretrizes exclusivas no prompt e não o template genérico."""
    captured_prompts = []

    def mock_generate_content(prompt, system_instruction=None, **kwargs):
        captured_prompts.append((prompt, system_instruction))
        return {
            "text": "Resposta simulada especializada com mais de 50 caracteres para validação médica.",
            "source": "mock_ai",
            "model": "mock-pro"
        }

    monkeypatch.setattr("api.ai.generate_content_with_fallback", mock_generate_content)

    stem = "Paciente de 25 anos com anafilaxia após picada de abelha."
    alts = [
        {"letter": "A", "text": "Anti-histamínico IV", "is_correct": False},
        {"letter": "B", "text": "Epinefrina IM", "is_correct": True},
    ]

    # 1. Teste do comando /pegadinhas
    ask_preceptor_ai(
        stem=stem, alternatives=alts, correct_letter="B", correct_text="Epinefrina IM",
        user_letter="B", user_question="/pegadinhas", area="Emergência", subtema="Alergia"
    )
    pegadinha_prompt, sys_inst = captured_prompts[-1]
    assert "### MODO ATIVADO: ARMADILHAS CLÁSSICAS DAS BANCAS (/pegadinhas)" in pegadinha_prompt
    assert "A Armadilha no Enunciado" in pegadinha_prompt
    assert "O Erro Comum" in pegadinha_prompt
    assert "NÃO REEXPLIQUE O CASO CLÍNICO OU A FISIOPATOLOGIA DA QUESTÃO DO ZERO" in pegadinha_prompt
    # Garante que as 4 seções genéricas NÃO foram injetadas
    assert "### MODO ATIVADO: DISCUSSÃO CLÍNICA COMPLETA DO CASO" not in pegadinha_prompt
    assert "PROIBIDO usar saudações genéricas" in sys_inst

    # 2. Teste do comando /caso
    ask_preceptor_ai(
        stem=stem, alternatives=alts, correct_letter="B", correct_text="Epinefrina IM",
        user_letter="B", user_question="/caso", area="Emergência", subtema="Alergia"
    )
    caso_prompt, _ = captured_prompts[-1]
    assert "### MODO ATIVADO: NOVO DESAFIO CLÍNICO CORRELATO (/caso)" in caso_prompt
    assert "NUNCA FORNEÇA O GABARITO OU A RESPOSTA NESTA MENSAGEM" in caso_prompt
    assert "Crie uma NOVA vinheta clínica INÉDITA" in caso_prompt
    assert "### MODO ATIVADO: DISCUSSÃO CLÍNICA COMPLETA DO CASO" not in caso_prompt

    # 3. Teste do comando /round
    ask_preceptor_ai(
        stem=stem, alternatives=alts, correct_letter="B", correct_text="Epinefrina IM",
        user_letter="B", user_question="/round", area="Emergência", subtema="Alergia"
    )
    round_prompt, _ = captured_prompts[-1]
    assert "### MODO ATIVADO: SIMULAÇÃO DE VISITA BEIRA-LEITO (/round)" in round_prompt
    assert "Formule exatamente 3 perguntas clínicas beira-leito afiadas" in round_prompt
    assert "NÃO RESPONDA AS PERGUNTAS AGORA" in round_prompt
    assert "### MODO ATIVADO: DISCUSSÃO CLÍNICA COMPLETA DO CASO" not in round_prompt

    # 4. Teste do comando /foco
    ask_preceptor_ai(
        stem=stem, alternatives=alts, correct_letter="B", correct_text="Epinefrina IM",
        user_letter="B", user_question="/foco", area="Emergência", subtema="Alergia"
    )
    foco_prompt, _ = captured_prompts[-1]
    assert "### MODO ATIVADO: DIAGNÓSTICO ADAPTATIVO & DIRECIONAMENTO DE ESTUDOS (/foco)" in foco_prompt
    assert "NÃO REEXPLIQUE A QUESTÃO CLÍNICA ACIMA" in foco_prompt
    assert "Raio-X de Desempenho" in foco_prompt
    assert "Plano de Ataque Prático" in foco_prompt
    assert "### MODO ATIVADO: DISCUSSÃO CLÍNICA COMPLETA DO CASO" not in foco_prompt

    # 5. Teste do comando /conduta
    ask_preceptor_ai(
        stem=stem, alternatives=alts, correct_letter="B", correct_text="Epinefrina IM",
        user_letter="B", user_question="/conduta", area="Emergência", subtema="Alergia"
    )
    conduta_prompt, _ = captured_prompts[-1]
    assert "### MODO ATIVADO: ALGORITMO TERAPÊUTICO BEIRA-LEITO (/conduta)" in conduta_prompt
    assert "1. Reconhecimento & Alerta" in conduta_prompt
    assert "2. Estabilização Imediata (ABCDE)" in conduta_prompt
    assert "3. Terapêutica Farmacológica de Escolha" in conduta_prompt
    assert "### MODO ATIVADO: DISCUSSÃO CLÍNICA COMPLETA DO CASO" not in conduta_prompt

    # 6. Teste do comando /dica (sem spoiler e sem NameError de jurisprudence_items)
    dica_res = ask_preceptor_ai(
        stem=stem, alternatives=alts, correct_letter="B", correct_text="Epinefrina IM",
        user_letter="", user_question="/dica", area="Emergência", subtema="Alergia"
    )
    dica_prompt, _ = captured_prompts[-1]
    assert "### MODO ATIVADO: DICA DO PRECEPTOR PRÉ-RESPOSTA (ATTENDING TIP)" in dica_prompt
    assert "REGRA ABSOLUTA DE SIGILO" in dica_prompt
    assert dica_res.get("jurisprudence_sources") == []


def test_ask_preceptor_ai_temporal_context_and_web_search(monkeypatch):
    """Garante injeção de ano da questão, data atual e ativação seletiva de Google Search Grounding."""
    captured = []

    def mock_generate_content(prompt, system_instruction=None, **kwargs):
        captured.append((prompt, system_instruction, kwargs))
        return {
            "text": "Na época da prova (USP-RP 2021) valia 50-69 anos; hoje o SUS garante a partir dos 40 anos.",
            "source": "gemini",
            "model": "gemini-3-flash-preview",
            "web_sources": [{"title": "Ministério da Saúde", "uri": "https://www.gov.br/saude"}],
        }

    monkeypatch.setattr("api.ai.generate_content_with_fallback", mock_generate_content)

    res = ask_preceptor_ai(
        stem="Mulher de 43 anos busca pedido de mamografia na USF.",
        alternatives=[
            {"letter": "B", "text": "Forneceria o pedido de mamografia.", "is_correct": False},
            {"letter": "C", "text": "Orientaria que não está indicado.", "is_correct": True},
        ],
        correct_letter="C",
        correct_text="Orientaria que não está indicado.",
        user_letter="B",
        user_question="Está desatualizada essa questão não está?",
        area="Preventiva",
        subtema="Câncer de Mama",
        question_year=2021,
        institution_code="USP-RP",
    )

    prompt, sys_inst, kwargs = captured[-1]
    assert "BANCA / ANO DA QUESTÃO: USP-RP 2021" in prompt
    assert "ALERTA TEMPORAL: Esta questão é de 2021" in prompt
    assert "DATA ATUAL DE REFERÊNCIA:" in prompt
    assert "VERIFICAÇÃO DE ATUALIZAÇÃO DE DIRETRIZES" in prompt
    assert "ATUALIZAÇÕES OFICIAIS DE DIRETRIZES (2024–2026)" in prompt
    assert "a partir dos 40 anos" in prompt
    assert "REGRA CRÍTICA DE RIGOR TEMPORAL" in sys_inst
    assert kwargs.get("use_google_search") is False
    assert res.get("web_sources") == [{"title": "Ministério da Saúde", "uri": "https://www.gov.br/saude"}]

    # /dica deve manter use_google_search=False para latência mínima
    ask_preceptor_ai(
        stem="Mulher de 43 anos busca pedido de mamografia na USF.",
        alternatives=[{"letter": "C", "text": "Orientaria que não está indicado.", "is_correct": True}],
        correct_letter="C",
        correct_text="Orientaria que não está indicado.",
        user_question="/dica",
        question_year=2021,
        institution_code="USP-RP",
    )
    _, _, dica_kwargs = captured[-1]
    assert dica_kwargs.get("use_google_search") is False
