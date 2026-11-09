# CitizenTech — Robô de pré-triagem para o agricultor familiar do semiárido (RPA + IA)

Global Solution 2026.2 · FIAP · AI for Robotic Process Automation

## Integrantes

| Nome completo | RM |
|---|---|
| Luís Fernando de Oliveira Salgado | RM561401 |
| Ricardo de Paiva Melo | RM565522 |
| Jonas Alaf | RM566479 |

## Problema

Quando a seca chega ao semiárido, o agricultor familiar perde a safra e precisa correr atrás de vários
benefícios ao mesmo tempo: Garantia-Safra, CAF (sem ele não há Garantia-Safra nem Pronaf), crédito do Pronaf,
Cadastro Único e Bolsa Família, aposentadoria e salário-maternidade rurais. Ele procura o sindicato rural, a
prefeitura ou a EMATER, muitas vezes depois de viajar quilômetros, e não sabe o nome oficial do programa,
quais documentos levar nem o prazo. O resultado é pedido incompleto, viagem perdida e atendimento sobrecarregado
justamente na pior hora.

O robô faz a **pré-triagem** desses pedidos: lê a solicitação escrita do jeito do agricultor, identifica o
serviço, confere os documentos anexados (inclusive o comprovante do CAF e o de posse da terra) contra os
exigidos na **Carta de Serviço oficial do gov.br**, e devolve por e-mail o que falta, onde pedir e o prazo,
citando a fonte. O que ele não resolve com segurança vai para revisão humana. Cada pedido carrega o município
de origem, o que alimenta o painel de decisão do gestor (repositório `citizentech-dashboard`).

Serviços atendidos (9): Garantia-Safra · CAF · Pronaf · aposentadoria por idade rural · salário-maternidade
rural · Cadastro Único · Bolsa Família · BPC · CPF. Lista, órgãos e documentos em [config.yaml](config.yaml).

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
git clone https://github.com/citizentech-fiap/citizentech-genai.git ../genAI
pip install -r requirements-integracao.txt   # opcional: assistente RAG (repositório citizentech-genai clonado em ../genAI)
```
Sem o assistente instalado o robô funciona do mesmo jeito e responde por template.
Também é possível instalar o clone com `pip install -e ../genAI`. Quando o RAG não carrega,
há um aviso único no início, campos `rag_disponivel`/`motivo_rag` na aba `execucoes` e uma linha
destacada no relatório. `--sem-genai` registra a escolha, sem aviso de falha.
`responder.llm_timeout_s` limita a espera por `rag.answer` e é repassado para `llm.timeout_s`
do genAI. Se expirar, usa template com `timeout_rag`. A thread em andamento não é interrompida;
o encerramento do processo pode aguardar sua conclusão (incluindo retries internos do genAI).

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

### Demonstrar SMTP e fechar a revisão

Para testar envio, abra um servidor SMTP local de testes (por exemplo, smtp4dev), escutando em
`localhost:1025`, sem autenticação e sem TLS. Em `config.yaml`, ajuste `email.send: true`,
`host: localhost`, `port: 1025`, `starttls: false` e `sender`. Envie uma solicitação sintética nova
pela interface e execute o robô: a mensagem aparecerá no servidor local e continuará em `outbox/`.
Para servidor autenticado, ative STARTTLS e forneça apenas pelas variáveis `SMTP_USER` e
`SMTP_PASSWORD` (nomes em `.env.example`). Ambos vazios permitem teste local sem login.
Falha SMTP mantém o rascunho, registra o erro e marca `status_email=falha` na planilha.
O padrão permanece sem envio; os testes automatizados substituem SMTP por um falso, sem rede.

```powershell
..\.venv\Scripts\python -m robo.revisao --listar
..\.venv\Scripts\python -m robo.revisao --fechar REQ-0011 --desfecho respondido --responsavel "Atendente Fictício" --observacao "Orientação prestada"
```

Use `--planilha caminho/controle_copia.xlsx` para testar numa cópia. Inexistente ou já fechado retorna
código 1, sem traceback. O painel Streamlit também permite fechar pendências. Uma nova execução não
reabre itens fechados; o desfecho humano permanece na aba `revisao_humana`.

## Saídas

| Onde | O quê |
|---|---|
| `outbox/<id>.eml` | resposta ao cidadão (abre no Outlook/Thunderbird) |
| `output/controle.xlsx` | abas `solicitacoes`, `revisao_humana`, `execucoes`, `invalidas` |
| `output/relatorios/relatorio_<execução>.md` | resumo de cada execução |
| `output/corpus/servicos.jsonl` | Cartas de Serviço coletadas (URL e data de coleta) |
| `logs/robot.log` | log de todas as etapas |
| `processed/`, `failed/` | solicitações já tratadas / rejeitadas (com `.motivo.txt`) |

## Resultados (solicitações sintéticas rotuladas)

60 pedidos de agricultores de 23 municípios do semiárido: classificação do serviço 93,8% · conferência
de documentos correta em 35/35 casos elegíveis · decisão final 83,3% · **0 respostas automáticas sobre
o serviço errado** em 29 · 9 revisões humanas desnecessárias · 5/6 ambíguos encaminhados.
Razão p1/p2 < 3,5 escolhida antes do teste em validação separada (9/12 ambíguos, 2/27 típicos revisados).
Tabela e método em [eval/calibracao_ambiguidade.md](eval/calibracao_ambiguidade.md). Detalhes e limites em
[docs/evidencias.md](docs/evidencias.md).

Para reproduzir a validação: `python scripts/gerar_dados_sinteticos.py --validacao` e
`python eval/calibrar_ambiguidade.py`. A avaliação aceita `--planilha caminho/controle.xlsx`.
Use uma execução nova, sem registros antigos de duplicados, para avaliar os 60 pedidos.
Resultados de `eval/`, corpus e cache são evidências versionadas; logs, planilhas e saídas operacionais
são ignorados. O coletor evita regravar conteúdo idêntico.

## Estrutura

```
run_robot.py          ponto de entrada
robo/                 collector, inbox, privacy, classifier, ocr, responder, outputs, resilience, config
app/                  interface Streamlit
scripts/              gerador de dados sintéticos
data/synthetic/       treino do classificador, inbox de teste e rótulos
data/municipios_semiarido.csv   23 municípios do semiárido (código IBGE e coordenadas)
eval/                 avaliação do robô
tests/                testes automáticos (python -m unittest discover -s tests)
docs/                 quadro de temas, ética/ODS, evidências
```

Todos os dados pessoais do projeto são fictícios. O conteúdo das Cartas de Serviço é público (gov.br).

Licença do código: [MIT](LICENSE), 2026, Luís Fernando de Oliveira Salgado, Ricardo de Paiva Melo e Jonas Alaf.
