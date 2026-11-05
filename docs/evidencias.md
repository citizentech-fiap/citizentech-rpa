# Evidências de validação

Todas as execuções abaixo foram feitas em 05/11/2026 com o conjunto sintético rotulado
(`data/synthetic/labels.csv`, 60 pedidos de agricultores de 23 municípios do semiárido) e as 9 Cartas de
Serviço coletadas do gov.br no mesmo dia. Os números completos, a matriz de confusão e a lista de erros estão
em [`eval/resultados_robo.md`](../eval/resultados_robo.md).

**Honestidade do teste.** Os pedidos de teste foram escritos com modelos de frase e vocabulário diferentes
dos de treino: nenhum pedido repete uma frase de treino, e a sobreposição de sequências de 4 palavras entre
teste e treino é 0%.

## 1. Execução contínua de ponta a ponta

`python run_robot.py --carregar-teste` processou os 60 pedidos em uma única execução, sem intervenção, em
cerca de 3 minutos (o OCR leva ~1,3 s por imagem):

| lidas | inválidas | resolvidas | revisão humana | falhas |
|---|---|---|---|---|
| 60 | 6 | 35 | 19 | 0 |

## 2. Resultado medido

| Métrica | Resultado | n |
|---|---|---|
| Classificador: validação cruzada no treino (5 dobras) | 98,0% (F1 macro 0,98) | 400 |
| Classificação do serviço correta no teste (texto livre) | 93,8% | 48 |
| Pedido fora de escopo encaminhado para revisão humana | 100% | 6 |
| OCR: tipo de documento identificado nos anexos legíveis | 100% (123 de 123) | 123 |
| OCR: anexos degradados rejeitados como ilegíveis | 100% (5 de 5) | 5 |
| Conferência de documentos correta (quando o serviço foi acertado) | 100% | 35 |
| Decisão final correta (resolvido / revisão / inválido) | 76,7% | 60 |
| **Erro grave**: resposta automática sobre o serviço errado | **0 de 35** | 35 |
| Erro seguro: revisão humana desnecessária | 8 | 60 |

Leitura: o robô erra para o lado seguro. Os 14 erros de decisão são de dois tipos:
- **8 revisões desnecessárias** — pedidos com confiança abaixo de 0,45. Seis tinham o serviço certo
  (ex.: um pedido de salário-maternidade rural com confiança 0,19); dois eram
  pedidos de CPF confundidos com BPC e CAF, mas como a confiança era baixa nenhum recebeu resposta errada.
- **6 pedidos ambíguos resolvidos automaticamente** — Garantia-Safra × Pronaf, CAF × Pronaf,
  Cadastro Único × Bolsa Família, aposentadoria rural × BPC. O classificador escolheu um dos dois serviços
  plausíveis com confiança entre 0,48 e 0,64. Não houve erro grave, mas o agricultor recebeu a orientação de
  um programa só. É a principal fraqueza do robô: no semiárido esses programas andam juntos (sem CAF não há
  Garantia-Safra nem Pronaf), e o ideal seria responder sobre os dois.

**Limiar de confiança.** Simulando outros limiares sobre as confianças registradas: com 0,30 a decisão
correta subiria para 78,3% e continuaria sem erro grave; com 0,20 aparece o primeiro erro grave. Mantivemos
0,45, escolhido antes do teste: mudar o limiar olhando o próprio conjunto de teste seria ajustar a métrica ao
teste. O certo seria calibrar num conjunto de validação separado (trabalho futuro).

**Limites.** Amostra pequena (60), dados sintéticos escritos pelo grupo, documentos gerados por computador
(mais limpos que fotos reais de celular; o OCR deve piorar em uso real) e classificador treinado em frases que
compartilham modelos de escrita (a validação cruzada de 98% é otimista; o número honesto é o do teste
separado, 93,8%).

## 3. Falhas tratadas e demonstradas

| Falha | Como foi provocada | O que o robô fez |
|---|---|---|
| JSON corrompido (2) | REQ-0027 (aspas simples e vírgula sobrando) e REQ-0040 (truncado) | rejeitados com motivo no log, movidos para `failed/` com `.motivo.txt`, execução seguiu |
| Campo obrigatório vazio (2) | REQ-0002 sem `texto`, REQ-0056 com `texto` vazio | idem |
| Anexo ausente / fora da inbox (2) | REQ-0038 cita arquivos inexistentes; REQ-0019 tenta ler `../../segredos/cpf.png` | tratados como inválidos; o caminho para fora da inbox é bloqueado |
| Anexo ilegível (5) | documentos com desfoque, pixelização, ruído, rotação e baixo contraste | OCR devolve texto insuficiente → revisão humana (5 de 5) |
| gov.br fora do ar | `python run_robot.py --offline` | os 9 serviços vieram do cache, com a data da coleta original |
| Reenvio da mesma solicitação | os 60 pedidos reenviados na mesma inbox | 54 pulados como duplicados (hash do arquivo); os 6 inválidos rejeitados de novo |
| Erro na API do Gemini | `GEMINI_API_KEY` inválida | Gemini respondeu 400; o robô registrou `llm_erro:erro_api_400` e respondeu pelo template com os dados da Carta |
| Chave do Gemini ausente | sem `.env` | resposta pelo template (`llm_indisponivel`) |

Trechos do log (`logs/robot.log`):

```
WARNING | robo.inbox | Solicitação rejeitada (REQ-0027.json): JSON malformado (linha 1, coluna 2): Expecting property name enclosed in double quotes
WARNING | robo.inbox | Solicitação rejeitada (REQ-0002.json): campo obrigatório ausente ou vazio: texto (REQ-0002)
ERROR   | robo.run | REQ-0019 inválida: nenhum dos anexos declarados foi encontrado: ../../segredos/cpf.png
INFO    | robo.collector | Coleta concluída: atualizados=0 inalterados=9 falhas=[] usou_cache=['garantia_safra', 'caf', 'pronaf', ...]
INFO    | robo.run | ===== Execução 20261105-143028 concluída: {'lidas': 60, 'invalidas': 6, 'resolvidas': 0, 'revisao_humana': 0, 'falhas': 0, 'puladas_duplicadas': 54} =====
ERROR [citizen_rag.llm] Gemini erro 400: 400 INVALID_ARGUMENT. ... 'API key not valid. ...'
```

## 4. Testes automáticos

- `python -m unittest discover -s tests` (RPA): 30 testes, todos passam — coletor (parsers, cache,
  idempotência, retry só em erro temporário, offline sem rede), IA/documentos (PII, inbox, classificador, OCR
  dos tipos rurais), gerador de dados sintéticos e localização dos pedidos na planilha.
- `scripts/medir_ocr_sintetico.py`: identificação de tipo de documento nos anexos de teste (seção 2).
- `genAI/tests`: 46 testes do assistente RAG, todos passam.
