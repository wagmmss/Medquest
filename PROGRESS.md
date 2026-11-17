# 🎯 MedQuest - Progresso e Backlog de Engenharia Autônoma

### STATUS: ATIVO

> **Diretrizes de Segurança do Autoloop**:
> 1. Todas as alterações ocorrem na branch `autoloop/dev`. A `main` e a produção (`medquest.live` / Render) estão 100% protegidas.
> 2. Valide cada mudança com `./validate.sh fast` antes de dar a tarefa como concluída.
> 3. Não modifique `app/frontend/src/proxy.ts`, `app/backend/api/db.py` ou credenciais do Clerk.
> 4. Nunca faça alterações automáticas em bancos de produção (Turso Cloud).
> 5. Respeite a calibração do algoritmo FSRS v6 (retenção 0.85 e intervalos com piso D+1).

---

## 🔄 Próxima Tarefa em Andamento

- [ ] **Rastreamento de Acerto Assistido (`assisted`) na Tentativa e FSRS (`app/backend/api/questions.py`, `app/backend/api/srs.py`)**:
    1. **Arquivo/Módulo Alvo**: `app/backend/api/questions.py`, `app/backend/api/schemas.py`, `app/frontend/src/app/estudar/QuizClient.tsx`
    2. **Função/Componente/Seletor**: Endpoint `submit_attempt` / `AttemptPayload` e envio da tentativa após uso de `handleRequestAttendingTip`
    3. **Comportamento Esperado / Critério de Aceite**: Enviar flag `assisted: true` quando a Dica do Preceptor foi aberta antes da resposta, ajustar o rating FSRS (ex.: limitar a `Hard` em acertos assistidos) e expor contagem separada na Análise (`Correto` vs `Correto com ajuda`).

---

## 📋 Backlog Prioritário (Tarefas Cirúrgicas)

1. [ ] **Criação de Sessão por Linguagem Natural (`app/frontend/src/app/estudar/components/QuizFilters.tsx`)**:
    - **Arquivo/Módulo Alvo**: `app/frontend/src/app/estudar/components/QuizFilters.tsx`
    - **Função/Componente/Seletor**: Barra rápida no topo do painel de filtros combináveis
    - **Comportamento Esperado / Critério de Aceite**: Permitir descrever a sessão em linguagem natural (ex.: `"20 questões de Cardiologia da USP-SP não respondidas"`) e mapear para os filtros e limite do bloco em 1 clique.

2. [ ] **Botão "Treinar Agora" por Tema em Cobertura e Foco (`app/frontend/src/app/analise/components/CoverageThemesTab.tsx`)**:
    - **Arquivo/Módulo Alvo**: `app/frontend/src/app/analise/components/CoverageThemesTab.tsx`, `app/frontend/src/app/analise/components/ThemeDetailDrawer.tsx`
    - **Função/Componente/Seletor**: Ação direta nas linhas de subtema e no drawer de detalhe
    - **Comportamento Esperado / Critério de Aceite**: Exibir botão `Treinar (10q)` abrindo `/estudar?subtema=...&limit=10` diretamente a partir do diagnóstico de cobertura.

3. [ ] **Ocultar Estatísticas de Alternativas Antes da Revisão (`app/frontend/src/app/estudar/components/AlternativeList.tsx`)**:
    - **Arquivo/Módulo Alvo**: `app/frontend/src/app/estudar/components/AlternativeList.tsx`
    - **Função/Componente/Seletor**: Toggle discreto para ocultar porcentagens de marcação/dificuldade durante revisões
    - **Comportamento Esperado / Critério de Aceite**: Persistir preferência em `localStorage` para evitar viés cognitivo em questões já respondidas anteriormente.

---

## 💡 Sugestões de Melhorias Futuras (Buffer Recente)

- Benchmark automatizado de carga para endpoints de fila adaptativa e remediação.
- Auditoria de contraste WCAG AAA nos badges de subtemas clínicos.
- Purga seletiva de imagens médicas no Cache Storage (`medquest-image-cache`) em saturação de disco.
- Exportação de caderno de erros em formato offline portátil com gabarito comentado congelado.
- Seção "Últimas sessões e artigos/questões consultadas" com retomada rápida em `/buscar`.

> 💡 Catálogo completo de sugestões arquivado em [docs/SUGESTOES_FUTURAS.md](docs/SUGESTOES_FUTURAS.md)

---

## ✅ Última Tarefa Concluída

- [x] **UI/UX Clinical Calm, Hardening `adaptive.py` e Melhorias AMBOSS (2026-11-17)**: Aplicada linguagem visual Clinical Calm nas páginas principais, corrigida compatibilidade Turbopack em `layout.tsx`, implementado fallback resiliente em `api/adaptive.py`, adicionados treino direto + toggle `Última tentativa` + KPIs de tempo em `/analise`, e `LabValuesModal` + controle `Aa` + Dica do Preceptor pré-resposta (`/dica`) em `/estudar`.

> 📁 Histórico completo arquivado em [CHANGELOG.md](CHANGELOG.md)
