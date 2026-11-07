# RIPD — Relatório de Impacto à Proteção de Dados Pessoais (LGPD, art. 38)

> **MODELO ILUSTRATIVO.** Dados do controlador e avaliações são fictícios/estimados por quem desenvolveu o sistema.
> Um RIPD real exige a participação do encarregado, do jurídico e de segurança da informação, e deve ser versionado.

## 1. Descrição do tratamento

Sistema que recebe currículos (PDF ou texto), remove identificadores diretos, envia o texto pseudonimizado a uma LLM
para extrair evidências sobre requisitos de uma vaga, calcula um score por regra determinística e entrega o resultado
a um recrutador, que decide. Detalhes operacionais em `RoPA.md`.

## 2. Necessidade e proporcionalidade

| Pergunta | Avaliação |
|---|---|
| A finalidade é legítima e específica? | Sim: apoio à triagem técnica de uma vaga determinada |
| Todos os dados coletados são necessários? | O texto técnico é necessário; identificadores diretos **não são** e são removidos antes do envio à LLM e da gravação |
| Há alternativa menos intrusiva? | Triagem manual (mais lenta, não menos intrusiva). Não enviar texto a terceiro exigiria LLM local (custo/qualidade) |
| A retenção é proporcional? | 180 dias, configurável, com eliminação automática e sob demanda |
| Informação ao titular | **Pendente**: aviso de privacidade ao candidato informando uso de IA e direito de revisão |

## 3. Riscos identificados

Escala: probabilidade e impacto em Baixo / Médio / Alto. Residual = risco após as medidas **já implementadas**.

| # | Risco | Prob. | Impacto | Medidas implementadas | Residual |
|---|---|---|---|---|---|
| R1 | Reidentificação por falha na pseudonimização (nome em formato atípico, empresa/cidade identificadora) | Média | Alto | Regex + remoção do nome no cabeçalho e no corpo; texto original nunca persistido; report só com contagens | **Médio** |
| R2 | Dado sensível em texto livre ("sou mãe solo", religião) enviado à LLM | Média | Alto | Remoção de linhas com rótulos sensíveis; prompt proíbe uso desses atributos | **Médio** |
| R3 | Vazamento/uso indevido pelo provedor de LLM (transferência internacional) | Baixa | Alto | Só texto pseudonimizado é enviado; modelo com snapshot fixo | **Médio** até haver contrato/ZDR |
| R4 | Decisão discriminatória por viés da LLM | Média | Alto | Score por regra; requisitos técnicos objetivos; evidência literal obrigatória; revisão humana obrigatória | **Médio** (viés não é eliminado) |
| R5 | Alucinação prejudicar candidato (requisito marcado como não atendido sem motivo) | Média | Médio | Evidência conferida contra o texto; `gaps` explícitos; revisão humana; golden set para medir | **Baixo–Médio** |
| R6 | Manipulação por prompt injection no currículo | Média | Médio | Delimitadores sanitizados; instruções de ignorar comandos do currículo; score fora da LLM; evidência literal | **Baixo** |
| R7 | Acesso indevido a dados de outro cliente | Baixa | Alto | Autenticação por API key; consultas filtradas por `client_id` (404 em acesso cruzado); testes automatizados | **Baixo** |
| R8 | Retenção excessiva | Baixa | Médio | TTL de 180 dias, purge horário, `DELETE` sob demanda | **Baixo** |
| R9 | Vazamento por falha de infraestrutura (banco exposto, sem TLS/criptografia em repouso) | Média | Alto | Container sem root; Redis sem persistência; sem PII em logs | **Médio** até implementar TLS e criptografia |

## 4. Medidas adicionais recomendadas (antes de uso real)

1. Contrato com o provedor de LLM (ZDR, cláusulas do art. 33) e avaliação do provedor de hospedagem.
2. NER para pseudonimização; medir taxa de vazamento em amostra sintética rotulada.
3. TLS, criptografia em repouso, rate limiting, JWT com identidade do recrutador.
4. Aviso de privacidade ao candidato e canal do DPO para direito de revisão.
5. Golden set de 30–50 casos; monitorar divergência entre decisão humana e extração.
6. Runbook de incidente (art. 48) e revisão deste RIPD a cada mudança de modelo, prompt ou finalidade.

## 5. Conclusão

Com as medidas implementadas, os riscos R6–R8 são baixos e os demais permanecem **médios**. O uso com dados reais
só é recomendável após as medidas da seção 4 (itens 1 a 4 no mínimo). Pseudonimização **não** equivale a anonimização:
o dado continua sendo pessoal (LGPD, art. 13, §4º).

| Parecer do encarregado | [pendente — fictício] |
|---|---|
| Aprovação do controlador | [pendente — fictício] |
