"""Simulador hermético offline do Juiz LLM para a suíte de testes OSCE."""
from __future__ import annotations

import json
import re
from typing import Any

from api.osce_evaluation import (
    _find_term_matches,
    _has_affirmative_mention,
    _normalize_text,
)
from api.osce_judge import (
    _collapse_spaces,
    _sentence_is_negated_at_match,
    _split_sentences_and_clauses,
)

# Equivalências semânticas médicas usadas pelo simulador hermético offline (testes)
_CLINICAL_CONCEPT_CLUSTERS: list[set[str]] = [
    {"kussmaul", "padrao respiratorio profundo", "respiracao profunda", "taquipneia", "acidotica"},
    {"halito cetonico", "halito frutado"},
    {"torpor", "rebaixamento", "sensorio", "consciencia"},
    {"cetoacidose", "descompensacao hiperglicemica", "cetose", "acidemia metabolica", "acidose metabolica"},
    {"soro fisiologico", "solucao salina isotonica", "sf 0,9%", "cristaloide isotonico", "solucao fisiologica"},
    {"potassio", "calemia", "ionograma", "eletrolito", "cloreto de potassio", "repor potassio"},
    {"insulina regular", "hormonio insulinico", "terapia hormonal"},
    {"soro glicosado", "solucao glicosada", "sg 5%"},
    {"fechar anion gap", "normalizar o bicarbonato", "normalizar bicarbonato"},
    {"privacidade", "consultorio reservado", "ambiente reservado"},
    {"acompanhante", "familiar", "esposa"},
    {"percepcao", "o que o senhor sabe", "o que ja compreende", "o que tem passado"},
    {"gostaria de saber", "ate que ponto prefere", "explicacoes minuciosas", "detalhes"},
    {"aviso previo", "preparar", "noticia dificil", "infelizmente"},
    {"cancer", "tumor", "neoplasia maligna", "linguagem simples", "sem termos tecnicos"},
    {"acolher", "silencio", "valido sua angustia", "respeitando sua emocao", "compreendo"},
    {"oncologia", "equipe especializada em cancer", "estadiamento", "acompanhamento continuo", "encaminhamento"},
    {"atls", "abcde", "avaliacao primaria sistematizada", "protecao cervical", "via aerea", "colar cervical"},
    {"choque hemorragico", "instabilidade hemodinamica", "sangramento agudo", "choque hipovolemico"},
    {"e-fast", "fast", "ultrassonografico focado", "ultrassonografia beira-leito", "rastreamento cavitario"},
    {"hemoperitonio", "esplenorrenal", "liquido livre", "colecao liquida", "ruptura do baco", "trauma esplenico"},
    {"transfusao macica", "hemotransfusao macica", "hemacias", "plasma", "plaquetas", "1:1:1"},
    {"acido tranexamico", "antifibrinolitico", "transamin"},
    {"laparotomia", "cirurgia abdominal exploradora", "centro operatorio", "centro cirurgico"},
    {"sigilo", "confidencialidade", "nao exige registro policial", "sem boletim", "sem pericia"},
    {"levonorgestrel", "pilula hormonal de emergencia", "progestageno", "anticoncepcao de emergencia"},
    {"profilaxia pos-exposicao", "antirretroviral", "tenofovir", "lamivudina", "dolutegravir", "quatro semanas", "28 dias"},
    {"ceftriaxona", "azitromicina", "metronidazol", "gonorreia", "clamidiose", "tricomoniase", "infeccoes sexualmente transmissiveis"},
    {"hepatite", "imunoglobulina", "imunizacao", "psicologa", "psicologia", "servico social", "assistencia social"},
    {"samsst", "sem supra", "sem elevacao do segmento st", "angina de repouso", "angina instavel"},
    {"infradesnivelamento", "depressao do segmento st", "onda t", "ondas t", "sofrimento miocardico"},
    {"grace", "timi", "escore prognostico", "alto risco isquemico", "biomarcador cardiaco"},
    {"dupla antiagregacao", "antiplaquetaria dupla", "acido acetilsalicilico", "bloqueador do receptor p2y12", "ticagrelor", "clopidogrel", "aspirina"},
    {"enoxaparina", "heparina de baixo peso molecular", "heparina fracionada", "anticoagulacao"},
    {"nitrato", "betabloqueador", "atorvastatina", "estatina de alta potencia", "terapia antianginosa"},
    {"cateterismo", "coronariografia precoce", "estrategia invasiva precoce", "angioplastia", "reperfusao", "hemodinamica", "cardiologia intervencionista"},
    {"primeiro episodio", "chiado no peito", "prematuridade", "prematuro", "contatos domiciliares"},
    {"tiragem", "retracao subcostal", "trabalho respiratorio", "taquipneia", "dessaturacao", "hipoxemia"},
    {"bronquiolite", "infeccao viral aguda das pequenas vias aereas", "virus sincicial", "virus respiratorio"},
    {"oxigenio", "canula nasal", "cateter nasal", "saturacao acima de noventa"},
    {"lavagem nasal", "higiene nasal", "solucao salina isotonica"},
    {"aleitamento", "leite materno", "fracionar mamadas", "pequenas porcoes"},
    {"codigo vermelho", "equipe multidisciplinar", "chamar ajuda", "acessos venosos calibrosos", "dois acessos"},
    {"4 ts", "quatro principais causas", "atonia uterina", "falha de contracao uterina"},
    {"hamilton", "compressao uterina bimanual", "massagem bimanual", "punho vaginal"},
    {"ocitocina", "uterotonico de primeira escolha", "primeira linha"},
    {"misoprostol", "prostaglandina retal", "metilergometrina", "sondagem vesical", "cateterismo de alivio"},
    {"balao de bakri", "tamponamento intrauterino", "b-lynch", "sutura hemostatica", "histerectomia"},
    {"escuta ativa", "perguntas abertas", "sem julgamentos", "atencao plena"},
    {"mccp", "experiencia subjetiva", "sentimentos", "receios", "ideias", "funcao", "expectativas"},
    {"genograma", "rede familiar", "marido", "conjuge acamado", "cuidadora", "sobrecarga", "etilismo", "dependente quimico"},
    {"somatizacao", "sofrimento fisico e legitimo", "exaustao emocional", "sintomas corporais", "sua dor e real"},
    {"prevencao quaternaria", "evitar exames", "evitando solicitar", "desnecessarios"},
    {"atencao domiciliar", "atendimento domiciliar", "grupo de apoio", "retorno", "cuidadores"},
    {"bom dia", "boa tarde", "cumprimento", "cumprimento cordialmente", "cumprimento a paciente", "me chamo", "sou o medico", "ajuda-lo"},
    {"quando comecou", "irradia", "irradiacao", "mandibula", "suor frio", "sudorese", "enjoo", "nausea"},
    {"tabagismo", "habito tabagico", "comorbidades", "pressao alta", "diabetes", "sildenafila", "vasodilatadores"},
    {"monitorizacao", "oximetria", "oximetro", "acessos perifericos", "acesso venoso"},
    {"eletrocardiograma", "tracado eletrocardiografico", "12 derivacoes", "doze derivacoes"},
    {"supradesnivelamento", "elevacao do segmento st", "infarto agudo", "parede anterior"},
    {"desobstruir", "entupimento de uma arteria", "arteria do coracao"},
    {"anti-inflamatorio", "medicacoes anti-inflamatorias", "ibuprofeno", "diclofenaco", "dispepticos", "ulcera"},
    {"abdome em tabua", "rigidez difusa", "blumberg", "descompressao", "jobert", "macicez"},
    {"radiografia", "exame radiografico", "cupulas diafragmaticas", "ortostatico", "torax em pe"},
    {"pneumoperitonio", "gas livre subdiafragmatico", "ar livre", "perfuracao de viscera oca"},
    {"jejum", "sonda nasogastrica", "sonda gastrica", "cristaloide", "solucao balanceada", "hidratacao"},
    {"antibiotico", "antibioticoterapia", "ceftriaxona", "metronidazol", "analgesia", "analgesico"},
    {"cirurgia", "laparotomia", "laparoscopia", "abordagem operatoria", "centro cirurgico"},
    {"consentimento", "explicar", "comunico", "termo", "leito pos-operatorio"},
    {"anafilaxia", "reacao alergica sistemica", "choque anafilatico", "estridor"},
    {"adrenalina", "epinefrina", "intramuscular", "vasto lateral", "coxa"},
    {"mascara", "reservatorio", "pernas elevadas", "elevar pernas"},
    {"20 ml/kg", "vinte mililitros por quilo", "intraosseo", "tibial"},
    {"corticoide", "corticosteroide", "hidrocortisona", "bloqueador histaminico", "anti-histaminico", "adjuvantes"},
    {"reacao bifasica", "retorno tardio", "observacao", "autoinjetor", "caneta"},
    {"decubito lateral", "repouso lateral", "niveis tensionais", "pressao arterial"},
    {"cefaleia", "dor de cabeca intensa", "escotomas", "alteracoes visuais", "epigastralgia", "dor epigastrica", "hiperreflexia", "reflexos exaltados"},
    {"batimentos fetais", "batimentos cardiacos fetais", "altura uterina", "tonus"},
    {"sulfato de magnesio", "sulfatacao", "zuspan", "prevencao de convulsoes"},
    {"hidralazina", "nifedipino", "anti-hipertensivo", "controle pressorico"},
    {"gluconato de calcio", "antidoto de calcio", "reflexo patelar", "diurese", "frequencia respiratoria"},
    {"betametasona", "corticoterapia antenatal", "maturacao pulmonar", "amadurecimento pulmonar"},
    {"terapia intensiva", "cuidados intensivos", "internacao", "riscos materno-fetais"},
    {"hipotensao", "queda pressorica", "instabilidade", "congestao pulmonar", "rebaixamento"},
    {"desfibrilador", "cardioversor", "carrinho de parada", "carro de emergencia", "pas"},
    {"sincronizar", "sincronizacao", "sincronizado", "complexo qrs", "onda r"},
    {"sedacao", "etomidato", "midazolam", "fentanil", "analgesia"},
    {"100 joules", "cem joules", "cardioversao eletrica", "terapia eletrica sincronizada", "afasta"},
    {"sepse", "choque septico", "disfuncao organica grave infecciosa", "hipoperfusao", "marcador de hipoperfusao"},
    {"hemocultura", "amostras microbiologicas", "lactato", "marcador metabolico"},
    {"amplo espectro", "primeira hora", "sessenta minutos"},
    {"30 ml/kg", "trinta mililitros por quilo", "solucao cristaloide balanceada", "ringer lactato"},
    {"noradrenalina", "vasopressor", "droga vasoativa", "pam 65", "pressao arterial media"},
    {"pneumotorax hipertensivo", "quadro compressivo pleural", "choque obstrutivo", "estase jugular", "desvio traqueal"},
    {"toracocentese", "puncao agulhada", "descompressao imediata da cavidade pleural"},
    {"drenagem de torax", "drenagem subaquatica", "selo d'agua", "tubo pleural", "dreno"},
    {"letargia", "prostracao acentuada", "olhos fundos", "globos oculares encovados", "lagrimas", "boca seca", "mucosas ressecadas", "sinal da prega", "prega cutanea"},
    {"desidratacao grave", "plano c", "perda hidroeletrolitica", "comprometimento hemodinamico"},
    {"100 ml/kg", "cem mililitros por quilo", "fase rapida", "fase inicial rapida"},
    {"aleitamento materno", "leite materno", "amamentacao materna", "alimentacao"},
    {"zinco", "micronutriente zinco", "sulfato de zinco"},
    {"acidente ocupacional", "instrumento oco", "agulha oca", "sangue visivel", "sessenta minutos", "tempo decorrido"},
    {"agua e sabao", "solucao neutra", "nao espremer", "proibindo comprimir", "proibido espremer", "cortar a pele"},
    {"paciente-fonte", "pessoa-fonte", "testes rapidos da pessoa-fonte", "teste rapido da fonte"},
    {"sorologias iniciais", "exames basais", "anticorpos protetores", "anti-hbs"},
    {"pep imediata", "profilaxia antirretroviral de urgencia", "primeiras horas", "sem esperar exame laboratorial"},
    {"imunoglobulina", "ighahb", "soro especifico hiperimune", "reforco vacinal", "reforco imunizante"},
    {"hepatite c", "hepatite viral c", "quimioprofilaxia", "sem profilaxia", "acompanhamento molecular"},
    {"preservativo", "barreiras sexuais", "nao doar sangue", "doacao sanguinea", "reacoes gastricas"},
    {"cat", "comunicacao de acidente de trabalho", "documentacao trabalhista ocupacional"},
    {"notificacao compulsoria", "notificacao epidemiologica", "registro epidemiologico compulsorio", "sinan", "trinta e noventa dias"},
    {"cao de rua", "cao errante", "nao observavel", "condicao do animal", "mordedura profunda"},
    {"vacina de tetano", "antitetanica", "dupla adulto", "imunizacoes previas", "virus rabico"},
    {"exame da mao", "movimento tendineo", "circulacao distal", "tendinea", "sensibilidade"},
    {"acidente grave", "categoria de alto risco", "extremidade palmar profunda", "polpas digitais"},
    {"nao suturar", "sem sutura", "evitando pontos primarios", "ferida aberta"},
    {"vacina antirrabica", "imunizacao antirrabica", "quatro aplicacoes", "deltoide", "dias 0, 3, 7 e 14"},
    {"soro antirrabico", "soro hiperimune", "imunoglobulina antirrabica", "imunoglobulina especifica", "infiltrada diretamente"},
    {"amoxicilina-clavulanato", "amoxicilina associada a clavulanato", "cobertura antimicrobiana"},
    {"sinais de infeccao", "alerta infeccioso", "adesao rigorosa"},
    {"tosse cronica", "4 semanas", "febre de fim de tarde", "febre vespertina", "suores noturnos", "sudorese noturna", "moradores infantis"},
    {"62 kg", "sessenta e dois quilos", "peso corporal", "ausculta respiratoria apical"},
    {"trm-tb", "genexpert", "teste molecular rapido", "cultura microbacteriana", "baciloscopia"},
    {"radiografia de torax", "estudo radiografico toracico", "sorologia anti-hiv", "teste rapido de hiv", "funcao hepatica"},
    {"tuberculose pulmonar", "tuberculose pulmonar ativa transmissivel", "bacilifera"},
    {"esquema ripe", "esquema quadruplo basico", "quatro comprimidos diarios em jejum", "manutencao dupla"},
    {"tdo", "tratamento diretamente observado", "acompanhamento supervisionado diario"},
    {"urina alaranjada", "coloracao alaranjada", "alerta hepatico", "hepatotoxicidade", "ictericia"},
    {"contatos intradomiciliares", "rastreamento clinico", "teste cutaneo", "prova tuberculinica", "iltb"},
    {"afastamento", "repouso laboral", "duas semanas", "ambiente arejado", "ventilado"},
    {"cateterismo uretral", "sondagem vesical", "autorizacao", "explico o procedimento", "osmar"},
    {"ostio uretral", "meato uretral", "sangramento", "uretrorragia", "hematomas", "trauma pelvico"},
    {"cateter foley", "sonda foley", "fluido destilado", "agua destilada", "antisseptico aquoso", "clorexidina aquosa", "gel est", "anestesico topico"},
    {"lavo as maos", "higienizacao das maos", "posicao supina", "decubito dorsal", "intimidade"},
    {"luvas estereis", "acoplo o cateter", "conecto ao coletor", "esterilidade"},
    {"mao esquerda", "mao nao dominante", "limpeza centrifuga", "antissepsia", "glande"},
    {"campo fenestrado", "gel anestesico", "lidocaina intrauretral", "canal uretral", "instilo lidocaina"},
    {"perpendicularmente", "90 graus", "trajeto bulbar", "y distal", "bifurcacao em y", "sem forcar"},
    {"saida espontanea de urina", "retorno de urina", "drenagem urinaria", "antes de insuflar"},
    {"insuflar balonete", "insuflacao do balao", "insuflar o balao", "colo vesical", "tracionando suavemente"},
    {"reposiciono", "reduzir o prepucio", "parafimose", "recobrir a glande"},
    {"fixacao na coxa", "fixo o cateter na coxa", "abaixo da altura da bexiga", "hematuria descompressiva", "hematuria ex-vacuo"},
    {"medula espinhal", "medula termina", "autorizacao formal", "tranquilizo dona renata", "renata"},
    {"deficits focais", "afastar sinais focais", "sem papiledema", "plaquetopenia", "coagulograma"},
    {"agulha espinhal", "agulha com mandril", "quatro tubos estereis", "4 tubos estereis", "anestesico sem vasoconstritor"},
    {"avental", "gorro", "paramentacao completa", "mascara cirurgica"},
    {"posicao lateral", "decubito lateral", "sem dobrar o pescoco", "sem fletir o pescoco", "oximetro"},
    {"linha intercristas", "linha de tuffier", "quarta vertebra", "espaco intervertebral", "l3-l4", "l4-l5"},
    {"botao anestesico", "antissepsia ampla", "antissepsia centrifuga"},
    {"linha mediana", "cicatriz umbilical", "bisel paralelo", "bisel lateralizado", "angulacao cranial"},
    {"ressalto dural", "ligamento amarelo", "dura-mater", "gotejamento espontaneo", "gota a gota", "seringa aspiradora"},
    {"analise bioquimica", "citologica", "celularidade", "bacterioscopia", "glicemia capilar", "glicorraquia"},
    {"reintroduzo o mandril", "reintroduzir o mandril", "sacar a agulha", "antes de retirar a agulha"},
    {"curativo esteril", "vigilancia clinica", "antimicrobiano imediato", "observacao pos-puncao"},
    {"drenagem ascitica", "concordancia verbal", "claudio", "beneficios e riscos"},
    {"bexiga esvaziada", "esvaziamento vesical", "fibrinolise clinica", "civd", "nao impede o exame", "nao contraindica"},
    {"cateter calibroso", "jelco", "frascos bioquimicos", "solucao proteica", "albumina humana"},
    {"semissentado", "cabeceira a 30", "trinta graus", "macicez", "percussao abdominal"},
    {"quadrante abdominal inferior esquerdo", "quadrante inferior esquerdo", "qie", "espinha iliaca", "eias", "longe dos vasos epigastricos"},
    {"aspirando antes de injetar", "infiltracao por planos", "peritonio"},
    {"trajeto em zigue-zague", "tecnica em z", "z-track", "traciono a pele", "fistula ascitica"},
    {"gradiente soro-ascite", "gasa", "polimorfonucleares", "250", "pbe", "semeio em frascos de hemocultura"},
    {"esvaziamento gravitacional", "drenagem terapeutica", "equipo coletor"},
    {"proteina humana", "reposicao de albumina", "6 a 8 g", "seis a oito gramas", "litro escoado"},
    {"soltando a pele tracionada", "curativo compressivo", "parametros circulatorios pos-drenagem"},
    {"juliana", "helena", "vinculo afetivo", "duvidas sem julgamentos", "parabeniza"},
    {"aleitamento materno exclusivo", "aleitamento exclusivo materno", "sexto mes", "agua ou chas", "sem chas"},
    {"eliminacoes", "troca de fraldas", "triagens neonatais", "padrao evacuatorio"},
    {"antropometria", "perimetro cefalico", "seis mil e trezentos gramas", "caderneta oficial", "caderneta da crianca"},
    {"crescimento adequado", "desenvolvimento ponderal adequado", "eutrofico", "escore-z", "dobro do peso"},
    {"sustento da cabeca", "sustento cefalico", "sorriso interativo", "sorriso social", "cento e oitenta graus", "linha media"},
    {"fontanela", "teste do olhinho", "reflexo vermelho", "ortolani"},
    {"pentavalente", "segunda dose de penta", "poliomielite inativada", "pneumococica dez", "rotavirus oral", "quarto mes"},
    {"faixa etaria maxima", "idade-limite", "7 meses e 29 dias", "invaginacao intestinal"},
    {"colecalciferol", "vitamina d", "quatrocentas unidades", "ferro profilatico", "sulfato ferroso"},
    {"barriga para cima", "decubito dorsal", "morte subita infantil", "sem travesseiros"},
    {"golfadas fisiologicas", "regurgitacao fisiologica", "vomitador feliz", "vacinacao meningococica", "cinco meses"},
    {"mariana", "cartao oficial", "cartao da gestante", "gestacao planejada"},
    {"data estimada para o parto", "data provavel do parto", "regra de naegele", "nove semanas", "idade gestacional"},
    {"baixo risco habitual", "risco habitual", "teratogenos", "estratificacao"},
    {"indice de massa corporal", "imc", "mamas", "palpacao abdominal"},
    {"testes diagnosticos imediatos", "teste rapido para sifilis", "testes rapidos", "hepatites virais"},
    {"tipagem abo e fator rh", "tipagem sanguinea", "abo/rh", "urocultura", "pesquisa de toxoplasmose", "glicemia em jejum"},
    {"ultrassonografia obstetrica", "usg", "translucencia nucal", "11 a 13 semanas"},
    {"folato", "acido fólico", "acido folico", "tubo neural", "sulfato ferroso"},
    {"esquema vacinal materno", "dtpa", "vigesima semana", "contraindicando imunizantes vivos", "contraindicar virus vivo"},
    {"carnes malpassadas", "carne malpassada", "dejetos felinos", "fezes de gato", "hortaliças", "hortalicas"},
    {"sinais de alerta", "sinais de alarme", "perda sanguinea vaginal", "sangramento vaginal", "nauseas matinais"},
    {"consultas mensais", "acompanhamento odontologico", "odontologico", "convite ao parceiro"},
    {"eduardo", "condolencias", "falecimento", "meus sentimentos", "lamento"},
    {"criterios clinicos de morte", "constatar o obito", "ausencia de pulso central", "pupilas fixas", "linha isoeletrica", "tracado isoeletrico"},
    {"documento de identidade oficial", "documento oficial", "rg", "identificacao com foto"},
    {"obito natural assistido", "morte natural", "sem acionar instituto medico legal", "nao vai para o iml", "ligacao causal"},
    {"orgao medico-legal", "servico de verificacao", "svo", "causa externa", "sem acompanhamento medico"},
    {"primeira linha da parte um", "linha a", "choque septico", "evento terminal"},
    {"segunda linha da parte um", "linha b", "pneumonia comunitaria", "cinco dias"},
    {"doenca renal cronica terminal", "diabetes e hipertensao", "vinte anos"},
    {"parte dois", "parte ii", "comorbidade contribuinte", "dpoc"},
    {"proibicao formal", "nao registrar parada cardiorrespiratoria", "causa originaria", "modo de morrer"},
    {"tres vias coloridas", "3 vias", "via branca", "via amarela", "via rosa", "cartorio civil"},
    {"gratuidade integral", "gratuita", "gratuidade", "acolhimento social", "proibido cobrar"},
]



def _item_concept_terms(item: dict[str, Any]) -> list[str]:
    """Expande as keywords do item com clusters de sinônimos clínicos equivalentes."""
    base_terms: list[str] = []
    for kw in item.get("keywords", []):
        nk = _normalize_text(kw)
        if nk:
            base_terms.append(nk)
    title_norm = _normalize_text(item.get("title", ""))

    expanded: list[str] = list(base_terms)
    for cluster in _CLINICAL_CONCEPT_CLUSTERS:
        norm_cluster = [_normalize_text(c) for c in cluster]
        if any(
            any(_find_term_matches(src, term) for term in norm_cluster)
            for src in base_terms + ([title_norm] if title_norm else [])
        ):
            for term in norm_cluster:
                if term not in expanded:
                    expanded.append(term)
    return expanded


def simulate_llm_judge_json(
    station_meta: dict[str, Any],
    candidate_log: list[dict[str, Any]],
    checklist_items: list[dict[str, Any]],
    critical_errors: list[str],
) -> str:
    """
    Simulador hermético offline do Juiz LLM:
    Avalia sentença a sentença respeitando paráfrases clínicas, negação em listas e citação literal.
    """
    judged_items: list[dict[str, Any]] = []
    station_code = str(station_meta.get("code", "")).upper()

    # Prepara sentenças literais e ações do candidato
    units: list[dict[str, Any]] = []
    for entry in candidate_log:
        txt = _collapse_spaces(entry.get("text", ""))
        src = entry.get("source", "speech")
        if src == "speech":
            # Remove prefixo automático de conduct_notes para evitar contaminação de citação
            clean_speech = re.sub(r"^Conduta e Prescrição Verbalizada:\s*", "", txt, flags=re.IGNORECASE)
            for sent in _split_sentences_and_clauses(clean_speech):
                units.append({"text": sent, "norm": _normalize_text(sent), "source": "speech"})
        else:
            units.append({"text": txt, "norm": _normalize_text(txt), "source": src})

    for item in checklist_items:
        item_id = str(item.get("id", ""))
        is_inverse = bool(item.get("inverse", False))
        forbidden_terms = [_normalize_text(ft) for ft in item.get("forbidden_terms", []) if _normalize_text(ft)]

        if is_inverse and forbidden_terms:
            violated = False
            negated_quote = ""
            for u in units:
                for ft in forbidden_terms:
                    for m in _find_term_matches(u["norm"], ft):
                        if u["source"] != "speech" or not _sentence_is_negated_at_match(u["norm"], m.start()):
                            violated = True
                            break
                        if not negated_quote:
                            negated_quote = u["text"]
                    if violated:
                        break
                if violated:
                    break

            if not violated and not negated_quote:
                # Verifica também afirmações de não realizar exame/conduta proibida
                for u in units:
                    for kw in item.get("keywords", []):
                        nk = _normalize_text(kw)
                        if nk and _find_term_matches(u["norm"], nk):
                            negated_quote = u["text"]
                            break
                    if not negated_quote and (
                        "proibo" in u["norm"]
                        or "proibida" in u["norm"]
                        or "evitando solicitar" in u["norm"]
                        or "nao ha indicacao" in u["norm"]
                        or "contraindic" in u["norm"]
                    ):
                        negated_quote = u["text"]
                        break

            if violated or not negated_quote:
                judged_items.append({
                    "id": item_id,
                    "status": "NONE",
                    "evidence_quote": "",
                    "rationale": "Conduta contraindicada executada ou não verbalizada." if violated else "Critério não contemplado.",
                })
            else:
                judged_items.append({
                    "id": item_id,
                    "status": "FULL",
                    "evidence_quote": negated_quote,
                    "rationale": "Candidato afastou explicitamente a conduta iatrogênica.",
                })
            continue

        # Caso especial: REVALIDA-2023-GO-PEP item_1 (acolhimento/sigilo sem exigir BO)
        if station_code == "REVALIDA-2023-GO-PEP" and item_id == "item_1":
            demands_bo = any(
                _has_affirmative_mention(
                    u["norm"], "", ["exigir boletim", "exijo boletim", "exijo o boletim", "condicao para realizar"]
                )
                for u in units
            )
            if demands_bo:
                judged_items.append({
                    "id": item_id,
                    "status": "NONE",
                    "evidence_quote": "",
                    "rationale": "Exigiu boletim de ocorrência indevidamente.",
                })
                continue

        concepts = _item_concept_terms(item)
        matched_units: list[tuple[str, int]] = []

        for u in units:
            unit_hits = 0
            for term in concepts:
                for m in _find_term_matches(u["norm"], term):
                    if u["source"] != "speech" or not _sentence_is_negated_at_match(u["norm"], m.start()):
                        unit_hits += 1
                        break
            if unit_hits > 0:
                matched_units.append((u["text"], unit_hits))

        if not matched_units:
            judged_items.append({
                "id": item_id,
                "status": "NONE",
                "evidence_quote": "",
                "rationale": "Critério ausente ou explicitamente negado pelo candidato.",
            })
        else:
            best_quote, best_hits = max(matched_units, key=lambda x: x[1])
            total_hits = sum(h for _, h in matched_units)
            status = "FULL" if (total_hits >= 1 and (best_hits >= 1 or len(matched_units) >= 1)) else "PARTIAL"
            judged_items.append({
                "id": item_id,
                "status": status,
                "evidence_quote": best_quote,
                "rationale": "Conduta ou conceito clínico contemplado com citação literal.",
            })

    # Erros críticos também extraídos com citação literal quando presentes
    spoken_joined = " ".join(u["text"] for u in units if u["source"] == "speech")
    prescribed_joined = " ".join(u["text"] for u in units if u["source"] != "speech")
    crit_triggered: list[dict[str, str]] = []
    if critical_errors:
        from api.osce_evaluation import evaluate_critical_safety_violations

        violated = evaluate_critical_safety_violations(
            critical_errors=critical_errors,
            evidence_text=spoken_joined,
            actions=[],
            station_meta=station_meta,
        )
        if not violated and prescribed_joined:
            violated = evaluate_critical_safety_violations(
                critical_errors=critical_errors,
                evidence_text=f"{spoken_joined} {prescribed_joined}",
                actions=[],
                station_meta=station_meta,
            )
        for err in violated:
            crit_triggered.append({
                "error": err,
                "evidence_quote": units[0]["text"] if units else "",
                "rationale": "Violação de segurança identificada na conduta do candidato.",
            })

    return json.dumps(
        {"items": judged_items, "critical_errors_triggered": crit_triggered},
        ensure_ascii=False,
    )


