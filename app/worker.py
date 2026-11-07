from celery import Celery, Task

from app.config import get_settings
from app.db import session_scope
from app.llm.client import LLMTransientError, build_llm_client
from app.services.pipeline import mark_failed, process_analysis
from app.services.retention import purge_expired

_settings = get_settings()

celery_app = Celery("talentmatch", broker=_settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,  # resultados ficam no PostgreSQL; nada de PII no Redis
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=100,
    task_time_limit=120,
    timezone="UTC",
    beat_schedule={"purge-expired": {"task": "app.worker.purge_expired_task", "schedule": 3600.0}},
)


class AnalysisTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):  # falha final (após retries)
        code = "LLM_UNAVAILABLE" if isinstance(exc, LLMTransientError) else "TASK_FAILED"
        with session_scope() as session:
            mark_failed(session, args[0], code)


@celery_app.task(
    base=AnalysisTask,
    bind=True,
    name="app.worker.analyze_candidate",
    autoretry_for=(LLMTransientError,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def analyze_candidate(self, analysis_id: str) -> None:
    settings = get_settings()
    with session_scope() as session:
        process_analysis(session, analysis_id, build_llm_client(settings), settings)


@celery_app.task(name="app.worker.purge_expired_task")
def purge_expired_task() -> int:
    with session_scope() as session:
        return purge_expired(session)
