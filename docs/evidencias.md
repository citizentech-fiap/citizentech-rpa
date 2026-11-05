# Evidências de validação

Todas as execuções abaixo foram feitas em 05/11/2026 com o conjunto sintético rotulado
(`data/synthetic/labels.csv`, 60 solicitações) e a base coletada do gov.br no mesmo dia.
Os números completos, a matriz de confusão e a lista de erros estão em [`eval/resultados_robo.md`](../eval/resultados_robo.md).

## 1. Execução contínua de ponta a ponta

`python run_robot.py --carregar-teste` processou as 60 solicitações em uma única execução, sem intervenção,
em cerca de 3 minutos (o OCR leva ~1,3 s por imagem):

| lidas | inválidas | resolvidas | revisão humana | falhas |
|---|---|---|---|---|
| 60 | 6 | 34 | 20 | 0 |

## 2. Resultado medido

| Métrica | Resultado | n |
|---|---|---|
| Classificação do serviço correta (texto livre) | 95,8% | 48 |
| Pedido fora de escopo encaminhado para revisão humana | 100% | 6 |
| Conferência de documentos correta (OCR) | 100% | 35 |
| Decisão final correta (resolvido / revisão / inválido) | 81,7% | 60 |
| **Erro grave**: resposta automática sobre o serviço errado | **0 de 34** | 34 |
| Erro seguro: revisão humana desnecessária | 7 | 60 |

Leitura: o robô erra para o lado seguro. Quando não tem certeza, manda para uma pessoa em vez de responder
errado. Os 11 erros de decisão são de dois tipos:
- **7 revisões desnecessárias** — pedidos típicos com confiança abaixo de 0,45 (frases mais longas ou
  informais do que as de treino, por exemplo "mandaram embora… parcelas do governo").
- **4 pedidos ambíguos resolvidos automaticamente** — o classificador ficou confiante em um dos dois serviços
  plausíveis (ex.: passaporte × título de eleitor com 0,94). A regra de margem entre o 1º e o 2º serviço só
  pegou 2 dos 6. Não causaram erro grave porque o serviço escolhido era um dos dois plausíveis, mas o cidadão
  recebeu orientação de um só.

**Limiar de confiança.** Simulando outros limiares sobre as confianças registradas: com 0,30 a decisão
correta subiria para 86,7% e continuaria sem erro grave; com 0,20 aparece o primeiro erro grave. Mantivemos
0,45, escolhido antes do teste: mudar o limiar olhando o próprio conjunto de teste seria ajustar a métrica ao
teste. O certo seria calibrar num conjunto de validação separado (trabalho futuro).

**Limites.** Amostra pequena (60), dados sintéticos escritos pelo grupo, documentos gerados por computador
(mais limpos que fotos reais de celular — o OCR deve piorar em uso real), e classificador treinado em frases
que compartilham modelos de escrita (a validação cruzada de 99% é otimista; o número honesto é o do teste
separado).

## 3. Falhas tratadas e demonstradas

| Falha | Como foi provocada | O que o robô fez |
|---|---|---|
| JSON corrompido (2) | arquivos REQ-0048 e REQ-0056 com sintaxe quebrada | rejeitados com motivo no log, movidos para `failed/` com `.motivo.txt`, execução seguiu |
| Campo obrigatório vazio (2) | REQ-0016 e REQ-0027 sem `texto` | idem |
| Anexo ausente / fora da inbox (2) | REQ-0007 aponta para arquivos inexistentes; REQ-0003 tenta ler `../../segredos/cpf.png` | tratados como inválidos; o caminho para fora da inbox é bloqueado |
| Anexo ilegível (5) | imagens borradas, com ruído, baixo contraste, giradas | OCR devolve texto insuficiente → revisão humana (5 de 5) |
| gov.br fora do ar | `python run_robot.py --offline` | os 10 serviços vieram do cache, com a data da coleta original |
| Reenvio da mesma solicitação | as 60 reenviadas na mesma inbox | 54 puladas como duplicadas (hash do arquivo); as 6 inválidas rejeitadas de novo |
| Erro na API do Gemini | `GEMINI_API_KEY` inválida | Gemini respondeu 400; o robô registrou `llm_erro:erro_api_400` e respondeu pelo template com os dados da Carta |
| Chave do Gemini ausente | sem `.env` | resposta pelo template (`llm_indisponivel`) |

Trechos do log (`logs/robot.log`):

```
WARNING | robo.inbox | Solicitação rejeitada (REQ-0048.json): JSON malformado (linha 7, coluna 12): Expecting value
ERROR   | robo.run | REQ-0003 inválida: nenhum dos anexos declarados foi encontrado: ../../segredos/cpf.png
INFO    | robo.collector | Coleta concluída: atualizados=0 inalterados=10 falhas=[] usou_cache=['seguro_desemprego', ...]
INFO    | robo.run | ===== Execução 20261105-131831 concluída: {'lidas': 60, 'invalidas': 6, 'resolvidas': 0, 'revisao_humana': 0, 'falhas': 0, 'puladas_duplicadas': 54} =====
ERROR [citizen_rag.llm] Gemini erro 400: 400 INVALID_ARGUMENT. ... 'API key not valid. ...'
INFO    | robo.responder | RAG sem resposta utilizável (llm_erro:erro_api_400); usando template
```

## 4. Testes automáticos

- `python -m unittest discover -s tests` (RPA): 18 testes, todos passam — coletor (parsers, cache,
  idempotência, retry só em erro temporário, offline sem rede) e IA/documentos (PII, inbox, classificador, OCR).
- `genAI/tests`: 46 testes do assistente RAG, todos passam.
