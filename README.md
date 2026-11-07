# TalentMatch AI — API de triagem e extração de currículos

API assíncrona (FastAPI + Celery + PostgreSQL) que **extrai evidências** de currículos contra os requisitos de uma vaga.
A LLM só extrai; o **score é calculado em código**. Nenhuma decisão é automatizada: toda análise exige revisão humana.

> Projeto de portfólio. Use **apenas currículos sintéticos**. Os documentos de conformidade em `docs/` são modelos ilustrativos.

## Decisões de projeto (e por quê)

| Decisão | Motivo |
|---|---|
| Score = Σ(peso atendido)/Σ(peso) × 100, em código | LLM não é reprodutível nem auditável para gerar nota |
| "Determinismo" = schema válido + reprodutibilidade auditável | `temperature=0` + `seed` reduzem variação, não a eliminam |
| Saída estruturada: `json_schema` estrito quando o provedor suporta; `json_object` + schema no prompt como alternativa | `json_object` só garante JSON; por isso a validação é sempre feita em código |
| Loop de autocorreção próprio (máx. 3 tentativas) | Controle exato de tokens somados por tentativa e erros sem eco de PII |
| Evidência deve ser trecho **literal** do currículo | Anti-alucinação e anti prompt-injection |
| `extraction_confidence` (não `confidence_score`) | Valor autodeclarado pela LLM não é probabilidade calibrada |
| PDF nunca é persistido; só texto pseudonimizado | Minimização (LGPD art. 6º, III) |
| Resultado no PostgreSQL; Celery sem result backend | Redis é efêmero e não deve guardar PII |
| Provedor de LLM configurável (`LLM_BASE_URL`) | Qualquer endpoint compatível com a API da OpenAI (OpenAI, OpenRouter, Gemini) |
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
cp .env.example .env        # preencha a chave do provedor (OPENAI_API_KEY) e API_KEYS
docker compose up --build
```

Exemplo de chamadas (no Windows PowerShell, use `curl.exe` no lugar de `curl`):

```bash
curl -X POST localhost:8000/api/v1/jobs -H "X-API-Key: <secret>" -H "Content-Type: application/json" -d '{
  "title":"Backend Python","must_have":[
   {"key":"fastapi_experience","description":"Experiencia com FastAPI","weight":2},
   {"key":"pytest_coverage","description":"Testes com Pytest","weight":1}]}'
curl -X POST localhost:8000/api/v1/candidates/analyze -H "X-API-Key: <secret>" \
  -F job_id=job_xxx -F lawful_basis=consent -F file=@curriculo.pdf
```

O `<secret>` é o valor que vem **depois** de `client_id:` na variável `API_KEYS`.

### Provedor de LLM

| Variável | Uso |
|---|---|
| `OPENAI_API_KEY` | Chave do provedor escolhido (o nome é só histórico) |
| `LLM_BASE_URL` | Vazio = OpenAI. OpenRouter: `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Modelo. Use um snapshot fixo, não alias móvel |
| `LLM_STRUCTURED_MODE` | `json_schema` (estrito) ou `json_object` (schema no prompt) |
| `LLM_SEND_SEED` | `false` se o provedor rejeitar o parâmetro `seed` |
| `LLM_MAX_COMPLETION_TOKENS` | Aumente para modelos que gastam tokens raciocinando |

Valide o provedor antes de subir o Docker: `python -m scripts.smoke_llm`.
Camadas gratuitas podem usar prompts e respostas para treino: **só use currículos sintéticos nelas.**

## Testes e avaliação

- Testes: `pip install -r requirements-dev.txt && pytest --cov=app` (SQLite em memória, LLM simulada).
- Qualidade da extração (chama a LLM real, consome cota): `python -m scripts.eval_golden`.

## Métricas

### Medido

**Suíte de testes:** 86 testes, 99% de cobertura de linhas/branches em `app/`; 100% em schemas, validação, scoring, redação, extração e pipeline. Os testes usam LLM simulada e SQLite.

**Com LLM real** — OpenRouter, modelo gratuito `nvidia/nemotron-3-ultra-550b-a55b:free`, modo `json_object`:

| Medição | Resultado |
|---|---|
| Golden set (`scripts/eval_golden`) | 6/6 casos sintéticos corretos (18/18 itens do checklist), incluindo 1 caso de prompt injection |
| Tentativas por caso | 1,17 em média (7 chamadas para 6 casos; a autocorreção foi acionada) |
| Tokens por caso | ≈ 1.665 (prompt + completion, somando tentativas) |
| Latência da LLM | ≈ 19,5 s por caso (soma das chamadas); 11,3 s em uma chamada isolada |
| Fluxo ponta a ponta via API (Docker) | POST → worker → GET executado manualmente até `SUCCEEDED` (sem teste automatizado) |
| Stack Docker Compose | Os 5 serviços (api, worker, beat, postgres, redis) subiram sem erro; worker com 16 threads e `results: disabled` |

**Leitura honesta:** com 6 casos, 6/6 não prova alta acurácia. O intervalo de confiança de 95% vai de ≈ 54% a 100%.
Os casos são sintéticos e simples. Não há medição de latência da API sob carga.

### Metas não validadas

Dependem de teste de carga e do provedor; não são garantias. Foram pensadas para um modelo pequeno pago.
Com o modelo gratuito medido acima, a latência da LLM fica em 11–20 s.

| Métrica | Meta |
|---|---|
| `POST /analyze` p95 | < 300 ms (inclui parse de PDF e redação) |
| `GET /results` p95 | < 50 ms |
| Análise ponta a ponta | p50 3–6 s, p95 10–15 s (modelo pequeno pago) |
| Schema válido na 1ª tentativa | 95–99% |
| Sucesso após até 2 correções | > 99,5% |
| Vazão sustentada, 1 nó | 60–100 análises/min (limitada pelo rate limit do provedor) |
| Custo | ≈ US$ 0,0007/análise (gpt-4o-mini; confirmar preço atual). Modelo gratuito: sem custo |

## Limites conhecidos do MVP

- Testado com OpenRouter (modelo gratuito). **Não testado com gpt-4o-mini** nem com o Gemini.
- Os testes automatizados não usam Postgres nem Redis reais; a integração entre eles só foi exercitada manualmente via Docker.
- Golden set com 6 casos é smoke test, não estatística.
- Sem OCR (PDF escaneado é rejeitado), sem rate limiting, sem migrações (usa `create_all`), auth por API key estática.
- Pseudonimização por regex + heurística: ver `docs/LGPD.md`.
- Sem teste de carga: as metas de vazão e de latência da API são estimativas.

## Documentação de conformidade

`docs/LGPD.md` (mapa técnico), `docs/RoPA.md` e `docs/RIPD.md` (modelos ilustrativos, **sem valor jurídico**).

## Roadmap

1. Alembic · 2. Teste de carga (Locust) e medição real das metas · 3. Golden set de 30–50 casos
4. NER (spaCy `pt_core_news`) na pseudonimização · 5. Rate limiting · 6. JWT/OAuth · 7. Cache por hash do input
8. Testes de integração com Postgres e Redis reais
