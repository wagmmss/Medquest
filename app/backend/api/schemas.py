"""Validação de entrada com Pydantic."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator, field_validator

__all__ = [
    "AttemptIn",
    "BatchAttemptIn",
    "BatchAttemptItem",
    "CronDispatchIn",
    "CurriculumEntryIn",
    "DayOverrideIn",
    "FavoriteIn",
    "GeneratePlanIn",
    "InternatoBlockIn",
    "InternatoBlocksUpdateIn",
    "MarchaIn",
    "MilestoneIn",
    "MilestonePatchIn",
    "NotificationConfigIn",
    "PlannerConfigIn",
    "PlannerRevisionIn",
    "PlannerStudyIn",
    "PushSubscriptionIn",
    "PushSubscriptionKeys",
    "PushUnsubscribeIn",
    "QuestionBatchIn",
    "ReviewIn",
    "ShiftItemIn",
    "ShiftsBatchIn",
    "SimuladoCustomIn",
    "SimuladoSessionIn",
    "SixYearPlanPatchIn",
    "ValidationError",
    "validation_errors",
]


def _validate_iso_date_str(val: str) -> str:
    try:
        parsed = date.fromisoformat(val)
    except (ValueError, TypeError) as exc:
        raise ValueError("must be a valid YYYY-MM-DD calendar date") from exc
    if parsed.isoformat() != val:
        raise ValueError("must be formatted as YYYY-MM-DD")
    return val


class APIInput(BaseModel):
    """Base for request bodies: reject unknown fields instead of ignoring them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validation_errors(error: ValidationError) -> list[dict]:
    """Return Pydantic diagnostics that Flask can safely JSON-encode."""

    return error.errors(include_url=False, include_context=False)


class AttemptIn(APIInput):
    selected_letter: str = Field(default="A", pattern=r"^(?:[A-Ea-e]|DISCURSIVA|D)?$")
    time_spent_ms: int | None = Field(default=None, ge=0)
    confidence: Literal["chutei", "duvida", "certeza", "defer"] | None = None
    is_correct: bool | None = None
    user_answer_text: str | None = Field(default=None, max_length=10000)
    twin_for_question_id: int | None = None
    answered_at: str | None = Field(default=None, max_length=64)
    assisted: bool = False


class BatchAttemptItem(APIInput):
    question_id: int = Field(gt=0)
    selected_letter: str = Field(default="A", pattern=r"^(?:[A-Ea-e]|DISCURSIVA|D)?$")
    time_spent_ms: int | None = Field(default=None, ge=0)
    confidence: Literal["chutei", "duvida", "certeza", "defer"] | None = None
    is_correct: bool | None = None
    user_answer_text: str | None = Field(default=None, max_length=10000)
    twin_for_question_id: int | None = None
    answered_at: str | None = Field(default=None, max_length=64)
    assisted: bool = False


class BatchAttemptIn(APIInput):
    attempts: list[BatchAttemptItem] = Field(max_length=500)


class ReviewIn(APIInput):
    confidence: Literal["chutei", "duvida", "certeza"]
    is_correct: bool | None = None
    twin_for_question_id: int | None = None
    attempt_id: int | None = None
    assisted: bool | None = None


WeekPatternMode = Literal["integral", "meio_periodo", "folga"]
WeekdayKey = Literal["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


class InternatoBlockIn(APIInput):
    id: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,40}$")
    start: str = Field(min_length=10, max_length=10)
    end: str = Field(min_length=10, max_length=10)
    area: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=100)
    hours_per_week: float | None = Field(default=None, ge=1, le=168)
    ancora70: str | None = Field(default=None, max_length=500)
    trilha30: str | None = Field(default=None, max_length=500)
    ancora_areas: list[str] | None = Field(default=None, max_length=10)
    procedimentos_alvo: list[str] | None = Field(default=None, max_length=20)
    micro_habito: str | None = Field(default=None, max_length=300)
    week_pattern: dict[WeekdayKey, WeekPatternMode] | None = None

    @field_validator("start", "end")
    @classmethod
    def validate_dates(cls, v: str) -> str:
        return _validate_iso_date_str(v)

    @model_validator(mode="after")
    def validate_date_order(self):
        if self.start > self.end:
            raise ValueError("start must be <= end")
        return self


class PlannerConfigIn(APIInput):
    exam_date: str | None = None
    start_date: str | None = None
    days_per_week: int = Field(default=6, ge=1, le=7)
    hours_per_day: int = Field(default=4, ge=1, le=24)
    target_score: float | None = Field(default=None, ge=0, le=100)
    target_institution: str | None = Field(default=None, max_length=500)
    target_institutions: list[str] | None = Field(default=None, max_length=50)
    primary_institution: str | None = Field(default=None, max_length=100)
    target_specialty: str | None = Field(default=None, max_length=100)
    organization_mode: Literal["geral", "internato"] | None = None
    internato_blocks: list[InternatoBlockIn] | None = None


class InternatoBlocksUpdateIn(APIInput):
    blocks: list[InternatoBlockIn] = Field(default_factory=list, max_length=50)


class PlannerResetIn(APIInput):
    scope: Literal["schedule", "progress", "all"] = "all"
    mode: Literal[
        "standard",
        "intensive",
        "geral_standard",
        "geral_intensive",
        "internato_standard",
        "internato_intensive",
    ] | None = None



class PlannerStudyIn(APIInput):
    studied: bool = False


class PlannerTopicProgressIn(APIInput):
    subtema: str = Field(min_length=1, max_length=500)
    completed: bool = False


class PlannerMoveTopicIn(APIInput):
    subtema: str = Field(min_length=1, max_length=500)
    source_week: int = Field(ge=1, le=260)
    target_week: int = Field(ge=1, le=260)
    target_index: int | None = Field(default=None, ge=0)
    mode: Literal[
        "standard",
        "intensive",
        "geral_standard",
        "geral_intensive",
        "internato_standard",
        "internato_intensive",
    ] = "geral_standard"


class PlannerRevisionIn(APIInput):
    type: Literal["rev24h", "rev7d", "rev30d"]
    checked: bool = False


class GeneratePlanIn(APIInput):
    exam_date: str
    start_date: str | None = None
    hours_per_week: int = Field(default=20, ge=1, le=168)
    intensive: bool = False
    organization: Literal["geral", "internato"] = "geral"
    regenerate: bool = False


class SimuladoCustomIn(APIInput):
    institutions: list[str] = Field(default_factory=list, max_length=20)
    years: list[str] = Field(default_factory=list, max_length=20)
    questions_per_area: int = Field(default=20, ge=1, le=100)
    # These options are consumed by the frontend after the question IDs are selected.
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    force_4_options: bool = False


class SimuladoSessionIn(APIInput):
    client_session_id: str = Field(min_length=8, max_length=100)
    planned_duration_seconds: int = Field(ge=1, le=24 * 60 * 60)
    elapsed_seconds: int = Field(ge=0, le=24 * 60 * 60)
    total_questions: int = Field(ge=1, le=500)
    answered_count: int = Field(ge=0, le=500)
    correct_count: int = Field(ge=0, le=500)
    filters: dict = Field(default_factory=dict)
    area_results: list[dict] = Field(default_factory=list, max_length=20)


class QuestionBatchIn(APIInput):
    ids: list[int] = Field(min_length=1, max_length=200)
    force_4_options: bool = False

    @model_validator(mode="after")
    def validate_ids(self):
        if any(question_id <= 0 for question_id in self.ids):
            raise ValueError("ids must contain positive integers")
        # Preserve caller order while avoiding repeated database and response work.
        self.ids = list(dict.fromkeys(self.ids))
        return self


class FavoriteIn(APIInput):
    is_favorite: bool | None = None


class NotificationConfigIn(APIInput):
    enabled: bool = False
    preferred_hour: int = Field(default=8, ge=0, le=23)
    days_of_week: list[int] = Field(default=[0, 1, 2, 3, 4, 5, 6], max_length=7)
    max_daily_reminders: Literal[1] = 1


    @model_validator(mode="after")
    def validate_days(self):
        for day in self.days_of_week:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValueError("days_of_week must contain integers from 0 to 6")
        return self


class PushSubscriptionKeys(APIInput):
    p256dh: str = Field(min_length=1, max_length=500)
    auth: str = Field(min_length=1, max_length=500)


class PushSubscriptionIn(APIInput):
    endpoint: str = Field(min_length=10, max_length=2000, pattern=r"^https://.*")
    keys: PushSubscriptionKeys
    expiration_time: int | None = None


class PushUnsubscribeIn(APIInput):
    endpoint: str | None = Field(default=None, max_length=2000)


class CronDispatchIn(APIInput):
    force_user_id: str | None = Field(default=None, max_length=100)
    ignore_hour: bool = False


class SixYearPlanPatchIn(APIInput):
    routine_mode_enabled: bool | None = None
    enamed_concept: Literal[3, 4, 5] | None = None
    foco_override: dict[str, dict[Literal["ancora70", "trilha30"], str | None]] | None = None
    ritual_done: dict[str, dict[str, bool]] | None = None


class ShiftItemIn(APIInput):
    date_iso: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: Literal["plantao_12h_dia", "plantao_noturno", "plantao_24h"]
    note: str = Field(default="", max_length=200)

    @field_validator("date_iso")
    @classmethod
    def validate_date_iso(cls, v: str) -> str:
        return _validate_iso_date_str(v)


class ShiftsBatchIn(APIInput):
    add: list[ShiftItemIn] = Field(default_factory=list, max_length=200)
    remove: list[ShiftItemIn] = Field(default_factory=list, max_length=200)


class DayOverrideIn(APIInput):
    mode: Literal["pos_plantao", "folga", "meio_periodo", "integral"]


class MarchaIn(APIInput):
    marcha_id: Literal["4_sprint", "3_normal", "2_pesada", "1_sobrevivencia"] | None = None


class CurriculumEntryIn(APIInput):
    value: float = Field(ge=0, le=1000)
    proof_status: Literal["falta", "em_andamento", "pdf_pronto"]
    note: str = Field(default="", max_length=2000)


class MilestoneIn(APIInput):
    id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    titulo: str = Field(min_length=1, max_length=200)
    data_iso: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    categoria: Literal["curriculo", "estudo", "graduacao", "prova", "ingresso"] = "prova"
    done: bool = False
    note: str = Field(default="", max_length=2000)

    @field_validator("data_iso")
    @classmethod
    def validate_data_iso(cls, v: str) -> str:
        return _validate_iso_date_str(v)


class MilestonePatchIn(APIInput):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    data_iso: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    categoria: Literal["curriculo", "estudo", "graduacao", "prova", "ingresso"] | None = None
    done: bool | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("data_iso")
    @classmethod
    def validate_data_iso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_iso_date_str(v)
