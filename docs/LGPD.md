# LGPD — mapa de controles

> Este documento descreve controles técnicos. **Não é parecer jurídico.** Antes de tratar dados reais de candidatos,
> valide com o DPO/jurídico: base legal, contrato com o provedor de LLM, RoPA e RIPD.
> Para demonstração e portfólio, use **apenas currículos sintéticos**.

| Artigo | Exigência | Controle implementado | Onde |
|---|---|---|---|
| 6º, I–III | Finalidade, adequação, necessidade | Texto pseudonimizado; PDF descartado após extração; só campos necessários | `privacy/redaction.py`, `api/candidates.py` |
| 7º | Base legal | `lawful_basis` obrigatório (`consent` ou `pre_contractual`) e registrado por candidato | `schemas.LawfulBasis` |
| 11 | Dados sensíveis | Linhas com estado civil, raça, religião, PCD, sindicato etc. removidas; prompt proíbe uso | `redaction.py`, `llm/prompts.py` |
| 16 | Eliminação ao fim do tratamento | Retenção configurável (`RETENTION_DAYS`, padrão 180); purge horário via Celery beat | `services/retention.py`, `worker.py` |
| 18, II | Acesso | `GET /candidates/{id}` | `api/candidates.py` |
| 18, VI | Eliminação | `DELETE /candidates/{id}` apaga candidato e análises; logs de IA ficam sem vínculo e sem hashes | `services/retention.py` |
| 20 | Revisão de decisão automatizada | `review_required: true` sempre; `PUT .../review` registra decisão humana | `services/pipeline.py` |
| 33 | Transferência internacional | **Não resolvido por código.** O provedor de LLM está fora do Brasil: exige cláusulas contratuais/ZDR | Responsabilidade do controlador |
| 37 | Registro das operações (RoPA) | **Não incluído.** Este mapa serve de insumo | — |
| 38 | RIPD | **Não incluído.** Recomendado: tratamento automatizado de dados de candidatos | — |
| 46 | Segurança | Autenticação por API key (comparação em tempo constante); isolamento por `client_id`; Redis sem persistência e sem resultados; container sem root; nenhum PII em logs | `api/deps.py`, `docker-compose.yml` |
| 48 | Incidente | **Não incluído.** Definir runbook | — |
| — | Auditoria | `audit_events` (acesso, revisão, exclusão, purge) sem PII; `llm_executions` com `trace_id`, modelo, versões, tokens, latência, hashes | `models.py` |

## Limitações que você deve conhecer

1. **A pseudonimização é best-effort.** Regex cobre e-mail, telefone BR, CPF, CEP, URLs, datas completas e endereços com prefixo.
   O nome é removido pela heurística "primeira linha com 2–6 palavras capitalizadas" e depois em todo o corpo.
   Falha com cabeçalhos atípicos, nomes de empresas/escolas/cidades que identifiquem a pessoa e menções indiretas.
   Isso **reduz** risco; não garante anonimização (art. 12). Mitigação planejada: NER.
2. **Falso positivo conhecido:** uma primeira linha como "Desenvolvedor Backend Python" pode ser tratada como nome e removida.
3. **Dados sensíveis em texto livre** ("sou mãe solo", "pertenço à igreja X") não são detectados por regex.
4. O hash do texto (`input_sha256`) é zerado na eliminação; enquanto existe, é um identificador pseudonimizado.
5. API key estática não oferece trilha por usuário final; para uso real, use JWT/OAuth com identidade do recrutador.
6. A LLM pode errar e ter vieses. O sistema reduz o impacto exigindo evidência literal e revisão humana, mas **não elimina** viés.
7. **Camadas gratuitas de provedores de LLM** (ex.: Gemini API sem faturamento, modelos `:free` do OpenRouter) podem usar o conteúdo
   enviado para melhorar produtos/treinar modelos, e o Google admite revisão humana. Com dados reais isso é incompatível com este projeto.
   Em dados reais, use plano pago com política de não-treino e/ou ZDR, e registre o provedor como operador no RoPA.
