# RoPA — Registro das Operações de Tratamento (LGPD, art. 37)

> **MODELO ILUSTRATIVO.** Controlador, encarregado e contratos abaixo são fictícios. Serve para demonstrar
> estrutura e raciocínio; **não tem valor jurídico** e deve ser refeito com dados reais e revisão jurídica.
> Os fatos técnicos (dados, retenção, controles) refletem o que o código do repositório realmente faz.

## 1. Identificação

| Campo | Conteúdo |
|---|---|
| Controlador | [Empresa Fictícia Ltda.], CNPJ [00.000.000/0001-00] |
| Encarregado (DPO) | [Nome Fictício], dpo@empresa-ficticia.example |
| Operadores | Provedor de LLM (OpenAI); provedor de infraestrutura/hospedagem [a definir] |
| Sistema | TalentMatch AI |
| Versão do registro / data | 1.0 / [data] |

## 2. Operação: triagem técnica de currículos

| Campo | Conteúdo |
|---|---|
| Finalidade | Auxiliar recrutadores a comparar o currículo de candidatos com requisitos técnicos de uma vaga específica |
| Base legal (art. 7º) | Procedimentos preliminares relacionados a contrato, a pedido do titular (inciso V), para quem se candidatou; ou consentimento (inciso I). Definida por análise no campo `lawful_basis` |
| Titulares | Candidatos a vagas |
| Dados pessoais tratados | Texto do currículo **após pseudonimização** (formação, experiência, habilidades); identificador interno `cand_*`; contagens de itens removidos |
| Dados removidos antes do tratamento | Nome, e-mail, telefone, CPF, CEP, endereço, URLs, datas completas |
| Dados sensíveis (art. 11) | Não são coletados intencionalmente. Linhas com estado civil, raça, religião, PCD e filiação sindical são descartadas. Risco residual: dado sensível em texto livre (ver RIPD) |
| Dados derivados | Checklist de requisitos, trechos de evidência, pontos fortes/lacunas, justificativa, score |
| Origem dos dados | Enviados pelo recrutador (PDF ou texto) |
| Decisão automatizada | Não. Toda análise sai com `review_required: true`; decisão humana registrada via `PUT .../review` |

## 3. Compartilhamento e transferência

| Destinatário | Dados | Finalidade | País | Salvaguarda |
|---|---|---|---|---|
| OpenAI (operador) | Texto pseudonimizado + requisitos da vaga | Extração de evidências | EUA | **Pendente**: cláusulas contratuais/ZDR e verificação de termos vigentes (art. 33) |
| Hospedagem | Banco de dados e backups | Armazenamento | [a definir] | **Pendente** |

## 4. Retenção e eliminação

| Dado | Prazo | Mecanismo |
|---|---|---|
| Candidato e análises | 180 dias (`RETENTION_DAYS`, configurável) | Purge horário via Celery beat; registro em `audit_events` |
| Eliminação a pedido | Imediata | `DELETE /api/v1/candidates/{id}` |
| PDF original | Não é armazenado | Descartado após extração do texto |
| Logs de execução da IA | Mantidos sem vínculo ao candidato | Ao eliminar, `analysis_id` e hashes são zerados |
| Trilha de auditoria | [prazo a definir] | Sem dados pessoais do candidato |

## 5. Medidas de segurança (art. 46)

Autenticação por API key com comparação em tempo constante; isolamento de dados por `client_id`; Redis sem persistência
e sem resultados de tarefas; container sem root; nenhum conteúdo de currículo em logs; trilha de auditoria.
**Pendentes:** TLS na borda, criptografia em repouso do banco, rate limiting, JWT por usuário.

## 6. Direitos dos titulares (art. 18)

| Direito | Atendimento |
|---|---|
| Acesso | `GET /candidates/{id}` |
| Eliminação | `DELETE /candidates/{id}` |
| Revisão de decisão automatizada (art. 20) | Revisão humana obrigatória; o titular solicita ao controlador (canal do DPO) |
| Correção, portabilidade, informação sobre compartilhamento | Processo manual via DPO; **não implementado em API** |
