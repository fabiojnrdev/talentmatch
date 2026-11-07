import json

import pytest
from sqlalchemy import select

from app.config import Settings
from app.llm.client import LLMPermanentError, LLMTransientError
from app.models import Analysis, Candidate, Job, LLMExecution
from app.services.extraction import run_extraction
from app.services.pipeline import mark_failed, process_analysis
from app.schemas import MustHave
from tests.helpers import CV, JOB_PAYLOAD, FakeLLM, call, good_payload

SETTINGS = Settings(llm_max_attempts=3)


def seed(session, text=CV):
    job = Job(id="job_1", title="Vaga", description=None, must_have=JOB_PAYLOAD["must_have"], created_by="tester")
    cand = Candidate(id="cand_1", redacted_text=text, redaction_report={}, lawful_basis="consent",
                     created_by="tester", expires_at=__import__("datetime").datetime(2999, 1, 1))
    an = Analysis(id="task-1", trace_id="trace-1", job_id="job_1", candidate_id="cand_1", created_by="tester")
    session.add_all([job, cand, an])
    session.commit()
    return an


def test_success_first_try(session):
    an = seed(session)
    process_analysis(session, "task-1", FakeLLM([call(good_payload(), pt=900, ct=200)]), SETTINGS)
    session.refresh(an)
    assert an.status == "SUCCEEDED" and an.finished_at is not None
    r = an.result
    assert r["trace_id"] == "trace-1" and r["model_version"] == "gpt-4o-mini-2024-07-18"
    assert r["execution_metrics"] == {"latency_ms": 120, "prompt_tokens": 900, "completion_tokens": 200,
                                      "total_tokens": 1100, "attempts": 1}
    m = r["match_analysis"]
    assert m["match_score"] == 75.0  # pesos 2+1 de 4
    assert m["review_required"] is True and m["candidate_id"] == "cand_1" and m["job_id"] == "job_1"
    assert m["must_have_checklist"]["pytest_coverage"] is False


def test_self_correction_loop_sums_tokens_and_feeds_errors_back(session):
    an = seed(session)
    bad = good_payload()
    bad["checklist"][0]["evidence"] = "inventado que não existe"
    llm = FakeLLM([call(bad, pt=500, ct=100), call(None, raw="{not json", pt=600, ct=10),
                   call(good_payload(), pt=700, ct=120)])
    process_analysis(session, "task-1", llm, SETTINGS)
    session.refresh(an)
    assert an.status == "SUCCEEDED"
    assert an.result["execution_metrics"]["attempts"] == 3
    assert an.result["execution_metrics"]["prompt_tokens"] == 1800
    assert an.result["execution_metrics"]["total_tokens"] == 1800 + 230
    rows = list(session.scalars(select(LLMExecution).order_by(LLMExecution.attempt)))
    assert [r.outcome for r in rows] == ["validation_error", "validation_error", "ok"]
    assert all(r.trace_id == "trace-1" and r.prompt_version == "v1" for r in rows)
    assert "evidence não é trecho literal" in rows[0].error_detail
    # correção enviada de volta ao modelo na 2ª chamada
    assert llm.calls[1][-1]["role"] == "user" and "inválida" in llm.calls[1][-1]["content"]
    assert llm.calls[1][-2]["role"] == "assistant"


def test_fails_after_max_attempts(session):
    an = seed(session)
    llm = FakeLLM([call(None, raw="lixo")] * 3)
    process_analysis(session, "task-1", llm, SETTINGS)
    session.refresh(an)
    assert an.status == "FAILED" and an.error_code == "LLM_VALIDATION_FAILED" and an.result is None


def test_truncated_response_counts_as_invalid(session):
    an = seed(session)
    process_analysis(session, "task-1", FakeLLM([call(good_payload(), finish="length"), call(good_payload())]),
                     SETTINGS)
    session.refresh(an)
    assert an.status == "SUCCEEDED" and an.result["execution_metrics"]["attempts"] == 2


def test_transient_error_requeues_and_logs(session):
    an = seed(session)
    with pytest.raises(LLMTransientError):
        process_analysis(session, "task-1", FakeLLM([LLMTransientError("RateLimitError")]), SETTINGS)
    session.refresh(an)
    assert an.status == "PENDING"
    row = session.scalars(select(LLMExecution)).one()
    assert row.outcome == "api_error" and row.attempt == 1
    # retry do Celery: numeração continua e processa
    process_analysis(session, "task-1", FakeLLM([call(good_payload())]), SETTINGS)
    session.refresh(an)
    assert an.status == "SUCCEEDED" and an.result["execution_metrics"]["attempts"] == 2
    assert sorted(r.attempt for r in session.scalars(select(LLMExecution))) == [1, 2]


def test_permanent_error_fails(session):
    an = seed(session)
    process_analysis(session, "task-1", FakeLLM([LLMPermanentError("HTTP 401")]), SETTINGS)
    session.refresh(an)
    assert an.status == "FAILED" and an.error_code == "LLM_PERMANENT_ERROR"


def test_missing_candidate_fails(session):
    an = seed(session)
    an.candidate_id = None
    session.commit()
    process_analysis(session, "task-1", FakeLLM([]), SETTINGS)
    session.refresh(an)
    assert an.error_code == "INPUT_UNAVAILABLE"


def test_idempotent_and_unknown_ids(session):
    an = seed(session)
    process_analysis(session, "nope", FakeLLM([]), SETTINGS)
    process_analysis(session, "task-1", FakeLLM([call(good_payload())]), SETTINGS)
    process_analysis(session, "task-1", FakeLLM([]), SETTINGS)  # reentrega: não chama a LLM
    session.refresh(an)
    assert an.status == "SUCCEEDED"


def test_mark_failed_does_not_overwrite_terminal(session):
    an = seed(session)
    process_analysis(session, "task-1", FakeLLM([call(good_payload())]), SETTINGS)
    mark_failed(session, "task-1", "TASK_FAILED")
    mark_failed(session, "unknown", "TASK_FAILED")
    session.refresh(an)
    assert an.status == "SUCCEEDED"


def test_run_extraction_without_callback():
    mh = [MustHave(**m) for m in JOB_PAYLOAD["must_have"]]
    run = run_extraction(client=FakeLLM([call(good_payload())]), title="t", description=None, must_have=mh,
                         cv_text=CV, max_attempts=2)
    assert run.validated is not None and len(run.attempts) == 1
    assert run.attempts[0].input_sha256 and run.attempts[0].output_sha256


def test_llm_logs_contain_no_cv_text(session):
    seed(session)
    process_analysis(session, "task-1", FakeLLM([call(good_payload())]), SETTINGS)
    dump = json.dumps([r.__dict__.get("error_detail") for r in session.scalars(select(LLMExecution))])
    assert "Maria" not in dump and "FastAPI" not in dump


def test_json_wrapped_in_markdown_fence_is_accepted(session):
    an = seed(session)
    fenced = "```json\n" + json.dumps(good_payload()) + "\n```"
    process_analysis(session, "task-1", FakeLLM([call(None, raw=fenced)]), SETTINGS)
    session.refresh(an)
    assert an.status == "SUCCEEDED" and an.result["execution_metrics"]["attempts"] == 1
