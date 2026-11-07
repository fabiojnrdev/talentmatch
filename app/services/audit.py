from sqlalchemy.orm import Session

from app.models import AuditEvent


def audit(
    session: Session, actor: str, action: str, subject_type: str, subject_id: str, trace_id: str | None = None
) -> None:
    session.add(
        AuditEvent(actor=actor, action=action, subject_type=subject_type, subject_id=subject_id, trace_id=trace_id)
    )
