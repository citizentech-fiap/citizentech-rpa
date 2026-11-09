# Evidências de validação

As execuções abaixo usam o conjunto sintético rotulado (`data/synthetic/labels.csv`, 60 pedidos de
agricultores de 23 municípios do semiárido) e as 9 Cartas de Serviço coletadas do gov.br em 05/11/2026.
A primeira rodada foi em 05/11/2026; a segunda, em 09/11/2026, depois das correções descritas nas seções 2 e 3
(ambiguidade calibrada em validação separada, timeout do LLM, fechamento da fila de revisão, envio SMTP). Os números completos, a matriz de confusão e a lista de erros estão
em [`eval/resultados_robo.md`](../eval/resultados_robo.md).

**Honestidade do teste.** Os pedidos de teste foram escritos com modelos de frase e vocabulário diferentes
dos de treino: nenhum pedido repete uma frase de treino, e a sobreposição de sequências de 4 palavras entre
teste e treino é 0%.

## 1. Execução contínua de ponta a ponta

`python run_robot.py --carregar-teste` processou os 60 pedidos em uma única execução, sem intervenção, em
cerca de 3 minutos (o OCR leva ~1,3 s por imagem):

| rodada | lidas | inválidas | resolvidas | revisão humana | falhas |
|---|---|---|---|---|---|
| 05/11 | 60 | 6 | 35 | 19 | 0 |
| 09/11 | 60 | 6 | 29 | 25 | 0 |

A diferença está nos pedidos ambíguos, que agora vão para revisão humana (seção 2).

## 2. Resultado medido

| Métrica | 05/11 | 09/11 | n |
|---|---|---|---|
| Classificador: validação cruzada no treino (5 dobras) | 98,0% (F1 macro 0,98) | — (sem retreino) | 400 |
| Classificação do serviço correta no teste (texto livre) | 93,8% | 93,8% | 48 |
| Pedido fora de escopo encaminhado para revisão humana | 100% | 100% | 6 |
| OCR: tipo de documento identificado nos anexos legíveis | 100% (123 de 123) | — (OCR inalterado) | 123 |
| OCR: anexos degradados rejeitados como ilegíveis | 100% (5 de 5) | 100% (5 de 5) | 5 |
| Conferência de documentos correta (quando o serviço foi acertado) | 100% | 100% | 35 |
| **Pedido ambíguo encaminhado para revisão humana** | **0 de 6** | **5 de 6** | 6 |
| Decisão final correta (resolvido / revisão / inválido) | 76,7% | **83,3%** (50 de 60) | 60 |
| **Erro grave**: resposta automática sobre o serviço errado | **0 de 35** | **0 de 29** | — |
| Erro seguro: revisão humana desnecessária | 8 | 9 | 60 |

Leitura: o robô erra para o lado seguro. Na rodada de 05/11, os 14 erros de decisão eram 8 revisões
desnecessárias (confiança abaixo de 0,45; dois eram pedidos de CPF confundidos com BPC e CAF, mas sem resposta
errada) e **6 pedidos ambíguos resolvidos automaticamente** — Garantia-Safra × Pronaf, CAF × Pronaf,
Cadastro Único × Bolsa Família, aposentadoria rural × BPC. O agricultor recebia a orientação de um programa só,
e no semiárido esses programas andam juntos (sem CAF não há Garantia-Safra nem Pronaf).

**Correção: ambiguidade calibrada em validação separada.** A regra antiga (diferença entre a 1ª e a 2ª
probabilidade menor que 0,15) não pegava nenhum dos seis. Para não ajustar a regra olhando o teste, criamos um
**conjunto de validação** com o mesmo gerador e outra semente (`python scripts/gerar_dados_sinteticos.py
--validacao`: 39 pedidos, 27 típicos e 12 ambíguos, textos próprios em `scripts/textos_validacao.py`, nenhum
texto igual aos de treino ou teste). `eval/calibrar_ambiguidade.py` comparou a diferença e a **razão** entre as
duas maiores probabilidades ([tabela](../eval/calibracao_ambiguidade.md)). A razão p1/p2 < 3,5 encaminhou 9 de
12 ambíguos e só 2 de 27 típicos; a melhor diferença (< 0,45) pegou os mesmos 9, mas revisou 3 típicos. O
limiar ficou congelado em `config.yaml` (`classifier.min_ratio`) **antes** de rodar o teste, que foi avaliado
uma única vez. O limiar de confiança (0,45) continuou o mesmo.

No teste, 5 dos 6 ambíguos passaram a ir para revisão humana. Ficou de fora o REQ-0011 (Pronaf × Garantia-Safra,
confiança 0,64), que recebe a orientação correta do Pronaf, mas sem mencionar o Garantia-Safra; e houve uma
revisão desnecessária a mais (REQ-0016, aposentadoria rural). Não mexemos no limiar depois de ver esses
resultados. Os outros 9 erros são revisões desnecessárias: erros para o lado seguro.

**Limites.** Amostra pequena (60), dados sintéticos escritos pelo grupo, documentos gerados por computador
(mais limpos que fotos reais de celular; o OCR deve piorar em uso real) e classificador treinado em frases que
compartilham modelos de escrita (a validação cruzada de 98% é otimista; o número honesto é o do teste
separado, 93,8%). A validação de ambiguidade também é pequena e sintética: texto diferente não garante que o
sentido seja independente do teste.

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
| genAI não instalado / pasta `../genAI` ausente | teste com RAG indisponível | aviso `ATENÇÃO: RAG indisponível` no início da execução, colunas `rag_disponivel`/`motivo_rag` na aba `execucoes` e linha em negrito no relatório; respostas por template |
| LLM lento | teste com RAG falso que demora mais que `responder.llm_timeout_s` | para de esperar e responde pelo template (`timeout_rag`); o mesmo valor vai para o timeout do Gemini no genAI |
| RAG devolve vazio, se abstém, bloqueia ou lança erro | testes em `tests/test_responder.py` | template, com o motivo registrado em `motivo_fallback` |
| Servidor de e-mail fora do ar | teste com SMTP falso que falha | o `.eml` fica em `outbox/`, a planilha marca `status_email=falha` e a execução segue |
| Queda no meio da execução | registro de idempotência gravado a cada pedido (arquivo temporário + troca) | pedidos já respondidos não são reprocessados na execução seguinte |
| Pedido inválido ou duplicado com anexos | anexos na inbox | o JSON **e os anexos** vão para `failed/` (inválido) ou `processed/` (duplicado); o `.motivo.txt` é gravado dentro do `safe_call` |
| Nova execução depois de um atendente fechar um pedido | `tests/test_revisao.py` | o item fechado da fila de revisão não é reaberto nem sobrescrito |

Trechos do log (`logs/robot.log`):

```
WARNING | robo.inbox | Solicitação rejeitada (REQ-0027.json): JSON malformado (linha 1, coluna 2): Expecting property name enclosed in double quotes
WARNING | robo.inbox | Solicitação rejeitada (REQ-0002.json): campo obrigatório ausente ou vazio: texto (REQ-0002)
ERROR   | robo.run | REQ-0019 inválida: nenhum dos anexos declarados foi encontrado: ../../segredos/cpf.png
INFO    | robo.collector | Coleta concluída: atualizados=0 inalterados=9 falhas=[] usou_cache=['garantia_safra', 'caf', 'pronaf', ...]
INFO    | robo.run | ===== Execução 20261105-143028 concluída: {'lidas': 60, 'invalidas': 6, 'resolvidas': 0, 'revisao_humana': 0, 'falhas': 0, 'puladas_duplicadas': 54} =====
ERROR [citizen_rag.llm] Gemini erro 400: 400 INVALID_ARGUMENT. ... 'API key not valid. ...'
```

## 4. Fila de revisão humana: do encaminhamento ao fechamento

Todo pedido encaminhado entra na aba `revisao_humana` do `output/controle.xlsx` como `pendente`. O atendente
fecha pelo terminal ou pelo portal (`app/streamlit_app.py`, que usa a mesma função):

```powershell
..\.venv\Scripts\python -m robo.revisao --listar
..\.venv\Scripts\python -m robo.revisao --fechar REQ-0011 --desfecho respondido --responsavel "Atendente" --observacao "Orientado sobre Pronaf e Garantia-Safra"
```

O fechamento grava `desfecho` (respondido, encaminhado ou indeferido), `responsavel` e `fechado_em`. Pedido
inexistente ou já fechado gera mensagem clara e código de saída 1, sem alterar a planilha. As colunas novas
foram acrescentadas no fim, sem renomear as que o dashboard lê.

## 5. Execuções repetidas não alteram arquivos versionados

Duas execuções seguidas de `python run_robot.py --carregar-teste --offline --sem-genai` não modificaram nenhum
arquivo versionado (comparação SHA-256 antes e depois). O corpus e o cache das Cartas só são regravados quando o
conteúdo muda, e a data de coleta é preservada quando nada mudou. Saídas de execução (inbox, processados,
planilha, relatórios, logs) ficam fora do git.

## 6. Testes automáticos

- `python -m unittest discover -s tests` (RPA): 47 testes, todos passam — coletor (parsers, cache,
  idempotência, retry só em erro temporário, offline sem rede, sem regravação), IA/documentos (PII, inbox,
  classificador, OCR dos tipos rurais), gerador de dados sintéticos, localização dos pedidos na planilha,
  responder com RAG falso (vazio, exceção, abstenção, bloqueio, timeout, citações, aviso de indisponibilidade),
  fechamento da fila, SMTP falso (desligado, sucesso, sem TLS, falha preservando o rascunho), movimentação dos
  anexos e registro gravado a cada pedido.
- `scripts/medir_ocr_sintetico.py`: identificação de tipo de documento nos anexos de teste (seção 2).
- `genAI/tests`: 68 testes do assistente RAG, todos passam.
