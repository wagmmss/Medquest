-- Migration 025: Remoção de tabela temporária, limpeza de índices redundantes e índices faltantes de alta frequência
DROP TABLE IF EXISTS test;

-- Índices redundantes já cobertos por índices compostos mais abrangentes
DROP INDEX IF EXISTS idx_attempts_user_question;
DROP INDEX IF EXISTS idx_attempts_user_question_latest;
DROP INDEX IF EXISTS idx_attempts_correct;
DROP INDEX IF EXISTS idx_attempts_user_answered_at;
DROP INDEX IF EXISTS idx_spaced_repetition_review;
DROP INDEX IF EXISTS idx_alternatives_question_id;
DROP INDEX IF EXISTS idx_questions_area;
DROP INDEX IF EXISTS idx_questions_institution;
DROP INDEX IF EXISTS idx_questions_missing_alts;

-- Índices faltantes para ordenação de imagens, busca de alternativas e faxina de idempotência
CREATE INDEX IF NOT EXISTS idx_question_images_qid_order ON question_images(question_id, order_index);
CREATE INDEX IF NOT EXISTS idx_alternatives_qid_letter ON alternatives(question_id, letter);
CREATE INDEX IF NOT EXISTS idx_idempotency_status_created ON idempotency_keys(status, created_at);
