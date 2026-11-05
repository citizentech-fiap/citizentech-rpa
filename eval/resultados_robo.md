# Avaliação do robô — conjunto de teste sintético rotulado

Amostra: **60 solicitações** (tipico: 25, docs_faltando: 12, invalido: 6, fora_escopo: 6, ambiguo: 6, ilegivel: 5).

| Métrica | Resultado | n |
|---|---|---|
| Acurácia da classificação do serviço (exceto inválidas e fora de escopo) | 93.8% | 48 |
| Fora de escopo encaminhado para revisão humana | 100.0% | 6 |
| Conferência de documentos correta (OCR, quando o serviço foi acertado) | 100.0% | 35 |
| Decisão final correta (resolvido / revisão humana / inválido) | 76.7% | 60 |
| **Erro grave**: resposta automática sobre o serviço errado | 0 de 35 respostas automáticas (0.0%) | 35 |
| Erro seguro: revisão humana desnecessária | 8 | 60 |

Pedidos ambíguos: qualquer um dos dois serviços plausíveis conta como acerto de classificação, mas a decisão esperada é revisão humana.

## Efeito do limiar de confiança (simulado sobre as confianças registradas)

| limiar | respostas automáticas | erros graves | revisões desnecessárias | decisão correta |
|---|---|---|---|---|
| 0.20 | 39 | 1 | 6 | 76.7% |
| 0.30 | 38 | 0 | 6 | 78.3% |
| 0.35 | 37 | 0 | 7 | 76.7% |
| 0.40 | 37 | 0 | 7 | 76.7% |
| 0.45 | 35 | 0 | 8 | 76.7% |
| 0.50 | 31 | 0 | 11 | 73.3% |
| 0.60 | 25 | 0 | 13 | 76.7% |

## Decisão por categoria

| categoria     |   acerto |     n |
|:--------------|---------:|------:|
| ambiguo       |     0.00 |  6.00 |
| docs_faltando |     0.92 | 12.00 |
| fora_escopo   |     1.00 |  6.00 |
| ilegivel      |     1.00 |  5.00 |
| invalido      |     1.00 |  6.00 |
| tipico        |     0.72 | 25.00 |

## Matriz de confusão da classificação

| servico_real              |   aposentadoria_rural |   bolsa_familia |   bpc |   cadunico |   caf |   cpf |   garantia_safra |   pronaf |   salario_maternidade_rural |
|:--------------------------|----------------------:|----------------:|------:|-----------:|------:|------:|-----------------:|---------:|----------------------------:|
| aposentadoria_rural       |                     5 |               0 |     1 |          0 |     0 |     0 |                0 |        0 |                           0 |
| bolsa_familia             |                     0 |               4 |     0 |          1 |     0 |     0 |                0 |        0 |                           0 |
| bpc                       |                     0 |               0 |     3 |          0 |     0 |     0 |                0 |        0 |                           0 |
| cadunico                  |                     0 |               1 |     0 |          4 |     0 |     0 |                0 |        0 |                           0 |
| caf                       |                     0 |               0 |     0 |          0 |     6 |     0 |                0 |        1 |                           0 |
| cpf                       |                     0 |               0 |     1 |          0 |     1 |     1 |                0 |        0 |                           0 |
| garantia_safra            |                     0 |               0 |     0 |          0 |     0 |     0 |                6 |        1 |                           0 |
| pronaf                    |                     0 |               0 |     0 |          0 |     0 |     0 |                0 |        7 |                           0 |
| salario_maternidade_rural |                     0 |               0 |     0 |          0 |     0 |     0 |                0 |        0 |                           5 |

## Erros

| request_id   | categoria     | servico_real              | servico_previsto          |   confianca | decisao_esperada   | decisao        | docs_esperados                                       | docs_previstos                                       |
|:-------------|:--------------|:--------------------------|:--------------------------|------------:|:-------------------|:---------------|:-----------------------------------------------------|:-----------------------------------------------------|
| REQ-0011     | ambiguo       | pronaf                    | pronaf                    |      0.6356 | revisao_humana     | resolvido      | nan                                                  | nan                                                  |
| REQ-0012     | ambiguo       | cadunico                  | bolsa_familia             |      0.5766 | revisao_humana     | resolvido      | nan                                                  | nan                                                  |
| REQ-0015     | tipico        | cadunico                  | cadunico                  |      0.3771 | resolvido          | revisao_humana | comprovante_residencia;cpf;documento_identidade      | comprovante_residencia;cpf;documento_identidade      |
| REQ-0018     | tipico        | cpf                       | bpc                       |      0.2591 | resolvido          | revisao_humana | nan                                                  | nan                                                  |
| REQ-0021     | tipico        | garantia_safra            | garantia_safra            |      0.3139 | resolvido          | revisao_humana | caf;cpf;documento_identidade                         | caf;cpf;documento_identidade                         |
| REQ-0034     | tipico        | pronaf                    | pronaf                    |      0.3703 | resolvido          | revisao_humana | caf;comprovante_posse_terra;cpf;documento_identidade | caf;comprovante_posse_terra;cpf;documento_identidade |
| REQ-0037     | tipico        | salario_maternidade_rural | salario_maternidade_rural |      0.1897 | resolvido          | revisao_humana | cpf;documento_identidade                             | cpf;documento_identidade                             |
| REQ-0039     | tipico        | salario_maternidade_rural | salario_maternidade_rural |      0.4207 | resolvido          | revisao_humana | cpf;documento_identidade                             | cpf;documento_identidade                             |
| REQ-0045     | ambiguo       | aposentadoria_rural       | aposentadoria_rural       |      0.563  | revisao_humana     | resolvido      | nan                                                  | nan                                                  |
| REQ-0046     | tipico        | cpf                       | caf                       |      0.2823 | resolvido          | revisao_humana | nan                                                  | nan                                                  |
| REQ-0048     | ambiguo       | bolsa_familia             | cadunico                  |      0.524  | revisao_humana     | resolvido      | nan                                                  | nan                                                  |
| REQ-0051     | ambiguo       | caf                       | pronaf                    |      0.4808 | revisao_humana     | resolvido      | nan                                                  | nan                                                  |
| REQ-0054     | docs_faltando | caf                       | caf                       |      0.349  | resolvido          | revisao_humana | comprovante_posse_terra;comprovante_renda            | comprovante_posse_terra;comprovante_renda            |
| REQ-0060     | ambiguo       | garantia_safra            | pronaf                    |      0.5438 | revisao_humana     | resolvido      | nan                                                  | nan                                                  |
