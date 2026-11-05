# Proteção de dados, ética e ODS

**Proteção de dados.** O protótipo usa apenas dados sintéticos (nomes, CPFs e documentos fictícios, marcados
como "DOCUMENTO FICTÍCIO") e conteúdo público do gov.br. Antes de qualquer chamada a API externa (Gemini), o
texto do cidadão passa por mascaramento de CPF, RG, e-mail e telefone (`robo/privacy.py`); imagens de
documentos são processadas só localmente (OCR na máquina, nada é enviado para fora). Chaves de API ficam no
`.env`, fora do código e do repositório (`.gitignore`). Num uso real, seriam necessários base legal pela LGPD
(art. 7º, III — execução de políticas públicas), prazo de retenção dos anexos e controle de acesso à planilha.

**Ética.** O robô não decide se o cidadão tem direito ao benefício: ele orienta e confere documentos, e cita a
fonte oficial em toda resposta. Quando não tem certeza (classificação com baixa confiança, pedido fora do
escopo, anexo ilegível), ele não arrisca uma resposta e encaminha para revisão humana. Riscos conhecidos: o
classificador foi treinado com frases sintéticas e pode errar com linguagem muito diferente; o OCR pode falhar
em fotos ruins, o que penaliza quem tem celular de baixa qualidade — por isso a falha de leitura gera revisão
humana, e não uma recusa.

**ODS.** ODS 16 (16.6 e 16.10 — instituições eficazes e acesso público à informação), porque reduz pedidos
incompletos e retrabalho no atendimento; ODS 10 (redução das desigualdades), porque os serviços escolhidos
(seguro-desemprego, CadÚnico, BPC) atendem justamente a população que mais sofre com burocracia e
deslocamentos desnecessários.
