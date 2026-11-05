# Contratos entre módulos (referência interna de desenvolvimento)

Pacote Python do robô: `robo/` (em `RPA/`). Pacote do RAG: `citizen_rag/` (em `genAI/`).
Os nomes são diferentes de propósito, para o robô importar o RAG sem colisão.
Reutilizar sempre `robo.resilience` (get_logger, retry, safe_call) e `robo.config` (load_config, path, services, service_by_id, env).

## Corpus — `RPA/output/corpus/servicos.jsonl` (um JSON por linha, um por serviço)
```json
{
  "id": "seguro_desemprego",
  "service_id": "seguro_desemprego",
  "titulo": "Solicitar o Seguro-Desemprego",
  "orgao": "Ministério do Trabalho e Emprego",
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
  "texto": "Fui demitido semana passada, como peço o seguro?",
  "anexos": ["anexos/REQ-0001_rg.png"]   // relativos à pasta inbox/
}
```
Rótulos (para avaliação, não ficam na inbox): `RPA/data/synthetic/labels.csv`
colunas: `request_id,service_id,docs_presentes,docs_ilegiveis,resultado_esperado,categoria,observacao`
(`docs_presentes`/`docs_ilegiveis` separados por `;`; `resultado_esperado` ∈ {resolvido, revisao_humana, invalido};
`categoria` ∈ {tipico, docs_faltando, ambiguo, fora_escopo, ilegivel, invalido}).

## Interfaces Python
- `robo.inbox.load_requests(inbox_dir) -> tuple[list[Request], list[InvalidItem]]`
  - `Request`: dataclass com campos do JSON + `source_path: Path` + `anexos_abs: list[Path]`
  - `InvalidItem`: `source_path`, `reason`
- `robo.privacy.mask_pii(text: str) -> str` (CPF, e-mail, telefone, RG → `[CPF]`, `[EMAIL]`, `[TELEFONE]`, `[RG]`)
- `robo.classifier.train(labels_csv=None, out_path=None) -> dict(metricas)`;
  `robo.classifier.predict(text) -> tuple[str | None, float]` (service_id ou `"fora_escopo"`, confiança)
- `robo.ocr.extract_text(path) -> OcrResult(text, method, ok, error)`
- `robo.ocr.identify_doc_type(text) -> tuple[str | None, float]` (tipo canônico de `document_types`)
- `robo.ocr.check_documents(attachments: list[Path], required: list[str]) -> DocCheck(presentes, faltantes, ilegiveis, detalhes)`
- `robo.collector.update_corpus() -> CollectResult(atualizados, inalterados, falhas, usou_cache)`
- RAG: `citizen_rag.rag.RAGAssistant(corpus_path=None).answer(question, history=None, service_id=None) -> dict`
  com chaves `answer: str`, `citations: list[{n, service_id, titulo, url, secao}]`, `abstained: bool`,
  `reason: str | None`, `chunks: list[{id, text, score, metadata}]`, `blocked: bool`.
  Nunca lança exceção para erro de LLM: devolve `abstained=True`/`reason` e o robô cai no template.
