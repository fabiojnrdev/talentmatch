from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import Analysis, Candidate, LLMExecution
from app.services.audit import audit
from app.utils import utcnow


def delete_candidate_data(session: Session, candidate_id: str) -> int:
    """Elimina candidato, análises (derivadas do currículo) e desvincula/anonimiza logs de IA.
    Não faz commit. Retorna nº de análises removidas."""
    analysis_ids = list(session.scalars(select(Analysis.id).where(Analysis.candidate_id == candidate_id)))
    if analysis_ids:
        session.execute(
            update(LLMExecution)
            .where(LLMExecution.analysis_id.in_(analysis_ids))
            .values(analysis_id=None, input_sha256=None, output_sha256=None)
        )
        session.execute(delete(Analysis).where(Analysis.id.in_(analysis_ids)))
    session.execute(delete(Candidate).where(Candidate.id == candidate_id))
    return len(analysis_ids)


def purge_expired(session: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    ids = list(session.scalars(select(Candidate.id).where(Candidate.expires_at < now)))
    for candidate_id in ids:
        delete_candidate_data(session, candidate_id)
        audit(session, "system", "candidate_purged", "candidate", candidate_id)
    session.commit()
    return len(ids)
