from app import worker
from app.llm.client import LLMTransientError
from app.models import Analysis, Candidate, Job
from app.db import session_scope
from tests.helpers import CV, JOB_PAYLOAD, FakeLLM, call, good_payload


def _seed():
    import datetime

    with session_scope() as s:
        s.add_all([
            Job(id="job_1", title="V", description=None, must_have=JOB_PAYLOAD["must_have"], created_by="t"),
            Candidate(id="cand_1", redacted_text=CV, redaction_report={}, lawful_basis="consent", created_by="t",
                      expires_at=datetime.datetime(2999, 1, 1)),
            Analysis(id="t1", trace_id="tr", job_id="job_1", candidate_id="cand_1", created_by="t"),
        ])
        s.commit()


def test_task_runs_pipeline(monkeypatch):
    _seed()
    monkeypatch.setattr(worker, "build_llm_client", lambda settings: FakeLLM([call(good_payload())]))
    worker.analyze_candidate.run("t1")
    with session_scope() as s:
        assert s.get(Analysis, "t1").status == "SUCCEEDED"


def test_on_failure_marks_analysis_failed():
    _seed()
    task = worker.analyze_candidate
    task.on_failure(LLMTransientError("x"), "t1", ["t1"], {}, None)
    with session_scope() as s:
        a = s.get(Analysis, "t1")
        assert a.status == "FAILED" and a.error_code == "LLM_UNAVAILABLE"


def test_on_failure_generic_code():
    _seed()
    worker.analyze_candidate.on_failure(RuntimeError("x"), "t1", ["t1"], {}, None)
    with session_scope() as s:
        assert s.get(Analysis, "t1").error_code == "TASK_FAILED"


def test_purge_task():
    assert worker.purge_expired_task.run() == 0


def test_celery_config_has_no_result_backend_and_acks_late():
    assert worker.celery_app.conf.task_ignore_result is True
    assert worker.celery_app.conf.task_acks_late is True
    assert "purge-expired" in worker.celery_app.conf.beat_schedule
