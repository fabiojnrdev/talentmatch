# TalentMatch AI — API de triagem e extração de currículos

API assíncrona (FastAPI + Celery + PostgreSQL) que **extrai evidências** de currículos contra os requisitos de uma vaga.
A LLM só extrai; o **score é calculado em código**. Nenhuma decisão é automatizada: toda análise exige revisão humana.

## Decisões de projeto (e por quê)

| Decisão | Motivo |
|---|---|
| Score = Σ(peso atendido)/Σ(peso) × 100, em código | LLM não é reprodutível nem auditável para gerar nota |
| "Determinismo" = schema válido + reprodutibilidade auditável | `temperature=0` + `seed` reduzem variação, não a eliminam |
| Structured Outputs `json_schema` estrito + validação de negócio | `json_object` só garante JSON, não o schema |
| Loop de autocorreção próprio (máx. 3 tentativas) | Controle exato de tokens somados por tentativa e erros sem eco de PII |
| Evidência deve ser trecho **literal** do currículo | Anti-alucinação e anti prompt-injection |
| `extraction_confidence` (não `confidence_score`) | Valor autodeclarado pela LLM não é probabilidade calibrada |
| PDF nunca é persistido; só texto pseudonimizado | Minimização (LGPD art. 6º, III) |
| Resultado no PostgreSQL; Celery sem result backend | Redis é efêmero e não deve guardar PII |
| SQLAlchemy síncrono | Endpoints enfileiram e leem por PK; o gargalo é a LLM, não o ORM |

## Endpoints (`X-API-Key` obrigatório)

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/v1/jobs` | Cadastra vaga e requisitos com pesos |
| GET | `/api/v1/jobs/{id}` | Consulta vaga |
| POST | `/api/v1/candidates/analyze` | `multipart`: `job_id`, `lawful_basis` (`consent`\|`pre_contractual`), `file` (PDF) **ou** `text`. Header opcional `Idempotency-Key`. Retorna **202** com `task_id` e `trace_id` |
| GET | `/api/v1/candidates/results/{task_id}` | 202 enquanto pendente; 200 com resultado ou erro |
| PUT | `/api/v1/candidates/results/{task_id}/review` | Revisão humana (art. 20) |
| GET | `/api/v1/candidates/{candidate_id}` | Direito de acesso (art. 18, II) |
| DELETE | `/api/v1/candidates/{candidate_id}` | Direito de eliminação (art. 18, VI) |

## Rodando

```bash
cp .env.example .env        # preencha OPENAI_API_KEY e API_KEYS
docker compose up --build
curl -X POST localhost:8000/api/v1/jobs -H "X-API-Key: <secret>" -H "Content-Type: application/json" -d '{
  "title":"Backend Python","must_have":[
   {"key":"fastapi_experience","description":"Experiência com FastAPI","weight":2},
   {"key":"pytest_coverage","description":"Testes com Pytest","weight":1}]}'
curl -X POST localhost:8000/api/v1/candidates/analyze -H "X-API-Key: <secret>" \
  -F job_id=job_xxx -F lawful_basis=consent -F file=@curriculo.pdf
```

Testes: `pip install -r requirements-dev.txt && pytest --cov=app` (SQLite em memória, LLM simulada).
Qualidade da extração (chama a LLM real): `python -m scripts.eval_golden`.

## Métricas

**Medido (suíte de testes):** 81 testes, 99% de cobertura de linhas/branches em `app/`; 100% em schemas, validação, scoring, redação, extração e pipeline.

**Metas NÃO validadas** (dependem de teste de carga e do provedor; não são garantias):

| Métrica | Meta |
|---|---|
| `POST /analyze` p95 | < 300 ms (inclui parse de PDF e redação) |
| `GET /results` p95 | < 50 ms |
| Análise ponta a ponta | p50 3–6 s, p95 10–15 s |
| Schema válido na 1ª tentativa | 95–99% |
| Sucesso após até 2 correções | > 99,5% |
| Vazão sustentada, 1 nó | 60–100 análises/min (limitada pelo rate limit do provedor) |
| Custo | ≈ US$ 0,0007/análise (gpt-4o-mini; confirmar preço atual) |

## Limites conhecidos do MVP

- Não testado contra a API real da OpenAI neste repositório (somente cliente simulado). Rode `scripts.eval_golden` primeiro.
- Sem OCR (PDF escaneado é rejeitado), sem rate limiting, sem migrações (usa `create_all`), auth por API key estática.
- Golden set com 6 casos é smoke test, não estatística.
- Pseudonimização por regex + heurística: ver `docs/LGPD.md`.

## Outros provedores de LLM (OpenRouter, Google)

Configure `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY` (a chave do provedor) e, se preciso, `LLM_STRUCTURED_MODE=json_object`
e `LLM_SEND_SEED=false` (ver `.env.example`). **Não testado contra esses provedores neste repositório.**
Teste o provedor antes do Docker: `python -m scripts.smoke_llm`.
Camadas gratuitas podem usar prompts e respostas para treino: **só use currículos sintéticos nelas.**
Modelos "thinking" gastam tokens de raciocínio; se a resposta truncar, aumente `LLM_MAX_COMPLETION_TOKENS`.

## Documentação de conformidade

`docs/LGPD.md` (mapa técnico), `docs/RoPA.md` e `docs/RIPD.md` (modelos ilustrativos, **sem valor jurídico**).

## Roadmap

1. Alembic · 2. Teste de carga (Locust) e medição real das metas · 3. Golden set de 30–50 casos
4. NER (spaCy `pt_core_news`) na pseudonimização · 5. Rate limiting · 6. JWT/OAuth · 7. Cache por hash do input
