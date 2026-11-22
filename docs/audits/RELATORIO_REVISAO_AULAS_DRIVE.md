# Relatório Técnico de Arquitetura & Auditoria — Videoteca do Google Drive no MedQuest

> **Objetivo deste documento**: fornecer contexto técnico completo, autocontido e auditável para revisão crítica independente no **ChatGPT** e no **Claude**, buscando falhas de segurança, bugs sutis, gargalos de performance e oportunidades de simplificação/otimização antes do deploy em produção (`medquest.live`).

---

## 1. Resumo Executivo

- **O que foi entregue**: integração privada de **1.987 videoaulas** hospedadas no Google Drive (`Drive:katomart-backup/courses/`) diretamente dentro do MedQuest, ancoradas nos **170 subtemas canônicos** do edital (`plannerData.json`).
- **Cursos integrados**:
  1. `medway_r1_2026` (**Extensivo R1 Medway** — principal, `is_extra = 0`): **790** vídeos (`312` aulas principais essenciais, `309` Flash, `147` Revisão rápida, `22` Como cai), **790/790** mapeados a **161/170** subtemas canônicos.
  2. `medcof_r1_2026` (**MedCof R1 Extras**, `is_extra = 1`): **1.033** vídeos clínicos (`513` `cofexpress` + `520` `aula_extra` completa; `18` vídeos de onboarding/plataforma filtrados como inativos), **863/1.033 (83,5%)** mapeados a **152/170** subtemas canônicos.
  3. `radiologia_2026` (**Imagens Radiológicas 2026**, `is_extra = 1`): **29** vídeos (`29/29` com duração real).
  4. `medway_pratica_2026` (**CRMedway Prática 2026**, `is_extra = 1`): **135** vídeos únicos deduplicados (`135/135` com duração real).
- **Cobertura global**: **170/170 subtemas canônicos** possuem pelo menos 1 aula vinculada; **100% das 1.987 aulas ativas** possuem `duration_seconds` real extraído via Google Drive API v3 (`videoMediaMetadata.durationMillis`).
- **Estado atual**: implementado e validado localmente (`app/backend/medquest.db`); **ainda não enviado para produção (Turso Cloud / Render / Vercel)**.

---

## 2. Arquitetura Ponta a Ponta

```
Google Drive (katomart-backup/courses)
   ├── rclone lsjson --fast-list        (ID, Path, Size sem baixar vídeo)
   └── Drive API v3 files.list          (videoMediaMetadata.durationMillis)
            │
            ▼
scripts/sync_drive_lessons.py           (normalização, overrides, deduplicação, UPSERT idempotente)
            │
            ▼
SQLite Local (app/backend/medquest.db) ──► app/backend/scripts/sync_db_turso.py ──► Turso Cloud
            │
            ▼
Flask Blueprint (app/backend/api/lessons.py)
   ├── @require_lessons_access (app/backend/api/auth.py) -> apenas moraes.wagg@gmail.com
   ├── GET  /api/lessons
   ├── GET  /api/lessons/summary-by-subtema
   ├── GET  /api/lessons/by-subtema
   ├── GET  /api/lessons/continue
   ├── GET  /api/lessons/current-week
   ├── GET  /api/lessons/<id>
   ├── PUT  /api/lessons/<id>/progress  (sincroniza theme_progress.theory_completed=1)
   └── PATCH /api/lessons/<id>/mapping
            │
            ▼
Next.js Proxy (/api/[...path]/route.ts) -> injeta Bearer JWT (Clerk) + X-User-Email + X-Internal-Proxy-Token
            │
            ▼
Frontend React 19 / Next.js 16 (App Router)
   ├── useLessonsAccess() (via GET /api/auth/me -> can_access_lessons)
   ├── Navegação condicional (Sidebar, TopNav, BottomNav, CommandPalette)
   ├── /aulas (LessonsClient.tsx): Player iframe Drive /preview + Modo Teatro + filtros em memória
   ├── / (DashboardClient.tsx): Card "Continuar assistindo"
   ├── /planner (PlannerClient.tsx): "Assistir aulas (x/y • tempo)" + badge "Teoria ✓"
   └── /analise (ThemeDetailDrawer.tsx): Lista de aulas do subtema + "Extras MedCof"
```

---

## 3. Modelo de Dados (`022_lessons.sql`)

Arquivo: `app/backend/migrations/022_lessons.sql`

```sql
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_key TEXT NOT NULL,
    course_name TEXT NOT NULL,
    is_extra INTEGER NOT NULL DEFAULT 0 CHECK (is_extra IN (0, 1)),
    area TEXT NOT NULL DEFAULT 'Extras',
    specialty TEXT NOT NULL DEFAULT '',
    subtema TEXT,
    module_name TEXT NOT NULL,
    module_order INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    lesson_order INTEGER NOT NULL DEFAULT 0,
    lesson_kind TEXT NOT NULL DEFAULT 'aula',
    is_essential INTEGER NOT NULL DEFAULT 1 CHECK (is_essential IN (0, 1)),
    media_type TEXT NOT NULL DEFAULT 'video',
    provider TEXT NOT NULL DEFAULT 'gdrive',
    drive_file_id TEXT NOT NULL UNIQUE,
    drive_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    duration_seconds INTEGER,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id TEXT NOT NULL,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started', 'in_progress', 'completed')),
    bookmark_seconds INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, lesson_id)
);
```

- **Chave estável de sincronização**: `drive_file_id` (`UNIQUE`). Re-sincronizações fazem `ON CONFLICT(drive_file_id) DO UPDATE`, preservando `lessons.id` e mantendo intactos todos os registros de `lesson_progress`.
- **Remoção lógica (`active = 0`)**: vídeos removidos no Drive ou filtrados (como os 18 de onboarding do MedCof) são marcados com `active = 0` em vez de `DELETE`, evitando perda acidental de anotações históricas.

---

## 4. Segurança e Controle de Acesso

- **Regra definida**: acesso restrito exclusivamente ao e-mail `moraes.wagg@gmail.com` (configurável via variável de ambiente `LESSONS_ALLOWED_EMAILS`, com fallback seguro `DEFAULT_LESSONS_ALLOWED_EMAILS = frozenset({"moraes.wagg@gmail.com"})`).
- **Implementação em `app/backend/api/auth.py`**:
  - `can_access_lessons_request()` rejeita sempre `user_id.startswith("guest:")` (mesmo que haja tentativa de injeção de `X-User-Email`) e exige `user_email` autenticado presente em `configured_lessons_allowed_emails()`.
  - `@require_lessons_access` encapsula `@require_auth` e retorna `403 Forbidden` para qualquer visitante ou outro usuário autenticado.
  - `GET /api/auth/me` expõe o booleano `can_access_lessons`.
- **Implementação no proxy Next.js (`app/frontend/src/app/api/[...path]/route.ts`, código existente)**:
  - Remove cabeçalhos spoofáveis do navegador (`authorization`, `x-guest-id`, `x-internal-proxy-token`, `x-user-email`) e injeta `X-User-Email` apenas a partir do usuário verificado no Clerk (`getServerCurrentUser()`), junto com `Authorization: Bearer <jwt>` e `X-Internal-Proxy-Token`.
- **Importante — Atenção na revisão**: no Flask (`auth.py` linhas 95–100 e 141–145), `g.user_email` confia no header `X-User-Email` quando `X-Internal-Proxy-Token == FLASK_API_PROXY_SECRET` (caso o JWT do Clerk não traga a claim `email`). Caso o Render exponha a URL do Flask diretamente na internet (`medquest-188y.onrender.com`), a segurança depende de `FLASK_API_PROXY_SECRET` ser secreto e não vazar, e de o JWT do Clerk ser validado com `RS256` + `JWKS_URL`. **Ponto explícito para revisão no ChatGPT/Claude**.

---

## 5. Inventário de Arquivos Criados e Alterados

### Backend & Scripts
- `app/backend/migrations/022_lessons.sql` *(novo)* — Schema `lessons`, `lesson_progress` e índices.
- `app/backend/api/auth.py` *(editado)* — `configured_lessons_allowed_emails`, `can_access_lessons_request`, `@require_lessons_access`, `can_access_lessons` em `/auth/me`.
- `app/backend/api/lessons.py` *(novo)* — Blueprint completo de videoteca, progresso, `continue`, `current-week` e sincronização com `theme_progress`.
- `app/backend/api/__init__.py` *(editado)* — Registro de `lessons_bp` em `/api` e `/api/v1`.
- `app/backend/data/lessons_mapping_overrides.json` *(novo)* — ~280 regras explícitas de mapeamento Medway/MedCof para os 170 subtemas canônicos.
- `scripts/sync_drive_lessons.py` *(novo)* — Sincronizador idempotente via `rclone` + Drive API v3 + limpeza de ruído + classificação `cofexpress` vs `aula_extra` + deduplicação.
- `app/backend/scripts/sync_db_turso.py` *(editado)* — Bloco `# 6` criando `lessons` + `lesson_progress` no Turso e fazendo upsert em lotes de 150 aulas.
- `app/backend/tests/test_lessons.py` *(novo)* — Testes de isolamento (guest/outro e-mail/dono), filtros, progresso, `continue`, `current-week`, schema legado e `PATCH /mapping`.
- `.env.example` *(editado)* — Adicionada chave `LESSONS_ALLOWED_EMAILS=`.

### Frontend
- `app/frontend/src/types/api.ts` *(editado)* — Tipos `LessonItem`, `LessonsListResponse`, `ContinueLessonResponse`, `CurrentWeekLessonsResponse`, etc.
- `app/frontend/src/lib/api.ts` *(editado)* — Namespace `api.lessons.*`.
- `app/frontend/src/hooks/useLessonsAccess.ts` *(novo)* — Hook React Query consultando `/api/auth/me`.
- `app/frontend/src/lib/navigation.ts` e `app/frontend/src/components/ui/ClinicalIcon.tsx` *(editados)* — Item condicional `/aulas` (`requiresLessonsAccess: true`) e ícone `play_circle`.
- `app/frontend/src/components/Sidebar.tsx`, `TopNav.tsx`, `BottomNav.tsx`, `CommandPalette.tsx` *(editados)* — Ocultam `/aulas` quando `canAccessLessons === false`.
- `app/frontend/src/app/aulas/page.tsx` e `app/frontend/src/app/aulas/LessonsClient.tsx` *(novos)* — Videoteca completa (5 abas, busca/filtros em memória, player iframe `/preview`, Modo Teatro atalho `T`, bookmark `mm:ss`, anotações, `Concluir e próxima`, agrupamento `Por Área/Tema` vs `Por Bloco` no MedCof, filtro `Semana X (Planner)`, ponte para `/estudar`).
- `app/frontend/src/app/DashboardClient.tsx` *(editado)* — Card compacto **"Continuar assistindo"**.
- `app/frontend/src/app/planner/PlannerClient.tsx` *(editado)* — Botão `Assistir aulas (x/y • tempo restante)` + badge `Teoria ✓`.
- `app/frontend/src/app/analise/components/ThemeDetailDrawer.tsx` *(editado)* — Lista de aulas do subtema + seção recolhível `Extras MedCof`.

---

## 6. Bugs Encontrados e Corrigidos na Auditoria Interna

1. **HTTP 500 em `/api/lessons/continue` e `/api/lessons/current-week` no `medquest.db` real**:
   - `_get_current_planner_week_subtemas` selecionava `organization_mode` diretamente da tabela `planner_config`, mas o `medquest.db` local não possuía essa coluna. Corrigido para `SELECT *` + checagem de colunas e fallback seguro.
2. **Duplicação 2× em `CRMedway Prática 2026`**:
   - No Drive, cada aula existia tanto em `lessons/0_video-aula/1. Aula.mp4` quanto em `lessons/0_video-aula/videos/1. Aula.mp4`. Deduplicado preferindo o caminho sem `/videos/` e chave `(module_name, title, size_bytes)` — caiu de `270` para `135` aulas únicas.
3. **Falsos positivos no matcher automático do MedCof**:
   - Tokens genéricos `"colo"` e `"choque"` em `MEDICAL_SYNONYMS` estavam levando *"Colo Curto e Incompetência Istmocervical"* para *Câncer de Colo Uterino* e *"Choque no Trauma"* para *Sepse no Adulto*. Removidos do dicionário de sinônimos e mapeados explicitamente via overrides.
4. **Tempestade de payloads na busca do `/aulas`**:
   - Anteriormente, `searchText`, `areaFilter`, `statusFilter` e `essentialOnly` estavam na `queryKey` e disparavam novas requisições de ~930 KB a ~2 MB a cada tecla digitada. Movidos para filtragem client-side via `useMemo` (0 ms de latência, mantendo apenas `effectiveCourse` e `paramSubtema` no fetch).

---

## 7. Validações Já Executadas (após última edição)

- **`scripts/sync_drive_lessons.py`**: rodado contra `app/backend/medquest.db` com sucesso:
  - `medway_r1_2026`: `790` vídeos (`790` c/ duração, `790` mapeados, `161/170` subtemas)
  - `medcof_r1_2026`: `1033` vídeos (`1033` c/ duração, `863` mapeados, `152/170` subtemas; `513` cofexpress, `520` aula_extra; `18` onboarding desativados)
  - `radiologia_2026`: `29` vídeos (`29` c/ duração)
  - `medway_pratica_2026`: `135` vídeos (`135` c/ duração)
  - Cobertura total: **170/170 subtemas canônicos**.
- **Teste direto dos 6 endpoints reais contra `app/backend/medquest.db`**:
  - `GET /api/lessons` -> `200` (`2.014.331` bytes, `29.67ms`)
  - `GET /api/lessons?course=medway_r1_2026` -> `200` (`936.305` bytes, `12.93ms`)
  - `GET /api/lessons?course=medcof_r1_2026` -> `200` (`926.002` bytes, `12.53ms`)
  - `GET /api/lessons/summary-by-subtema` -> `200` (`49.083` bytes, `4.37ms`)
  - `GET /api/lessons/continue` -> `200` (`1.330` bytes, `1.92ms`)
  - `GET /api/lessons/current-week` -> `200` (`28` bytes, `0.54ms`)
- **`ruff check --select E,F --ignore E501`**: `All checks passed!` nos arquivos alterados/criados.
- **`pytest`**: `20 passed in 0.88s` (`test_lessons.py`, `test_auth.py`, `test_themes.py`, `test_migrations.py`).
- **Frontend (`npm run lint && npm run build`)**: `eslint` com `0` erros e `next build --webpack` concluído (rota `/aulas`, Service Worker e budgets aprovados).

---

## 8. Pontos Críticos & Riscos para o ChatGPT e o Claude Auditarem

1. **Tamanho de Payload de `GET /api/lessons` (`2.0 MB` em `Todos`, `936 KB` por curso)**:
   - Hoje o endpoint devolve todos os campos (`drive_path`, `size_bytes`, `preview_url`, `open_url`, `notes` até 10 KB por aula) de todas as ~1.987 aulas de uma vez. Em conexões 4G ou no Turso remoto, serializar e trafegar 2 MB (e principalmente `notes` em lista) pode pesar.
   - *Pergunta para revisão*: vale enxugar o payload de listagem (`preview_url` e `open_url` deriváveis no frontend a partir de `drive_file_id`, `drive_path` omitido da listagem, `notes` carregado completo só no `GET /api/lessons/<id>` ou substituído por booleano `has_notes`) e adicionar compressão/gzip ou paginação?
2. **Consistência Bidirecional `lesson_progress` ↔ `theme_progress`**:
   - Ao concluir todas as aulas primárias essenciais do subtema, `lessons.py` marca `theme_progress.theory_completed = 1`. Mas se o usuário **desmarcar** uma aula essencial de volta para `not_started`/`in_progress`, `theory_completed` continua `1` (porque o usuário pode ter estudado por apostila).
   - *Pergunta para revisão*: essa assimetria é desejável ou pode confundir o badge `Teoria ✓` no Planner?
3. **Resiliência do Embed do Google Drive (`/preview`)**:
   - Arquivos privados do Google Drive em `<iframe>` exigem que o navegador esteja logado na mesma conta Google (`moraes.wagg@gmail.com`) com cookies de terceiros aceitos para `drive.google.com`. Se o usuário limpar cookies ou abrir em perfil diferente do Chrome, o iframe exibe tela de erro/solicitação de acesso (mitigado pelo botão *"Abrir no Drive"*).
   - Além disso, o `bookmark_seconds` é manual (o iframe cross-origin do Drive não emite `timeupdate`), o que exige disciplina de clicar em *"Salvar ponto e anotações"*.
4. **Cálculo de Semana Atual no Planner (`_get_current_planner_week_subtemas`)**:
   - Usa `datetime.now(timezone.utc).date()` em vez de `America/Sao_Paulo` (note que o repositório já tem `app/backend/api/timezones.py`!). Após as 21h de domingo no Brasil (00h UTC de segunda), a semana do filtro *"Semana X (Planner)"* pode virar 3 horas antes da hora local.
   - Também prioriza sempre `{org}_standard` mesmo que o usuário esteja usando `{org}_intensive` (Reta Final).
5. **Mapeamento Manual de `Radiologia` e `Prática` vs `MedCof`**:
   - Em `Radiologia` (2/29 mapeadas) e `Medway Prática` (5/135 mapeadas), quase tudo ficou com `subtema = NULL` porque o corte de `min_score = 0.72` foi conservador e vários nomes em Radiologia vieram truncados pelo Katomart no nome da pasta (ex: `"01. Introdução ao Domínio de Ima"` — `manifest.json` de Radiologia não foi lido para recuperar os títulos completos, ao contrário do que foi feito em `Medway Prática`!).
6. **Segurança no `sync_db_turso.py` & `auth.py`**:
   - Em `sync_db_turso.py`, apenas linhas locais são enviadas via `UPSERT` (ok), mas se `sync_db_turso.py` for rodado contra produção antes do deploy do código Flask no Render, `022_lessons.sql` já terá sido criada fora da tabela `schema_migrations` do Turso — quando o Render subir e rodar `apply_pending_migrations`, `CREATE TABLE IF NOT EXISTS` e `CREATE INDEX IF NOT EXISTS` são idempotentes (não quebram), mas vale conferir se existe algum risco de lock no Turso ou incompatibilidade de `FOREIGN KEY` em `lesson_progress` no LibSQL.
   - Em `auth.py`, verificar se `X-User-Email` vindo do proxy Next.js pode ser reutilizado caso alguém conheça `FLASK_API_PROXY_SECRET`, e se há necessidade de cabeçalho extra ou validação de `email` direto no JWT do Clerk (Claim customization).
7. **Anomalia já visível nos dados do Drive (higiene de origem)**:
   - Durante a auditoria do banco real, apareceu na pasta `Cirurgia Geral/Afecções Cirúrgicas da Cabeça e Pescoço` um arquivo mal nomeado na origem: `'01. Aula — Cardiopatias Congênitas Cianogênicas e Acianogênicas - Pediatria que versa sobre cardiopatias congênitas'` (erro do próprio backup do Drive/Katomart).
   - E na tabela de `lessons` no `medquest.db`, ficaram títulos truncados em `Imagens Radiológicas 2026` pelos nomes curtos das pastas no Drive.

---

## 9. Prompt Pronto para Colar no ChatGPT e no Claude

Copie e envie o texto abaixo junto com este relatório:

```text
Você é um engenheiro sênior especialista em segurança web, arquitetura Python/Flask + SQLite/LibSQL (Turso) e Next.js/React 19.
Analise o relatório técnico anexo sobre a integração de uma videoteca privada do Google Drive (1.987 aulas) no MedQuest.

Quero uma auditoria crítica, direta e sem elogios gratuitos cobrindo obrigatoriamente:
1. SEGURANÇA: existem brechas para visitantes (`guest:`) ou outros usuários acessarem IDs/links do Google Drive ou progresso? Analise o fluxo Clerk -> Next.js Proxy (`X-Internal-Proxy-Token` + `X-User-Email`) -> Flask (`@require_lessons_access`) e o fallback de testes.
2. INTEGRIDADE DE DADOS & TURSO: há riscos na migration `022_lessons.sql`, no `UPSERT` idempotente por `drive_file_id`, na sincronização via `sync_db_turso.py`, ou na assimetria entre `lesson_progress` e `theme_progress`?
3. PERFORMANCE & ESCALA: o payload de `GET /api/lessons` (~2 MB em "Todos") e o uso de `useMemo` / React Query têm gargalos? O que você cortaria ou mudaria agora com esforço mínimo?
4. BUGS SUTIS DE REGRA DE NEGÓCIO: avalie timezone (`UTC` vs `America/Sao_Paulo` em `current-week`), modo `intensive` vs `standard` no Planner, títulos truncados de Radiologia, comportamento do iframe `/preview` e conflitos de query params em `/aulas`.
5. PLANO DE AÇÃO PRIORIZADO: liste apenas correções de alto impacto prático ordenadas por prioridade (P0, P1, P2), evitando overengineering.
```
