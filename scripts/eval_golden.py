"""Avalia a extração contra o golden set (casos sintéticos). Chama a LLM real: consome tokens.

Uso:  OPENAI_API_KEY=... python -m scripts.eval_golden
Mede acurácia por item do checklist, taxa de sucesso, tentativas, tokens e latência.
Com 6 casos isto é um smoke de qualidade, NÃO uma métrica estatisticamente confiável.
Para uma estimativa útil, amplie para 30-50 casos rotulados por humano.
"""
import json
import statistics
from pathlib import Path

from app.config import get_settings
from app.llm.client import build_llm_client
from app.privacy.redaction import redact
from app.schemas import MustHave
from app.services.extraction import run_extraction

JOB_TITLE = "Backend Python Pleno"
MUST_HAVE = [
    MustHave(key="fastapi_experience", description="Experiência prática com FastAPI em produção", weight=2),
    MustHave(key="async_architecture", description="Arquitetura assíncrona com filas/mensageria", weight=1),
    MustHave(key="pytest_coverage", description="Testes automatizados com Pytest", weight=1),
]


def main() -> None:
    settings = get_settings()
    client = build_llm_client(settings)
    cases = [json.loads(line) for line in Path("evals/golden.jsonl").read_text().splitlines() if line.strip()]
    correct = total = succeeded = 0
    tokens, latencies, attempts = [], [], []
    for case in cases:
        run = run_extraction(
            client=client, title=JOB_TITLE, description=None, must_have=MUST_HAVE,
            cv_text=redact(case["text"]).text, max_attempts=settings.llm_max_attempts,
        )
        attempts.append(len(run.attempts))
        tokens.append(sum(a.prompt_tokens + a.completion_tokens for a in run.attempts))
        latencies.append(sum(a.latency_ms for a in run.attempts))
        if run.validated is None:
            print(f"{case['id']}: FALHOU ({run.error_code})")
            total += len(case["expected"])
            continue
        succeeded += 1
        hits = sum(run.validated.checklist[k] == v for k, v in case["expected"].items())
        correct += hits
        total += len(case["expected"])
        print(f"{case['id']}: {hits}/{len(case['expected'])} itens corretos")
    print(f"\nacurácia por item: {correct}/{total} = {100 * correct / total:.1f}%")
    print(f"sucesso: {succeeded}/{len(cases)} | tentativas médias: {statistics.mean(attempts):.2f}")
    print(f"tokens médios/caso: {statistics.mean(tokens):.0f} | latência LLM média: {statistics.mean(latencies):.0f} ms")


if __name__ == "__main__":
    main()
