# Avaliação do robô — conjunto de teste sintético rotulado

Amostra: **60 solicitações** (tipico: 25, docs_faltando: 12, invalido: 6, fora_escopo: 6, ambiguo: 6, ilegivel: 5).

| Métrica | Resultado | n |
|---|---|---|
| Acurácia da classificação do serviço (exceto inválidas e fora de escopo) | 95.8% | 48 |
| Fora de escopo encaminhado para revisão humana | 100.0% | 6 |
| Conferência de documentos correta (OCR, quando o serviço foi acertado) | 100.0% | 35 |
| Decisão final correta (resolvido / revisão humana / inválido) | 81.7% | 60 |
| **Erro grave**: resposta automática sobre o serviço errado | 0 de 34 respostas automáticas (0.0%) | 34 |
| Erro seguro: revisão humana desnecessária | 7 | 60 |

Pedidos ambíguos: qualquer um dos dois serviços plausíveis conta como acerto de classificação, mas a decisão esperada é revisão humana.

## Efeito do limiar de confiança (simulado sobre as confianças registradas)

| limiar | respostas automáticas | erros graves | revisões desnecessárias | decisão correta |
|---|---|---|---|---|
| 0.20 | 40 | 1 | 2 | 88.3% |
| 0.30 | 39 | 0 | 3 | 86.7% |
| 0.35 | 38 | 0 | 4 | 85.0% |
| 0.40 | 36 | 0 | 6 | 81.7% |
| 0.45 | 34 | 0 | 7 | 81.7% |
| 0.50 | 33 | 0 | 8 | 80.0% |
| 0.60 | 27 | 0 | 11 | 80.0% |

## Decisão por categoria

| categoria     |   acerto |     n |
|:--------------|---------:|------:|
| ambiguo       |     0.33 |  6.00 |
| docs_faltando |     0.83 | 12.00 |
| fora_escopo   |     1.00 |  6.00 |
| ilegivel      |     1.00 |  5.00 |
| invalido      |     1.00 |  6.00 |
| tipico        |     0.80 | 25.00 |

## Matriz de confusão da classificação

| servico_real              |   antecedentes_criminais |   aposentadoria_idade |   bpc |   cadunico |   carteira_trabalho_digital |   cpf |   mei |   passaporte |   seguro_desemprego |   titulo_eleitor |
|:--------------------------|-------------------------:|----------------------:|------:|-----------:|----------------------------:|------:|------:|-------------:|--------------------:|-----------------:|
| antecedentes_criminais    |                        2 |                     0 |     0 |          0 |                           0 |     0 |     0 |            1 |                   0 |                0 |
| aposentadoria_idade       |                        0 |                     4 |     0 |          0 |                           0 |     0 |     0 |            0 |                   0 |                0 |
| bpc                       |                        0 |                     0 |     6 |          0 |                           0 |     0 |     0 |            0 |                   0 |                0 |
| cadunico                  |                        0 |                     0 |     0 |          4 |                           0 |     0 |     0 |            0 |                   0 |                0 |
| carteira_trabalho_digital |                        1 |                     0 |     0 |          0 |                           3 |     0 |     0 |            0 |                   0 |                0 |
| cpf                       |                        0 |                     0 |     0 |          0 |                           0 |     4 |     0 |            0 |                   0 |                0 |
| mei                       |                        0 |                     0 |     0 |          0 |                           0 |     1 |     4 |            0 |                   0 |                0 |
| passaporte                |                        0 |                     0 |     0 |          0 |                           0 |     0 |     0 |            5 |                   0 |                1 |
| seguro_desemprego         |                        0 |                     0 |     1 |          0 |                           0 |     0 |     1 |            0 |                   6 |                0 |
| titulo_eleitor            |                        0 |                     0 |     0 |          0 |                           0 |     0 |     0 |            0 |                   0 |                4 |

## Erros

| request_id   | categoria     | servico_real              | servico_previsto       |   confianca | decisao_esperada   | decisao        | docs_esperados           | docs_previstos           |
|:-------------|:--------------|:--------------------------|:-----------------------|------------:|:-------------------|:---------------|:-------------------------|:-------------------------|
| REQ-0001     | tipico        | antecedentes_criminais    | passaporte             |      0.2813 | resolvido          | revisao_humana | nan                      | nan                      |
| REQ-0002     | docs_faltando | cpf                       | cpf                    |      0.3961 | resolvido          | revisao_humana | certidao_civil           | certidao_civil           |
| REQ-0010     | ambiguo       | passaporte                | titulo_eleitor         |      0.9397 | revisao_humana     | resolvido      | nan                      | nan                      |
| REQ-0011     | tipico        | bpc                       | bpc                    |      0.4116 | resolvido          | revisao_humana | cpf;documento_identidade | cpf;documento_identidade |
| REQ-0018     | ambiguo       | mei                       | cpf                    |      0.551  | revisao_humana     | resolvido      | nan                      | nan                      |
| REQ-0022     | ambiguo       | seguro_desemprego         | seguro_desemprego      |      0.5462 | revisao_humana     | resolvido      | nan                      | nan                      |
| REQ-0036     | tipico        | seguro_desemprego         | seguro_desemprego      |      0.3929 | resolvido          | revisao_humana | cpf;termo_rescisao       | cpf;termo_rescisao       |
| REQ-0039     | tipico        | seguro_desemprego         | seguro_desemprego      |      0.2122 | resolvido          | revisao_humana | cpf;termo_rescisao       | cpf;termo_rescisao       |
| REQ-0044     | tipico        | mei                       | mei                    |      0.3436 | resolvido          | revisao_humana | cpf;documento_identidade | cpf;documento_identidade |
| REQ-0045     | ambiguo       | carteira_trabalho_digital | antecedentes_criminais |      0.5481 | revisao_humana     | resolvido      | nan                      | nan                      |
| REQ-0050     | docs_faltando | seguro_desemprego         | bpc                    |      0.3196 | resolvido          | revisao_humana | nan                      | nan                      |
