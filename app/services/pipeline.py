import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.scoring import compute_match_score
from app.llm.client import LLMClient, LLMTransientError
from app.llm.prompts import PROMPT_VERSION, SCHEMA_VERSION
from app.models import Analysis, Candidate, Job, LLMExecution
from app.schemas import AnalysisStatus, MustHave, ValidatedExtraction
from app.services.extraction import AttemptRecord, run_extraction
from app.utils import utcnow

log = logging.getLogger("talentmatch.pipeline")

TERMINAL = (AnalysisStatus.SUCCEEDED, AnalysisStatus.FAILED)
_ERROR_MESSAGES = {
    "INPUT_UNAVAILABLE": "Vaga ou candidato indisponível (removido ou expirado).",
    "LLM_VALIDATION_FAILED": "A LLM não produziu saída válida dentro do limite de tentativas.",
    "LLM_PERMANENT_ERROR": "Erro permanente no provedor de LLM.",
    "LLM_UNAVAILABLE": "Provedor de LLM indisponível após novas tentativas.",
    "TASK_FAILED": "Falha inesperada ao processar a análise.",
    "QUEUE_UNAVAILABLE": "Fila indisponível no momento do envio.",
}


def mark_failed(session: Session, analysis_id: str, code: str, message: str | None = None) -> None:
    analysis = session.get(Analysis, analysis_id)
    if analysis is None or analysis.status in TERMINAL:
        return
    analysis.status = AnalysisStatus.FAILED
    analysis.error_code = code
    analysis.error_message = (message or _ERROR_MESSAGES.get(code, code))[:300]
    analysis.finished_at = utcnow()
    session.commit()
    log.warning("analysis_failed trace_id=%s code=%s", analysis.trace_id, code)


def _build_result(
    analysis: Analysis,
    job: Job,
    candidate: Candidate,
    must_have: list[MustHave],
    validated: ValidatedExtraction,
    executions: list[LLMExecution],
    settings: Settings,
) -> dict[str, Any]:
    prompt_tokens = sum(e.prompt_tokens for e in executions)
    completion_tokens = sum(e.completion_tokens for e in executions)
    model = next((e.model for e in reversed(executions) if e.model), settings.llm_model)
    return {
        "trace_id": analysis.trace_id,
        "model_version": model,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "execution_metrics": {
            "latency_ms": sum(e.latency_ms for e in executions),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "attempts": len(executions),
        },
        "match_analysis": {
            "candidate_id": candidate.id,
            "job_id": job.id,
            "match_score": compute_match_score(must_have, validated.checklist),
            "extraction_confidence": validated.extraction_confidence,
            "must_have_checklist": validated.checklist,
            "evidence": validated.evidence,
            "strengths": validated.strengths,
            "gaps": validated.gaps,
            "justification": validated.justification,
            "review_required": True,  # LGPD art. 20: nenhuma decisão é 100% automatizada
        },
    }


def process_analysis(session: Session, analysis_id: str, client: LLMClient, settings: Settings) -> None:
    analysis = session.get(Analysis, analysis_id)
    if analysis is None or analysis.status in TERMINAL:
        return  # idempotente: reentrega do Celery não reprocessa

    analysis.status = AnalysisStatus.PROCESSING
    session.commit()

    job = session.get(Job, analysis.job_id)
    candidate = session.get(Candidate, analysis.candidate_id) if analysis.candidate_id else None
    if job is None or candidate is None:
        mark_failed(session, analysis_id, "INPUT_UNAVAILABLE")
        return

    must_have = [MustHave(**m) for m in job.must_have]
    sequence = session.scalar(
        select(func.count()).select_from(LLMExecution).where(LLMExecution.analysis_id == analysis_id)
    ) or 0

    def record(rec: AttemptRecord) -> None:
        nonlocal sequence
        sequence += 1
        session.add(
            LLMExecution(
                trace_id=analysis.trace_id,
                analysis_id=analysis_id,
                attempt=sequence,
                outcome=rec.outcome,
                model=rec.model,
                system_fingerprint=rec.system_fingerprint,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                temperature=settings.llm_temperature,
                seed=settings.llm_seed,
                prompt_tokens=rec.prompt_tokens,
                completion_tokens=rec.completion_tokens,
                latency_ms=rec.latency_ms,
                input_sha256=rec.input_sha256,
                output_sha256=rec.output_sha256,
                error_detail=rec.error_detail,
            )
        )
        session.commit()

    try:
        run = run_extraction(
            client=client,
            title=job.title,
            description=job.description,
            must_have=must_have,
            cv_text=candidate.redacted_text,
            max_attempts=settings.llm_max_attempts,
            on_attempt=record,
        )
    except LLMTransientError:
        analysis.status = AnalysisStatus.PENDING  # volta para a fila; Celery faz o retry
        session.commit()
        raise

    if run.validated is None:
        mark_failed(session, analysis_id, run.error_code or "TASK_FAILED")
        return

    executions = list(
        session.scalars(
            select(LLMExecution).where(LLMExecution.analysis_id == analysis_id).order_by(LLMExecution.attempt)
        )
    )
    analysis.result = _build_result(analysis, job, candidate, must_have, run.validated, executions, settings)
    analysis.status = AnalysisStatus.SUCCEEDED
    analysis.finished_at = utcnow()
    session.commit()
    log.info(
        "analysis_done trace_id=%s attempts=%d tokens=%d",
        analysis.trace_id,
        len(executions),
        analysis.result["execution_metrics"]["total_tokens"],
    )
