from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_client
from app.db import get_session
from app.models import Job
from app.schemas import JobCreate, JobOut
from app.utils import new_id

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("", status_code=201, response_model=JobOut)
def create_job(
    payload: JobCreate, client: str = Depends(require_client), session: Session = Depends(get_session)
) -> Job:
    job = Job(
        id=new_id("job"),
        title=payload.title,
        description=payload.description,
        must_have=[m.model_dump() for m in payload.must_have],
        created_by=client,
    )
    session.add(job)
    session.commit()
    return job


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, client: str = Depends(require_client), session: Session = Depends(get_session)) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.created_by != client:
        raise HTTPException(404, "Vaga não encontrada.")
    return job
