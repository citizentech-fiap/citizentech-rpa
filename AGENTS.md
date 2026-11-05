# Regras do projeto para agentes de código

Repositório `citizentech-rpa` — robô de pré-triagem de pedidos de agricultores familiares do semiárido
(FIAP Global Solution 2026.2, disciplina AI for RPA). Faz parte da solução CitizenTech, junto com
`citizentech-genai` (pasta irmã `../genAI`) e `citizentech-dashboard` (`../dashboard`).

## Convenções
- Código, comentários, logs, docs e dados sintéticos em **português do Brasil**.
- Python do ambiente: `..\.venv\Scripts\python.exe` (Windows). Não instale pacotes novos sem necessidade;
  se instalar, adicione em `requirements.txt`.
- Reutilize `robo.resilience` (`get_logger`, `retry`, `safe_call`) e `robo.config`
  (`load_config`, `path`, `services`, `service_by_id`). Nada de `print` para log.
- Catálogo de serviços e tipos de documento: **sempre lidos de `config.yaml`** (`services`,
  `document_types`); não fixe listas no código.
- Formatos de dados e interfaces entre módulos: `CONTRACTS.md`. Mudou um contrato? Atualize o arquivo.
- Falhas previsíveis nunca derrubam a execução: registre no log e siga por um caminho seguro.
- Dados: apenas sintéticos ou públicos. Nenhum dado pessoal real; documentos fictícios trazem
  "DOCUMENTO FICTÍCIO - USO ACADÊMICO". CPFs sintéticos com dígito verificador inválido.
- Nunca leia, grave ou exiba o conteúdo de `.env`; chaves ficam fora do código.

## Antes de terminar
- Rode os testes: `..\.venv\Scripts\python -m unittest discover -s tests -q` (todos devem passar).
- Mexa só nos arquivos que a tarefa pede. Não faça commit nem push: quem revisa e faz commit é o humano.
- Termine com um relatório curto: arquivos alterados, comandos rodados e resultados, decisões, pendências.
