-- Migration 026: Remove novamente os índices legados que eram recriados por _create_indexes no boot
DROP INDEX IF EXISTS idx_attempts_user_question;
DROP INDEX IF EXISTS idx_attempts_user_question_latest;
DROP INDEX IF EXISTS idx_attempts_correct;
DROP INDEX IF EXISTS idx_attempts_user_answered_at;
DROP INDEX IF EXISTS idx_spaced_repetition_review;
DROP INDEX IF EXISTS idx_alternatives_question_id;
DROP INDEX IF EXISTS idx_questions_area;
DROP INDEX IF EXISTS idx_questions_institution;
DROP INDEX IF EXISTS idx_questions_missing_alts;
