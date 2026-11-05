# Contratos entre módulos (referência interna de desenvolvimento)

Pacote Python do robô: `robo/` (em `RPA/`). Pacote do RAG: `citizen_rag/` (em `genAI/`).
Os nomes são diferentes de propósito, para o robô importar o RAG sem colisão.
Reutilizar sempre `robo.resilience` (get_logger, retry, safe_call) e `robo.config` (load_config, path, services, service_by_id, env).

## Corpus — `RPA/output/corpus/servicos.jsonl` (um JSON por linha, um por serviço)
```json
{
  "id": "garantia_safra",
  "service_id": "garantia_safra",
  "titulo": "Acessar o Benefício Garantia-Safra",
  "orgao": "Ministério do Desenvolvimento Agrário e Agricultura Familiar",
  "url": "https://www.gov.br/pt-br/servicos/...",
  "data_coleta": "2026-11-05T14:30:00-03:00",
  "fonte": "api" | "html" | "cache",
  "content_hash": "sha256 do texto_completo",
  "secoes": {
    "descricao": "...", "requisitos": "...", "documentos": "...",
    "etapas": "...", "canais": "...", "prazos": "...", "custos": "..."
  },
  "texto_completo": "texto limpo da carta inteira"
}
```
Seções ausentes ficam como string vazia. Conteúdo é público (gov.br).

## Solicitação na inbox — `RPA/inbox/<request_id>.json`
```json
{
  "request_id": "REQ-0001",
  "data_envio": "2026-11-05T10:00:00-03:00",
  "nome": "Nome Fictício",
  "email": "ficticio@exemplo.com",
  "cpf": "000.000.000-00",          // opcional, sempre fictício
  "municipio": "Petrolina",          // opcional
  "uf": "PE",                       // opcional
  "cod_ibge": "2611101",             // opcional, código como texto
  "texto": "A chuva não veio e perdi meu roçado. Como peço o garantia safra?",
  "anexos": ["anexos/REQ-0001_rg.png"]   // relativos à pasta inbox/
}
```
Rótulos (para avaliação, não ficam na inbox): `RPA/data/synthetic/labels.csv`
colunas: `request_id,service_id,docs_presentes,docs_ilegiveis,resultado_esperado,categoria,observacao,municipio,uf,cod_ibge`
(`docs_presentes`/`docs_ilegiveis` separados por `;`; `resultado_esperado` ∈ {resolvido, revisao_humana, invalido};
`categoria` ∈ {tipico, docs_faltando, ambiguo, fora_escopo, ilegivel, invalido}).

`municipio`, `uf` e `cod_ibge` são opcionais e independentes na inbox: ausentes, nulos ou
em branco viram `""` em `Request`; valores informados são convertidos para texto e aparados.
O código IBGE deve ser fornecido como string para preservar sua representação. A inbox não
valida pertencimento ao semiárido. O gerador sorteia os três campos juntos da mesma linha de
`data/municipios_semiarido.csv`, com pesos 8, 5, 3, 2 para as quatro primeiras linhas e 1
para as demais. O endereço dos documentos acompanha o município sorteado. Mesmo os casos
de JSON malformado mantêm localização no gabarito.

Treino: `treino_classificador.csv` tem `texto,service_id`, 40 frases por serviço ativo em
`config.yaml` mais 40 de `fora_escopo`. Teste: 60 pedidos com textos próprios, separados dos
modelos de treino: 25 `tipico`, 12 `docs_faltando`, 6 `ambiguo`, 6 `fora_escopo`, 5 `ilegivel`
e 6 `invalido`. `tipico` e `docs_faltando` esperam `resolvido`; `ambiguo`, `fora_escopo` e
`ilegivel` esperam `revisao_humana`; `invalido` espera `invalido`. A observação de ambíguos
contém `alternativa=<service_id>`. Requisitos e tipos de documentos vêm do config em execução.

## Planilha de controle — `RPA/output/controle.xlsx`

- `solicitacoes`: `run_id,request_id,data_envio,service_id,confianca,segunda_opcao,decisao,motivo,docs_presentes,docs_faltantes,docs_ilegiveis,anexos_ausentes,fonte_resposta,motivo_fallback,eml,tempo_s,municipio,uf,cod_ibge`.
- `revisao_humana`: `run_id,request_id,motivo,service_id,confianca,status,municipio,uf,cod_ibge`.
- `execucoes`: `run_id,inicio,fim,lidas,invalidas,resolvidas,revisao_humana,falhas,puladas_duplicadas,corpus_atualizados,corpus_cache,corpus_falhas`.
- `invalidas`: `run_id,arquivo,motivo`.

Localização é copiada da solicitação, inclusive em falhas encaminhadas para revisão. Campos
vazios aparecem como células vazias; `cod_ibge` preenchido é texto. Listas de documentos são
serializadas com `; `. Ao abrir planilhas antigas, colunas ausentes são acrescentadas ao fim,
preservando os dados e a ordem das colunas existentes. Linhas são atualizadas por `request_id`
(`run_id` em `execucoes`, `arquivo` em `invalidas`).

## Interfaces Python
- `robo.inbox.load_requests(inbox_dir) -> tuple[list[Request], list[InvalidItem]]`
  - `Request`: dataclass com campos do JSON + `source_path: Path` + `anexos_abs: list[Path]`
  - `InvalidItem`: `source_path`, `reason`
- `robo.privacy.mask_pii(text: str) -> str` (CPF, e-mail, telefone, RG → `[CPF]`, `[EMAIL]`, `[TELEFONE]`, `[RG]`)
- `robo.classifier.train(labels_csv=None, out_path=None) -> dict(metricas)`;
  `robo.classifier.predict(text) -> tuple[str | None, float]` (service_id ou `"fora_escopo"`, confiança)
  - O treino deve conter todas e somente as classes ativas do config mais `fora_escopo`;
    divergência gera `ValueError` com as classes ausentes/desconhecidas. Modelos persistidos
    de outro catálogo são descartados em memória e o carregamento tenta treinar novamente;
    falhas de predição continuam retornando `(None, 0.0)`.
- `robo.ocr.extract_text(path) -> OcrResult(text, method, ok, error)`
- `robo.ocr.identify_doc_type(text) -> tuple[str | None, float]` (tipo canônico de `document_types`)
- `robo.ocr.check_documents(attachments: list[Path], required: list[str]) -> DocCheck(presentes, faltantes, ilegiveis, detalhes)`
- `robo.collector.update_corpus() -> CollectResult(atualizados, inalterados, falhas, usou_cache)`
- RAG: `citizen_rag.rag.RAGAssistant(corpus_path=None).answer(question, history=None, service_id=None) -> dict`
  com chaves `answer: str`, `citations: list[{n, service_id, titulo, url, secao}]`, `abstained: bool`,
  `reason: str | None`, `chunks: list[{id, text, score, metadata}]`, `blocked: bool`.
  Nunca lança exceção para erro de LLM: devolve `abstained=True`/`reason` e o robô cai no template.
