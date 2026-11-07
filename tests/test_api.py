from datetime import timedelta

from sqlalchemy import select

from app import queueing
from app.api import candidates as candidates_module
from app.config import Settings, get_settings
from app.db import session_scope
from app.main import app as fastapi_app
from app.models import Analysis, AuditEvent, Candidate, LLMExecution
from app.services.pipeline import process_analysis
from app.services.retention import purge_expired
from app.utils import utcnow
from tests.conftest import AUTH, OTHER
from tests.helpers import CV, JOB_PAYLOAD, FakeLLM, call, good_payload
from tests.test_pdf import make_pdf

RAW_CV = (
    "Maria Souza Lima\nEmail: maria@example.com\nTelefone: (86) 99999-8888\nCPF: 123.456.789-09\n"
    "Estado civil: casada\n" + CV
)


def make_job(client, headers=AUTH):
    r = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def analyze(client, job_id, **kw):
    data = {"job_id": job_id, "lawful_basis": "consent"}
    data.update(kw.pop("data", {}))
    return client.post("/api/v1/candidates/analyze", data=data, headers=kw.pop("headers", AUTH), **kw)


def test_health_and_trace_header(client):
    r = client.get("/health")
    assert r.status_code == 200 and len(r.headers["X-Trace-Id"]) == 36


def test_auth_required(client):
    assert client.post("/api/v1/jobs", json=JOB_PAYLOAD).status_code == 401
    assert client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/v1/candidates/results/x").status_code == 401


def test_job_crud_and_ownership(client):
    jid = make_job(client)
    assert client.get(f"/api/v1/jobs/{jid}", headers=AUTH).json()["title"] == JOB_PAYLOAD["title"]
    assert client.get(f"/api/v1/jobs/{jid}", headers=OTHER).status_code == 404
    assert client.get("/api/v1/jobs/nope", headers=AUTH).status_code == 404
    assert client.post("/api/v1/jobs", json={"title": "x"}, headers=AUTH).status_code == 422


def test_full_flow_text(client, monkeypatch):
    queued = []
    monkeypatch.setattr(candidates_module, "enqueue_analysis", queued.append)
    jid = make_job(client)
    r = analyze(client, jid, data={"text": RAW_CV})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "PENDING" and body["trace_id"] == r.headers["X-Trace-Id"]
    assert queued == [body["task_id"]]

    pending = client.get(f"/api/v1/candidates/results/{body['task_id']}", headers=AUTH)
    assert pending.status_code == 202 and pending.json()["result"] is None

    with session_scope() as s:  # simula o worker
        process_analysis(s, body["task_id"], FakeLLM([call(good_payload())]), Settings())

    done = client.get(f"/api/v1/candidates/results/{body['task_id']}", headers=AUTH)
    assert done.status_code == 200
    d = done.json()
    assert d["status"] == "SUCCEEDED" and d["result"]["trace_id"] == body["trace_id"]
    assert d["result"]["match_analysis"]["match_score"] == 75.0

    # PII nunca chegou ao banco nem ao texto salvo
    cand = client.get(f"/api/v1/candidates/{body['candidate_id']}", headers=AUTH).json()
    for leaked in ["maria@example.com", "99999-8888", "123.456.789-09", "casada", "Maria Souza"]:
        assert leaked not in cand["redacted_text"]
    assert cand["redaction_report"]["email"] == 1 and cand["lawful_basis"] == "consent"
    assert cand["analyses"][0]["task_id"] == body["task_id"]


def test_results_scoped_per_client(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    tid = analyze(client, jid, data={"text": RAW_CV}).json()["task_id"]
    assert client.get(f"/api/v1/candidates/results/{tid}", headers=OTHER).status_code == 404
    assert client.get("/api/v1/candidates/results/nope", headers=AUTH).status_code == 404
    assert analyze(client, jid, data={"text": RAW_CV}, headers=OTHER).status_code == 404  # vaga de outro client


def test_analyze_pdf(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    pdf = make_pdf(["Experiencia com FastAPI e Celery em producao", "Pytest com cobertura alta nos projetos"])
    r = analyze(client, jid, files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert r.status_code == 202, r.text


def test_analyze_input_validation(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    both = analyze(client, jid, data={"text": RAW_CV}, files={"file": ("cv.pdf", make_pdf(["x"]), "application/pdf")})
    assert both.status_code == 422 and both.json()["detail"]["code"] == "INPUT_REQUIRED"
    assert analyze(client, jid).json()["detail"]["code"] == "INPUT_REQUIRED"
    assert analyze(client, jid, data={"text": "curto"}).json()["detail"]["code"] == "TEXT_TOO_SHORT"
    assert analyze(client, jid, data={"text": "a" * 20_001}).status_code == 413
    bad_basis = analyze(client, jid, data={"text": RAW_CV, "lawful_basis": "legitimate_interest"})
    assert bad_basis.status_code == 422
    not_pdf = analyze(client, jid, files={"file": ("cv.pdf", b"hello", "application/pdf")})
    assert not_pdf.json()["detail"]["code"] == "INVALID_PDF"
    assert analyze(client, "job_x", data={"text": RAW_CV}).status_code == 404


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    fastapi_app.dependency_overrides[get_settings] = lambda: Settings(
        max_upload_bytes=100, api_keys="tester:secret-a"
    )
    r = analyze(client, jid, files={"file": ("cv.pdf", b"%PDF-" + b"0" * 500, "application/pdf")})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_idempotency_key(client, monkeypatch):
    queued = []
    monkeypatch.setattr(candidates_module, "enqueue_analysis", queued.append)
    jid = make_job(client)
    h = {**AUTH, "Idempotency-Key": "abc-123"}
    first = analyze(client, jid, data={"text": RAW_CV}, headers=h).json()
    second = analyze(client, jid, data={"text": RAW_CV}, headers=h).json()
    assert first["task_id"] == second["task_id"] and len(queued) == 1


def test_queue_failure_returns_503_and_marks_failed(client, monkeypatch):
    def boom(_id):
        raise ConnectionError("redis down")

    monkeypatch.setattr(candidates_module, "enqueue_analysis", boom)
    jid = make_job(client)
    r = analyze(client, jid, data={"text": RAW_CV})
    assert r.status_code == 503
    with session_scope() as s:
        assert s.scalars(select(Analysis)).one().error_code == "QUEUE_UNAVAILABLE"


def test_human_review(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    tid = analyze(client, jid, data={"text": RAW_CV}).json()["task_id"]
    url = f"/api/v1/candidates/results/{tid}/review"
    assert client.put(url, json={"decision": "approved"}, headers=AUTH).status_code == 409  # ainda PENDING
    with session_scope() as s:
        process_analysis(s, tid, FakeLLM([call(good_payload())]), Settings())
    assert client.put(url, json={"decision": "maybe"}, headers=AUTH).status_code == 422
    r = client.put(url, json={"decision": "needs_info", "note": "validar Pytest em entrevista"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["human_review"]["decision"] == "needs_info"
    assert client.get(f"/api/v1/candidates/results/{tid}", headers=AUTH).json()["human_review"]["reviewed_by"] == "tester"
    with session_scope() as s:
        assert s.scalars(select(AuditEvent).where(AuditEvent.action == "analysis_reviewed")).one()


def test_failed_result_exposes_error(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    tid = analyze(client, jid, data={"text": RAW_CV}).json()["task_id"]
    with session_scope() as s:
        process_analysis(s, tid, FakeLLM([call(None, raw="x")] * 3), Settings(llm_max_attempts=3))
    r = client.get(f"/api/v1/candidates/results/{tid}", headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "FAILED"
    assert r.json()["error"]["code"] == "LLM_VALIDATION_FAILED"


def test_delete_candidate_erases_everything_but_keeps_anonymous_logs(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    body = analyze(client, jid, data={"text": RAW_CV}).json()
    with session_scope() as s:
        process_analysis(s, body["task_id"], FakeLLM([call(good_payload())]), Settings())
    cid = body["candidate_id"]
    assert client.delete(f"/api/v1/candidates/{cid}", headers=OTHER).status_code == 404
    assert client.delete(f"/api/v1/candidates/{cid}", headers=AUTH).status_code == 204
    assert client.get(f"/api/v1/candidates/{cid}", headers=AUTH).status_code == 404
    assert client.get(f"/api/v1/candidates/results/{body['task_id']}", headers=AUTH).status_code == 404
    with session_scope() as s:
        assert s.scalars(select(Candidate)).first() is None and s.scalars(select(Analysis)).first() is None
        row = s.scalars(select(LLMExecution)).one()
        assert row.analysis_id is None and row.input_sha256 is None and row.output_sha256 is None
        assert s.scalars(select(AuditEvent).where(AuditEvent.action == "candidate_deleted")).one()


def test_purge_expired(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    old = analyze(client, jid, data={"text": RAW_CV}).json()
    fresh = analyze(client, jid, data={"text": RAW_CV}).json()
    with session_scope() as s:
        s.get(Candidate, old["candidate_id"]).expires_at = utcnow() - timedelta(days=1)
        s.commit()
        assert purge_expired(s) == 1
        assert s.get(Candidate, old["candidate_id"]) is None and s.get(Candidate, fresh["candidate_id"])
        assert s.scalars(select(AuditEvent).where(AuditEvent.action == "candidate_purged")).one().actor == "system"
        assert purge_expired(s) == 0


def test_processing_of_deleted_candidate_fails_gracefully(client, monkeypatch):
    monkeypatch.setattr(candidates_module, "enqueue_analysis", lambda _id: None)
    jid = make_job(client)
    body = analyze(client, jid, data={"text": RAW_CV}).json()
    client.delete(f"/api/v1/candidates/{body['candidate_id']}", headers=AUTH)
    with session_scope() as s:
        process_analysis(s, body["task_id"], FakeLLM([]), Settings())  # análise já não existe: no-op


def test_queueing_uses_analysis_id_as_task_id(monkeypatch):
    from app import worker

    sent = {}
    monkeypatch.setattr(worker.analyze_candidate, "apply_async", lambda **kw: sent.update(kw))
    queueing.enqueue_analysis("abc")
    assert sent == {"args": ["abc"], "task_id": "abc"}
