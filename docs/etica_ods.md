# Proteção de dados, ética e ODS

**Proteção de dados.** O protótipo usa apenas dados sintéticos (nomes, CPFs, números de CAF e documentos
fictícios, marcados como "DOCUMENTO FICTÍCIO") e conteúdo público do gov.br; os municípios são reais, mas
nenhum pedido corresponde a uma pessoa real. Antes de qualquer chamada a API externa (Gemini), o texto do
agricultor passa por mascaramento de CPF, RG, e-mail e telefone (`robo/privacy.py`); as imagens de documentos
são processadas só localmente (OCR na máquina, nada é enviado para fora). Chaves de API ficam no `.env`, fora do
código e do repositório (`.gitignore`). Num uso real seriam necessários base legal pela LGPD (art. 7º, III —
execução de políticas públicas), prazo de retenção dos anexos e controle de acesso à planilha, que passa a
conter o município de cada pedido.

**Ética.** O robô não decide se o agricultor tem direito ao benefício nem atesta perda de safra: ele orienta,
confere documentos e cita a fonte oficial em toda resposta. Quando não tem certeza (classificação com baixa
confiança, pedido fora do escopo, anexo ilegível), ele não arrisca uma resposta e encaminha para revisão
humana. Riscos conhecidos: o classificador foi treinado com frases sintéticas e pode errar com falas regionais
muito diferentes; o OCR pode falhar em fotos ruins, o que penaliza justamente quem tem celular simples e sinal
fraco na zona rural — por isso a falha de leitura gera revisão humana, e não uma recusa. A orientação digital
não substitui o atendimento presencial, que continua sendo o canal de quem não tem acesso à internet.

**ODS.** ODS 1 (1.5 — resiliência dos mais pobres a eventos climáticos extremos) e ODS 2 (2.3 e 2.4 — renda e
produção do agricultor familiar), porque acelera o acesso a Garantia-Safra, Pronaf e benefícios rurais quando
a safra se perde; ODS 13 (13.1 — capacidade de adaptação a desastres relacionados ao clima); e ODS 16 (16.6 —
instituições eficazes), porque reduz pedidos incompletos e viagens perdidas ao atendimento.
