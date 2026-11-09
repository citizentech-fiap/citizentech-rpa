# Calibração de ambiguidade — validação separada

Semente 20261109; textos próprios em scripts/textos_validacao.py; mesmos gerador e documentos sintéticos.
Amostra: 27 típicos e 12 ambíguos. Sobreposição exata normalizada com treino: 0; com teste: 0.
Verificação de sobreposição não utiliza rótulos nem previsões do teste. Não garante independência semântica.
Confiança mínima mantida em 0,45. Revisão inclui escopo/confiança e o sinal candidato, sem OCR.
Objetivo pré-definido: menor média entre taxa de ambíguos perdidos e taxa de típicos revisados; empate favorece menos típicos revisados e menor limiar.

| Sinal | Limiar (<) | Ambíguos revisados | Típicos revisados | Erro balanceado |
|---|---|---|---|---|
| margem | 0.15 | 4/12 | 2/27 | 0.3704 |
| margem | 0.20 | 5/12 | 2/27 | 0.3287 |
| margem | 0.25 | 5/12 | 2/27 | 0.3287 |
| margem | 0.30 | 7/12 | 2/27 | 0.2454 |
| margem | 0.35 | 7/12 | 2/27 | 0.2454 |
| margem | 0.40 | 8/12 | 2/27 | 0.2037 |
| margem | 0.45 | 9/12 | 3/27 | 0.1806 |
| margem | 0.50 | 9/12 | 5/27 | 0.2176 |
| razao | 1.50 | 4/12 | 2/27 | 0.3704 |
| razao | 2.00 | 5/12 | 2/27 | 0.3287 |
| razao | 2.50 | 7/12 | 2/27 | 0.2454 |
| razao | 3.00 | 8/12 | 2/27 | 0.2037 |
| razao | 3.50 | 9/12 | 2/27 | 0.1620 |
| razao | 4.00 | 9/12 | 2/27 | 0.1620 |
| razao | 5.00 | 9/12 | 3/27 | 0.1806 |

Escolha congelada antes da avaliação do teste: **razao < 3.50**; erro balanceado 0.1620.
Limites: amostra pequena e sintética; várias frases explícitas, sem representar toda a linguagem real. Não se promete recuperar todos os ambíguos do teste.
