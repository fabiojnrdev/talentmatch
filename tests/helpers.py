import json

from app.llm.client import LLMCallResult

CV = (
    "Maria Souza Lima\n"
    "Desenvolvedora backend com 3 anos de experiência.\n"
    "Construí APIs assíncronas com FastAPI e Celery em produção.\n"
    "Automatizei testes com Pytest e cobertura de 95%.\n"
)

JOB_PAYLOAD = {
    "title": "Backend Python Pleno",
    "description": "Time de plataforma de IA.",
    "must_have": [
        {"key": "fastapi_experience", "description": "Experiência com FastAPI", "weight": 2},
        {"key": "async_architecture", "description": "Arquitetura assíncrona (filas)", "weight": 1},
        {"key": "pytest_coverage", "description": "Testes automatizados com Pytest", "weight": 1},
    ],
}


def good_payload(**overrides) -> dict:
    payload = {
        "checklist": [
            {"key": "fastapi_experience", "met": True, "evidence": "APIs assíncronas com FastAPI"},
            {"key": "async_architecture", "met": True, "evidence": "Celery em produção"},
            {"key": "pytest_coverage", "met": False, "evidence": None},
        ],
        "strengths": ["APIs assíncronas com FastAPI"],
        "gaps": ["Cobertura de testes não comprovada"],
        "extraction_confidence": 0.9,
        "justification": "Evidências claras de FastAPI e Celery.",
    }
    payload.update(overrides)
    return payload


def call(payload, *, pt=100, ct=50, finish="stop", model="gpt-4o-mini-2024-07-18", raw=None) -> LLMCallResult:
    return LLMCallResult(
        raw_content=raw if raw is not None else json.dumps(payload),
        finish_reason=finish,
        model=model,
        system_fingerprint="fp_test",
        prompt_tokens=pt,
        completion_tokens=ct,
        latency_ms=120,
    )


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def extract(self, messages):
        self.calls.append(messages)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
