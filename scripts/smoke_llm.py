"""Teste rápido do provedor de LLM configurado no .env, sem Docker e sem banco.

Uso (na raiz do projeto, com o venv ativo):  python -m scripts.smoke_llm
Faz de 1 a 3 chamadas reais (currículo SINTÉTICO) e mostra se o modelo respeita o schema.
"""
from app.config import get_settings
from app.llm.client import LLMPermanentError, LLMTransientError, build_llm_client
from app.schemas import MustHave
from app.services.extraction import run_extraction

CV = (
    "Experiência: 3 anos desenvolvendo APIs com FastAPI em produção.\n"
    "Usei Celery e Redis para processar tarefas assíncronas.\n"
    "Sem experiência com testes automatizados."
)
MUST_HAVE = [
    MustHave(key="fastapi_experience", description="Experiência prática com FastAPI", weight=2),
    MustHave(key="async_architecture", description="Arquitetura assíncrona com filas", weight=1),
    MustHave(key="pytest_coverage", description="Testes automatizados com Pytest", weight=1),
]


def main() -> None:
    settings = get_settings()
    print(f"modelo: {settings.llm_model} | base_url: {settings.llm_base_url or 'OpenAI'} | modo: {settings.llm_structured_mode}")
    try:
        run = run_extraction(
            client=build_llm_client(settings), title="Backend Python", description=None,
            must_have=MUST_HAVE, cv_text=CV, max_attempts=settings.llm_max_attempts,
        )
    except (LLMTransientError, LLMPermanentError) as exc:
        print(f"ERRO do provedor: {type(exc).__name__}: {exc}  (429 = limite/sobrecarga; 401 = chave; 400 = parâmetro)")
        return
    for i, a in enumerate(run.attempts, 1):
        print(f"tentativa {i}: {a.outcome} | tokens {a.prompt_tokens}+{a.completion_tokens} | {a.latency_ms} ms"
              + (f" | {a.error_detail}" if a.error_detail else ""))
    if run.validated:
        print("OK. checklist esperado: fastapi=True, async=True, pytest=False")
        print("obtido:", run.validated.checklist)
    else:
        print(f"FALHOU: {run.error_code}. Tente outro modelo ou aumente LLM_MAX_COMPLETION_TOKENS.")


if __name__ == "__main__":
    main()
