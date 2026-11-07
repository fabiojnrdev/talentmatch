import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_client
from app.config import Settings, get_settings
from app.db import get_session
from app.models import Analysis, Candidate, Job
from app.privacy.pdf import DocumentError, extract_pdf_text
from app.privacy.redaction import redact
from app.queueing import enqueue_analysis
from app.schemas import (
    AnalysisRef,
    AnalysisStatus,
    AnalyzeAccepted,
    CandidateOut,
    ErrorOut,
    LawfulBasis,
    ResultOut,
    ReviewIn,
    ReviewOut,
)
from app.services.audit import audit
from app.services.pipeline import mark_failed
from app.services.retention import delete_candidate_data
from app.utils import new_id, new_uuid, utcnow

log = logging.getLogger("talentmatch.api")
router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])


def _http(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _accepted(analysis: Analysis) -> AnalyzeAccepted:
    return AnalyzeAccepted(
        task_id=analysis.id,
        trace_id=analysis.trace_id,
        candidate_id=analysis.candidate_id,
        status=AnalysisStatus(analysis.status),
    )


def _owned_analysis(session: Session, task_id: str, client: str) -> Analysis:
    analysis = session.get(Analysis, task_id)
    if analysis is None or analysis.created_by != client:
        raise HTTPException(404, "Análise não encontrada.")
    return analysis


def _to_result(analysis: Analysis) -> ResultOut:
    review = None
    if analysis.review_decision:
        review = ReviewOut(
            decision=analysis.review_decision,
            note=analysis.review_note,
            reviewed_by=analysis.reviewed_by or "",
            reviewed_at=analysis.reviewed_at,
        )
    error = (
        ErrorOut(code=analysis.error_code, message=analysis.error_message or "")
        if analysis.error_code
        else None
    )
    return ResultOut(
        task_id=analysis.id,
        trace_id=analysis.trace_id,
        status=AnalysisStatus(analysis.status),
        result=analysis.result,
        error=error,
        human_review=review,
    )


@router.post("/analyze", status_code=202, response_model=AnalyzeAccepted)
def analyze(
    request: Request,
    job_id: str = Form(...),
    lawful_basis: LawfulBasis = Form(...),
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    client: str = Depends(require_client),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AnalyzeAccepted:
    if (text is None) == (file is None):
        raise _http("INPUT_REQUIRED", "Envie exatamente um entre 'text' e 'file'.", 422)

    job = session.get(Job, job_id)
    if job is None or job.created_by != client:
        raise HTTPException(404, "Vaga não encontrada.")

    if idempotency_key:
        existing = session.scalar(
            select(Analysis).where(Analysis.created_by == client, Analysis.idempotency_key == idempotency_key)
        )
        if existing:
            return _accepted(existing)

    try:
        if file is not None:
            data = file.file.read(settings.max_upload_bytes + 1)
            if len(data) > settings.max_upload_bytes:
                raise DocumentError("FILE_TOO_LARGE", "Arquivo excede o tamanho máximo.", 413)
            raw = extract_pdf_text(
                data,
                max_pages=settings.max_pdf_pages,
                max_chars=settings.max_text_chars,
                min_chars=settings.min_text_chars,
            )
        else:
            raw = text or ""
            if len(raw) > settings.max_text_chars:
                raise DocumentError("TEXT_TOO_LONG", f"Texto excede {settings.max_text_chars} caracteres.", 413)
    except DocumentError as exc:
        raise _http(exc.code, exc.message, exc.http_status) from exc

    redacted = redact(raw)
    if len(redacted.text.strip()) < settings.min_text_chars:
        raise _http("TEXT_TOO_SHORT", "Texto insuficiente após remoção de dados pessoais.", 422)

    now = utcnow()
    candidate = Candidate(
        id=new_id("cand"),
        redacted_text=redacted.text,
        redaction_report=redacted.report,
        lawful_basis=lawful_basis.value,
        created_by=client,
        expires_at=now + timedelta(days=settings.retention_days),
    )
    analysis = Analysis(
        id=new_uuid(),
        trace_id=request.state.trace_id,
        job_id=job.id,
        candidate_id=candidate.id,
        created_by=client,
        idempotency_key=idempotency_key,
        status=AnalysisStatus.PENDING,
    )
    session.add_all([candidate, analysis])
    session.commit()  # commit ANTES de enfileirar, senão o worker pode não achar a linha

    try:
        enqueue_analysis(analysis.id)
    except Exception:
        log.exception("enqueue_failed trace_id=%s", analysis.trace_id)
        mark_failed(session, analysis.id, "QUEUE_UNAVAILABLE")
        raise _http("QUEUE_UNAVAILABLE", "Fila indisponível. Tente novamente.", 503)
    return _accepted(analysis)


@router.get("/results/{task_id}", response_model=ResultOut)
def get_result(
    task_id: str,
    response: Response,
    client: str = Depends(require_client),
    session: Session = Depends(get_session),
) -> ResultOut:
    analysis = _owned_analysis(session, task_id, client)
    if analysis.status in (AnalysisStatus.PENDING, AnalysisStatus.PROCESSING):
        response.status_code = 202
    return _to_result(analysis)


@router.put("/results/{task_id}/review", response_model=ResultOut)
def review_result(
    task_id: str,
    payload: ReviewIn,
    request: Request,
    client: str = Depends(require_client),
    session: Session = Depends(get_session),
) -> ResultOut:
    analysis = _owned_analysis(session, task_id, client)
    if analysis.status != AnalysisStatus.SUCCEEDED:
        raise _http("NOT_REVIEWABLE", "Só análises concluídas podem ser revisadas.", 409)
    analysis.review_decision = payload.decision.value
    analysis.review_note = payload.note
    analysis.reviewed_by = client
    analysis.reviewed_at = utcnow()
    audit(session, client, "analysis_reviewed", "analysis", analysis.id, request.state.trace_id)
    session.commit()
    return _to_result(analysis)


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: str,
    request: Request,
    client: str = Depends(require_client),
    session: Session = Depends(get_session),
) -> CandidateOut:
    """Direito de acesso (LGPD art. 18, II)."""
    candidate = session.get(Candidate, candidate_id)
    if candidate is None or candidate.created_by != client:
        raise HTTPException(404, "Candidato não encontrado.")
    analyses = session.scalars(select(Analysis).where(Analysis.candidate_id == candidate_id))
    audit(session, client, "candidate_accessed", "candidate", candidate_id, request.state.trace_id)
    session.commit()
    return CandidateOut(
        candidate_id=candidate.id,
        lawful_basis=LawfulBasis(candidate.lawful_basis),
        created_at=candidate.created_at,
        expires_at=candidate.expires_at,
        redaction_report=candidate.redaction_report,
        redacted_text=candidate.redacted_text,
        analyses=[AnalysisRef(task_id=a.id, status=AnalysisStatus(a.status)) for a in analyses],
    )


@router.delete("/{candidate_id}", status_code=204)
def delete_candidate(
    candidate_id: str,
    request: Request,
    client: str = Depends(require_client),
    session: Session = Depends(get_session),
) -> Response:
    """Direito de eliminação (LGPD art. 18, VI)."""
    candidate = session.get(Candidate, candidate_id)
    if candidate is None or candidate.created_by != client:
        raise HTTPException(404, "Candidato não encontrado.")
    delete_candidate_data(session, candidate_id)
    audit(session, client, "candidate_deleted", "candidate", candidate_id, request.state.trace_id)
    session.commit()
    return Response(status_code=204)
