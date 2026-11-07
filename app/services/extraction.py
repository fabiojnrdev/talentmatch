"""Loop de extração com autocorreção (self-correction). Independe de banco e de Celery."""
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.domain.validation import ExtractionInvalid, validate_extraction
from app.llm.client import LLMClient, LLMPermanentError, LLMTransientError
from app.llm.prompts import CORRECTION_TEMPLATE, build_messages
from app.schemas import ExtractionWire, MustHave, ValidatedExtraction


@dataclass
class AttemptRecord:
    outcome: str  # ok | validation_error | api_error
    model: str = ""
    system_fingerprint: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    input_sha256: str | None = None
    output_sha256: str | None = None
    error_detail: str | None = None


@dataclass
class ExtractionRun:
    validated: ValidatedExtraction | None
    attempts: list[AttemptRecord] = field(default_factory=list)
    error_code: str | None = None


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strip_fences(raw: str) -> str:
    """Alguns modelos (sobretudo gratuitos) embrulham o JSON em ```json ... ```."""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())


def _describe(exc: ValidationError | ExtractionInvalid) -> list[str]:
    if isinstance(exc, ExtractionInvalid):
        return exc.errors
    # Só loc + msg: o 'input' do Pydantic pode ecoar conteúdo.
    return [f"{'.'.join(str(p) for p in e['loc']) or 'json'}: {e['msg']}" for e in exc.errors()]


def run_extraction(
    *,
    client: LLMClient,
    title: str,
    description: str | None,
    must_have: Sequence[MustHave],
    cv_text: str,
    max_attempts: int,
    on_attempt: Callable[[AttemptRecord], None] | None = None,
) -> ExtractionRun:
    messages = build_messages(title, description, must_have, cv_text)
    expected = [m.key for m in must_have]
    run = ExtractionRun(validated=None)
    failures = 0

    def emit(record: AttemptRecord) -> None:
        run.attempts.append(record)
        if on_attempt:
            on_attempt(record)

    while True:
        input_hash = _sha(json.dumps(messages, ensure_ascii=False, sort_keys=True))
        try:
            call = client.extract(messages)
        except LLMTransientError as exc:
            emit(AttemptRecord("api_error", input_sha256=input_hash, error_detail=str(exc)[:200]))
            raise
        except LLMPermanentError as exc:
            emit(AttemptRecord("api_error", input_sha256=input_hash, error_detail=str(exc)[:200]))
            run.error_code = "LLM_PERMANENT_ERROR"
            return run

        base = dict(
            model=call.model,
            system_fingerprint=call.system_fingerprint,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            latency_ms=call.latency_ms,
            input_sha256=input_hash,
            output_sha256=_sha(call.raw_content),
        )
        try:
            if call.finish_reason == "length":
                raise ExtractionInvalid(["resposta truncada; seja mais conciso"])
            wire = ExtractionWire.model_validate_json(_strip_fences(call.raw_content))
            validated = validate_extraction(wire, expected, cv_text)
        except (ValidationError, ExtractionInvalid) as exc:
            errors = _describe(exc)
            emit(AttemptRecord("validation_error", error_detail="; ".join(errors)[:500], **base))
            failures += 1
            if failures >= max_attempts:
                run.error_code = "LLM_VALIDATION_FAILED"
                return run
            messages = messages + [
                {"role": "assistant", "content": call.raw_content},
                {"role": "user", "content": CORRECTION_TEMPLATE.format(errors="\n".join(f"- {e}" for e in errors))},
            ]
            continue

        emit(AttemptRecord("ok", **base))
        run.validated = validated
        return run
