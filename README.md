# CitizenTech — Robô de pré-triagem de serviços públicos (RPA + IA)

Global Solution 2026.2 · FIAP · AI for Robotic Process Automation

## Integrantes

| Nome completo | RM |
|---|---|
| _preencher_ | _preencher_ |
| _preencher_ | _preencher_ |
| _preencher_ | _preencher_ |

## Problema

Quem precisa de um serviço federal (seguro-desemprego, Cadastro Único, BPC, passaporte, CPF…) muitas vezes
não sabe o nome oficial do serviço, quais documentos levar, por onde pedir e em quanto tempo sai. O resultado
é pedido incompleto, viagem perdida ao atendimento e retrabalho para o órgão — e quem mais sofre é justamente
o público dos benefícios sociais.

O robô faz a **pré-triagem**: lê a solicitação escrita do jeito do cidadão, identifica o serviço, confere os
documentos anexados contra os exigidos na **Carta de Serviço oficial do gov.br**, e devolve por e-mail o que
falta, onde pedir e o prazo, citando a fonte. O que ele não resolve com segurança vai para revisão humana.

## Fluxo

```
gov.br (API + HTML) ─► 1. coleta das Cartas de Serviço ─► corpus (também usado pelo assistente de IA generativa)
inbox/*.json ─► 2. validação ─► 3. máscara de dados pessoais ─► 4. classificação do serviço (ML)
            ─► 5. OCR dos anexos + conferência de documentos ─► 6. resposta (RAG/Gemini ou template)
            ─► 7. e-mail .eml + controle.xlsx + relatório ─► processed/ | failed/ | revisão humana
```

### Parte da solução CitizenTech
| Repositório | Disciplina | Papel |
|---|---|---|
| **`citizentech-rpa`** (este) | AI for RPA | coleta das Cartas de Serviço e pré-triagem dos pedidos |
| `citizentech-genai` | Generative AI | assistente RAG que redige as respostas (etapa 6) e responde no chat |
| `citizentech-dashboard` | Front-end | painel de decisão do gestor |

O corpus coletado aqui (`output/corpus/servicos.jsonl`) é a base de conhecimento do assistente; o formato
está em [CONTRACTS.md](CONTRACTS.md).

Temas da disciplina e onde cada um entra: [docs/quadro_temas.md](docs/quadro_temas.md).
Proteção de dados, ética e ODS: [docs/etica_ods.md](docs/etica_ods.md).
Evidências de validação: [docs/evidencias.md](docs/evidencias.md).

## Como executar

Requisitos: Python 3.11+ (testado no 3.14, Windows 11). Não precisa instalar nada além do `pip`
(o OCR usa RapidOCR; o Tesseract é opcional).

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-integracao.txt   # opcional: assistente RAG (repositório citizentech-genai clonado em ../genAI)
```
Sem o assistente instalado o robô funciona do mesmo jeito e responde por template.

Gerar os dados sintéticos e rodar o robô no conjunto de teste:

```bash
python scripts/gerar_dados_sinteticos.py
python run_robot.py --carregar-teste
python eval/avaliar_robo.py
```

Interface (enviar solicitação, painel do robô e chat do assistente):

```bash
streamlit run app/streamlit_app.py
```

Opções de `run_robot.py`: `--offline` (simula o gov.br fora do ar e usa o cache), `--sem-genai` (só template),
`--sem-coleta` (não atualiza a base nesta execução). Ajustes (limiares, timeouts, caminhos, catálogo de
serviços) ficam em [config.yaml](config.yaml).

### Chaves

Copie `.env.example` para `.env` e preencha `GEMINI_API_KEY` (gratuita em https://aistudio.google.com/apikey).
O `.env` está no `.gitignore` e nunca vai para o repositório. Sem a chave o robô funciona normalmente e
responde por template; envio real de e-mail (SMTP) é opcional e desligado por padrão (`email.send: false`).

## Saídas

| Onde | O quê |
|---|---|
| `outbox/<id>.eml` | resposta ao cidadão (abre no Outlook/Thunderbird) |
| `output/controle.xlsx` | abas `solicitacoes`, `revisao_humana`, `execucoes`, `invalidas` |
| `output/relatorios/relatorio_<execução>.md` | resumo de cada execução |
| `output/corpus/servicos.jsonl` | Cartas de Serviço coletadas (URL e data de coleta) |
| `logs/robot.log` | log de todas as etapas |
| `processed/`, `failed/` | solicitações já tratadas / rejeitadas (com `.motivo.txt`) |

## Resultados (60 solicitações sintéticas rotuladas)

Classificação do serviço 95,8% · conferência de documentos 100% · decisão final 81,7% ·
**0 respostas automáticas sobre o serviço errado** em 34 · 7 revisões humanas desnecessárias.
Detalhes, limites e falhas demonstradas em [docs/evidencias.md](docs/evidencias.md).

## Estrutura

```
run_robot.py          ponto de entrada
robo/                 collector, inbox, privacy, classifier, ocr, responder, outputs, resilience, config
app/                  interface Streamlit
scripts/              gerador de dados sintéticos
data/synthetic/       treino do classificador, inbox de teste e rótulos
eval/                 avaliação do robô
tests/                testes automáticos (python -m unittest discover -s tests)
docs/                 quadro de temas, ética/ODS, evidências
```

Todos os dados pessoais do projeto são fictícios. O conteúdo das Cartas de Serviço é público (gov.br).
