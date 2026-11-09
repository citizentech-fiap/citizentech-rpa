"""Gera os dados sintéticos do robô CitizenTech (determinístico, semente fixa).

Saídas (em `data/synthetic/`, sobrescritas a cada execução):
- `treino_classificador.csv` (texto, service_id): ~40 frases por serviço + classe `fora_escopo`,
  montadas por combinação de modelos (abertura + contexto + núcleo + fecho) com ruído
  realista (gírias, sem acento, erros de digitação, caixa alta/baixa).
- `inbox_teste/*.json` + `inbox_teste/anexos/*`: 60 solicitações de TESTE (held-out). Os textos
  de teste foram escritos à mão, com redação diferente dos modelos de treino, para que a
  métrica seja honesta.
- `labels.csv`: gabarito no formato do CONTRACTS.md.

Categorias do conjunto de teste e regra do `resultado_esperado`:
- tipico (25)        -> todos os documentos exigidos, legíveis           -> resolvido
- docs_faltando (12) -> falta 1+ documento exigido (o robô responde
                        dizendo o que falta, sem precisar de humano)     -> resolvido
- ambiguo (6)        -> pedido cabe em dois serviços                     -> revisao_humana
- fora_escopo (6)    -> assunto que não é um dos serviços do catálogo    -> revisao_humana
- ilegivel (5)       -> um anexo borrado/ruidoso/rotacionado/sem contraste -> revisao_humana
- invalido (6)       -> JSON malformado, `texto` ausente/vazio ou anexo
                        apontando para arquivo inexistente               -> invalido
Ou seja: `revisao_humana` só para ambiguo/fora_escopo/ilegivel; docs_faltando é `resolvido`.
Em `ambiguo`, `service_id` é o serviço principal e a `observacao` traz
"alternativa=<outro_service_id>".

Anexos: documentos FALSOS desenhados com PIL (PNG), com dados claramente fictícios
(nomes como "Fulano de Tal", CPF com dígito verificador propositalmente inválido) e a marca
"DOCUMENTO FICTÍCIO - USO ACADÊMICO". Alguns anexos são PDF: (a) PDF com camada de texto,
escrito "à mão" em sintaxe PDF mínima (reportlab não está instalado e não instalamos pacotes
novos); (b) PDF "escaneado" (só imagem), gerado pelo próprio PIL, para exercitar o OCR em PDF.
Nenhum dado pessoal real é usado.

Uso: (na pasta RPA)  python scripts/gerar_dados_sinteticos.py
"""
from __future__ import annotations

import csv
import json
import random
import shutil
import sys
import textwrap
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robo.config import load_config, path  # noqa: E402
from robo.resilience import get_logger  # noqa: E402

log = get_logger("dados_sinteticos")

SEED = 20261105
MARCA = "DOCUMENTO FICTÍCIO - USO ACADÊMICO"
FONTS_DIR = Path("C:/Windows/Fonts")

# ---------------------------------------------------------------------------
# 1) Conjunto de TREINO do classificador (modelos + vocabulário)
# ---------------------------------------------------------------------------
# Vocabulário de autoria sintética; o catálogo ativo vem exclusivamente do config.
NUCLEOS: dict[str, list[str]] = {
    "garantia_safra": [
        "quero receber o garantia safra", "a chuva não veio e perdi a safra, tem benefício",
        "o feijão não vingou, como peço a ajuda pela perda da colheita",
        "como recebo as parcelas do garantia-safra", "meu milho secou todinho, tem seguro safra",
        "paguei o boleto do garantia safra e não recebi", "onde me inscrevo no garantia safra",
        "a seca levou minha plantação, quero a compensação", "como comprovar a quebra da safra",
        "o sindicato pode olhar meu garantia safra", "quero saber da indenização da lavoura perdida",
        "plantei mas não colhi nada, como acesso o garantia", "perda de safra por estiagem dá auxílio",
    ],
    "caf": [
        "quero fazer meu cadastro de agricultor familiar", "como tiro o CAF",
        "minha DAP venceu, preciso mudar pro CAF", "onde renovo o cadastro da agricultura familiar",
        "preciso da inscrição no CAF", "a EMATER faz o cadastro nacional da agricultura familiar",
        "quero atualizar meu CAF no sindicato", "como substituo a dap antiga",
        "onde consigo o RICAF", "preciso incluir minha mulher no cadastro de agricultor",
        "quais papeis pro registro da agricultura familiar", "a declaração de aptidão venceu",
        "tenho um roçado pequeno e quero me cadastrar como agricultor",
    ],
    "pronaf": [
        "quero um empréstimo do pronaf", "como peço crédito rural no banco",
        "preciso financiar sementes pra plantar de novo", "tem financiamento pro pequeno agricultor",
        "quero dinheiro emprestado pra comprar ração", "como fazer custeio da lavoura pelo pronaf",
        "o banco empresta pra comprar bomba de irrigação", "quero financiar uma cisterna pelo pronaf",
        "qual o juro do crédito da agricultura familiar", "como pedir investimento rural no banco do nordeste",
        "preciso de empréstimo pra salvar o gado", "posso renegociar meu financiamento pronaf",
        "quero crédito pra recomeçar o plantio depois da seca",
    ],
    "aposentadoria_rural": [
        "como peço aposentadoria rural", "trabalhei a vida toda na roça e quero me aposentar",
        "já tenho idade pra aposentadoria de agricultor", "como comprovo tempo de roça no INSS",
        "minha mãe quer aposentadoria de trabalhadora rural", "quero aposentar como segurado especial",
        "tenho 60 anos de idade e só trabalhei no campo", "aposentadoria por idade rural precisa de contribuição",
        "como dar entrada na aposentadoria do lavrador", "quero aposentadoria pela lida na terra",
        "minha mulher fez 55 e quer se aposentar pela roça", "o sindicato ajuda a provar atividade rural",
        "preciso juntar prova do trabalho rural pra aposentadoria",
    ],
    "salario_maternidade_rural": [
        "sou agricultora e quero salário maternidade", "meu filho nasceu e trabalho na roça, tem auxílio",
        "como peço o salário maternidade rural", "quero receber o benefício de mãe lavradora",
        "tive neném e não posso ir pro roçado", "a trabalhadora rural recebe quando tem bebê",
        "como pedir auxílio maternidade de segurada especial", "estou grávida e sou agricultora familiar",
        "ganhei menino e preciso da licença maternidade rural", "parto de quem planta dá salário maternidade",
        "sou mãe da zona rural e preciso do benefício pelo nascimento", "adotei uma criança, tenho salário maternidade rural",
        "o INSS paga maternidade pra quem vive da agricultura",
    ],
    "cadunico": [
        "quero fazer cadastro único", "onde atualizo meu cadunico", "preciso me inscrever no CRAS",
        "como tiro meu NIS pelo cadastro único", "quero cadastrar minha família de baixa renda",
        "mudei de casa e preciso atualizar o cad único", "como faço a entrevista do cadastro único",
        "preciso incluir meu filho no cadunico", "quero corrigir minha renda no cadastro social",
        "meu cadastro único tá velho", "onde fazer o primeiro cadúnico", "como cadastro minha família no CRAS",
        "preciso do cadastro único pra tarifa social",
    ],
    "bolsa_familia": [
        "como recebo bolsa família", "meu bolsa familia foi bloqueado", "quero pedir o bolsa família",
        "o dinheiro do bolsa não caiu", "quando sai a parcela do bolsa família",
        "me cortaram o bolsa familia, como volto a receber", "quero entrar no programa bolsa família",
        "qual a renda pra ter direito ao bolsa", "como desbloquear meu benefício bolsa família",
        "preciso da ajuda mensal do bolsa pra alimentar os meninos", "já tenho cadastro e quero receber o bolsa",
        "meu bolsa família foi cancelado", "como consulto o pagamento do bolsa família",
    ],
    "bpc": [
        "como peço BPC LOAS", "meu filho tem deficiência e precisa do benefício assistencial",
        "quero benefício de prestação continuada", "meu pai tem 67 e nunca contribuiu, pode pedir loas",
        "como solicitar BPC pra pessoa com deficiência", "sou idoso sem renda e quero o bpc",
        "tenho deficiência e não consigo trabalhar, tem benefício", "como agendo a avaliação do BPC",
        "quero o loas pro meu menino autista", "benefício assistencial de um salário mínimo, como pede",
        "minha mãe de 70 anos não tem renda nem contribuição", "quem nunca pagou INSS pode receber BPC",
        "sou deficiente visual e preciso do amparo social",
    ],
    "cpf": [
        "preciso tirar CPF", "meu cpf tá suspenso", "como regularizo CPF na receita federal",
        "quero fazer cpf do meu filho", "o nome no CPF tá errado", "quero inscrição no cadastro de pessoas físicas",
        "como atualizo meus dados do cpf", "meu CPF deu pendente de regularização",
        "não tenho cpf ainda, como faço", "perdi o cartão do CPF", "como corrigir data de nascimento no cpf",
        "preciso resolver meu cpf irregular", "casei e quero mudar o sobrenome no CPF",
    ],
    "fora_escopo": [
        "quero carro-pipa da prefeitura", "a cisterna secou, mandem um caminhão de água",
        "o poste tá sem luz", "a energia acabou e ninguém resolve", "onde pago IPTU atrasado",
        "preciso consertar a estrada do sítio", "a ponte quebrou e o ônibus não passa",
        "quero seguro de carro", "meu carro bateu e a seguradora não paga", "quem ganhou o jogo ontem",
        "me conta uma piada", "bom dia, só vim prosear", "qual a previsão de chuva pra amanhã",
        "quero marcar consulta no posto", "a prefeitura recolhe lixo na comunidade",
        "qual o preço da passagem", "quero segunda via da conta de energia", "tem receita de bolo de milho",
        "o trator da prefeitura quebrou", "quero reclamar da água barrenta", "como peço poda de árvore",
        "o vizinho tá fazendo barulho", "a internet do sítio não funciona", "como renovar seguro do automóvel",
    ],
}

# Contexto rural compartilhado evita associar a seca a uma única classe.
CONTEXTOS_RURAIS = [
    "moro no sertão", "a chuva não veio este ano", "aqui no sítio a cisterna secou",
    "o gado tá morrendo e a renda acabou", "somos pequenos agricultores", "vim procurar o sindicato rural",
    "a EMATER me orientou a perguntar", "o feijão não vingou", "a seca apertou demais",
    "na comunidade vivemos da roça", "tô sem dinheiro depois da estiagem", "o milho virou palha",
]

ABERTURAS = ["", "", "", "oi", "olá", "bom dia", "boa tarde", "boa noite", "oi, tudo bem?", "prezados,",
             "por gentileza,", "eae", "olá equipe", "socorro", "com licença,", "gostaria de uma informação:"]
FECHOS = ["", "", "", "obrigado", "obrigada", "desde já agradeço", "vlw", "aguardo retorno", "pode me ajudar?",
          "me ajudem por favor", "grato", "obg", "o que eu faço?", "é urgente"]
GIRIAS = [("você", "vc"), ("para", "pra"), ("porque", "pq"), ("não", "nao"), ("também", "tb"),
          ("está", "tá"), ("estou", "tô"), ("que", "q"), ("obrigado", "obg"), ("muito", "mto")]


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def erro_digitacao(s: str, rng: random.Random) -> str:
    palavras = s.split()
    idx = [i for i, w in enumerate(palavras) if len(w) > 4 and w.isalpha()]
    if not idx:
        return s
    i = rng.choice(idx)
    w = list(palavras[i])
    j = rng.randrange(1, len(w) - 1)
    op = rng.choice(["troca", "apaga", "dobra"])
    if op == "troca":
        w[j], w[j + 1] = w[j + 1], w[j]
    elif op == "apaga":
        del w[j]
    else:
        w.insert(j, w[j])
    palavras[i] = "".join(w)
    return " ".join(palavras)


def ruido(s: str, rng: random.Random) -> str:
    if rng.random() < 0.3:
        for a, b in GIRIAS:
            if rng.random() < 0.6:
                s = s.replace(f" {a} ", f" {b} ")
    if rng.random() < 0.35:
        s = sem_acento(s)
    if rng.random() < 0.35:
        for _ in range(rng.choice([1, 1, 2])):
            s = erro_digitacao(s, rng)
    r = rng.random()
    if r < 0.35:
        s = s.lower()
    elif r < 0.40:
        s = s.upper()
    elif r < 0.75 and s:
        s = s[0].upper() + s[1:]
    if rng.random() < 0.2:
        s = s.rstrip("?.!") + rng.choice(["??", "!!", "...", "?!"])
    return " ".join(s.split())


def frase_treino(sid: str, rng: random.Random) -> str:
    n = rng.choice(NUCLEOS[sid])
    c = rng.choice(CONTEXTOS_RURAIS)
    a, f = rng.choice(ABERTURAS), rng.choice(FECHOS)
    forma = rng.randrange(7)
    if forma == 0:
        s = n
    elif forma == 1:
        s = f"{a} {n}? {f}"
    elif forma == 2:
        s = f"{c}, {n}"
    elif forma == 3:
        s = f"{a} {c}. {n}? {f}"
    elif forma == 4:
        s = f"{c} e queria saber {n}"
    elif forma == 5:
        s = f"{n}. {c}"
    else:
        s = f"{n} {f}"
    return ruido(s.strip(" ,"), rng)


def gerar_treino(rng: random.Random, por_classe: int = 40) -> list[tuple[str, str]]:
    linhas: list[tuple[str, str]] = []
    for sid in [s["id"] for s in load_config()["services"]] + ["fora_escopo"]:
        vistos: set[str] = set()
        tentativas = 0
        while len(vistos) < por_classe and tentativas < 5000:
            tentativas += 1
            s = frase_treino(sid, rng)
            if len(s) >= 4:
                vistos.add(s)
        linhas += [(s, sid) for s in sorted(vistos)]
    rng.shuffle(linhas)
    return linhas


# ---------------------------------------------------------------------------
# 2) Textos de TESTE escritos à mão (redação diferente dos modelos de treino)
# ---------------------------------------------------------------------------
TEXTOS_TESTE: dict[str, list[str]] = {
    "garantia_safra": [
        "Perdi quase tudo que semeei por falta de inverno. Existe aquele pagamento Garantia-Safra para compensar a frustração da produção?",
        "O laudo do técnico diz que a estiagem destruiu mais da metade da colheita. Como encaminho o pedido de ressarcimento do seguro-safra?",
        "A associação recolheu minha adesão ao garantia, mas até hoje não apareceu parcela. Podem orientar a consulta?",
        "Nem uma saca de fava saiu da minha área este ano. Falaram de uma proteção chamada garantia-safra, preciso requerer.",
        "Sou inscrito naquele programa que indeniza o produtor quando o inverno falha. Gostaria de verificar a liberação do Garantia Safra.",
        "Num deu espiga nenhuma. Me disseram pra buscar o pagamento pela quebra da produção no programa garantia-safra.",
    ],
    "caf": [
        "Levei a antiga declaração de aptidão ao sindicato e disseram que agora o registro do produtor é outro. Como obtenho o documento sucessor da DAP?",
        "A técnica pediu o extrato RICAF da unidade familiar. Ainda não somos inscritos, onde entrego a papelada?",
        "Meu companheiro deixou de participar da unidade produtiva. Preciso retificar os integrantes no CAF.",
        "Cultivo num lote cedido pelo meu tio. Quero reconhecimento no cadastro nacional dos agricultores familiares, sem solicitar dinheiro agora.",
        "A declaração antiga da agricultura familiar perdeu a validade. Quem emite a identificação que entrou no lugar dela?",
        "O balcão falou que falta registrar nossa unidade de produção no CAF. A família toda vive desse pedaço de chão.",
    ],
    "pronaf": [
        "Preciso de recurso reembolsável para instalar gotejamento na horta. Como apresento um projeto de investimento ao Pronaf?",
        "A cooperativa falou numa linha bancária com juros menores para agricultura familiar. Pretendo comprar matrizes caprinas a prazo.",
        "Minha reserva acabou. Busco custeio do Pronaf para adquirir insumos na próxima estação, com pagamento depois da venda.",
        "O gerente solicitou proposta técnica para liberar financiamento de um reservatório. Podem explicar o acesso ao crédito Pronaf?",
        "Tô querendo tomar um dinheiro no banco pra recuperar o pomar. A linha de pequeno produtor permite pagar em prestações?",
        "Queria contratar operação de crédito agrícola familiar para uma ordenhadeira. Procuro orientação sobre o Pronaf.",
    ],
    "aposentadoria_rural": [
        "Desde menina ajudo na enxada, agora completei cinquenta e cinco. Como encaminhar meu descanso remunerado de trabalhadora do campo no INSS?",
        "Meu marido chegou aos sessenta e tem décadas de cultivo em regime familiar. Deseja requerer aposentadoria de segurado especial.",
        "Tenho notas de venda de mandioca e declarações antigas do sindicato. Servem para demonstrar minha trajetória de lavrador ao aposentar?",
        "Passei quinze anos tirando sustento de um pedaço arrendado. Já alcancei a idade e preciso solicitar aposentadoria rural.",
        "Nunca tive patrão, sempre plantei junto dos meus pais. Agora idoso, busco reconhecimento desses anos para o benefício previdenciário rural.",
        "Meu pai guarda recibos da feira de muitos anos. Como usa essa prova de atividade agrícola para requerer aposentadoria?",
    ],
    "salario_maternidade_rural": [
        "Pari há vinte dias e suspendi a lida com os animais. Como encaminho o pagamento de maternidade de quem produz com a família?",
        "Nasceu minha pequena e a agente mencionou quatro meses de proteção pelo INSS para mulher do campo. Onde protocolar?",
        "Estou no oitavo mês da gestação e cultivo hortaliças como segurada especial. Desejo solicitar a prestação de maternidade rural.",
        "Fiquei responsável por uma criança adotada e parei de trabalhar na plantação. Busco o benefício materno da agricultora.",
        "O nascimento do meu caçula foi registrado no cartório. Qual caminho para receber salário de maternidade como camponesa?",
        "Tive gêmeos e dependo da produção familiar. Me orientem no requerimento de maternidade ao instituto da previdência.",
    ],
    "cadunico": [
        "A equipe social vai fazer entrevista das famílias do povoado. Quero entrar na base de dados dos programas sociais, o Cadastro Único.",
        "Mudou o responsável da nossa casa e precisamos retificar a ficha do CadÚnico, sem pedir benefício específico por enquanto.",
        "Passamos a morar com minha sogra. O posto de assistência pediu que informássemos a nova composição domiciliar no cadastro único.",
        "O entrevistador do CRAS pediu agendamento para meu primeiro registro socioeconômico. Como faço essa inscrição?",
        "Meu endereço rural ficou errado na ficha do governo. Preciso corrigir só os dados cadastrais do CadÚnico.",
        "Não tenho número de identificação social. Quero registrar nosso domicílio no sistema único das famílias de pouca renda.",
    ],
    "bolsa_familia": [
        "No aplicativo apareceu averiguação e o auxílio do Bolsa Família sumiu. Como restabeleço a transferência mensal?",
        "As crianças estão frequentando a escola e somos cadastrados. Busco inclusão na folha de pagamentos do Bolsa Família.",
        "Minha vizinha recebe o benefício das famílias com crianças. Quero saber como solicitar esse repasse do Bolsa Família também.",
        "O extrato do Bolsa Família mostrou suspensão. Preciso entender o procedimento para voltar a sacar.",
        "A última prestação do bolsa familiar não entrou na poupança social. Onde verifico a situação do pagamento?",
        "Vivemos com muito pouco e aguardamos seleção para a transferência de renda Bolsa Família. Qual o próximo passo?",
    ],
    "bpc": [
        "Meu irmão tem impedimento de longo prazo e depende de nós até para se alimentar. Quero o amparo assistencial BPC, pois não possui renda.",
        "Vovó completou sessenta e oito, não possui histórico de contribuição nem sustento. Como requerer a prestação continuada da LOAS?",
        "Sou pessoa com deficiência auditiva e a renda da casa é quase nenhuma. Busco orientação sobre o amparo de um mínimo mensal.",
        "O médico recomendou avaliação social e pericial para conceder o BPC ao meu menino. Qual o caminho do requerimento?",
        "Meu avô nunca recolheu previdência, tem mais de 65 e vive de doações. Queremos o benefício assistencial ao idoso.",
        "Minha filha tem limitações permanentes desde pequena. Queria solicitar a proteção assistencial prevista na LOAS.",
    ],
    "cpf": [
        "O banco recusou meu número da Receita por divergência na filiação. Como arrumo o registro de pessoa física?",
        "Minha menina ainda não possui inscrição fiscal. Preciso obter o número dela no cadastro da Receita.",
        "Consta situação suspensa no meu documento de pessoa física. Como deixo o CPF em ordem?",
        "Depois da união civil meu sobrenome mudou. Gostaria de retificar o cadastro fiscal de onze algarismos.",
        "A repartição encontrou data de nascimento diferente no registro da Receita Federal. Quero corrigir o CPF.",
        "O atendente identificou pendência no cadastro de pessoa física. Desejo regularizar minha inscrição fiscal.",
    ],
}

AMBIGUOS: list[tuple[str, str, str]] = [
    ("garantia_safra", "pronaf", "A lavoura virou prejuízo. Busco tanto a indenização do Garantia-Safra quanto financiamento do Pronaf para a próxima estação; qual resolver primeiro?"),
    ("pronaf", "garantia_safra", "Fiquei sem produção. Vim pedir crédito no banco e também o pagamento do seguro-safra, preciso dos dois."),
    ("caf", "pronaf", "Não tenho registro familiar atualizado e preciso financiar uma caixa d'água. Vim solicitar o CAF e a operação de crédito Pronaf juntos."),
    ("cadunico", "bolsa_familia", "Quero alterar os moradores no Cadastro Único e liberar o Bolsa Família suspenso. Não sei qual dos dois pedidos é este."),
    ("bolsa_familia", "cadunico", "Preciso incluir meu bebê na entrevista cadastral do CRAS e requerer o Bolsa Família. Vocês fazem as duas coisas?"),
    ("aposentadoria_rural", "bpc", "Meu pai passou a vida no campo, mas não tem prova desses anos. Procuramos aposentadoria rural ou amparo LOAS para idoso; não sabemos qual se aplica."),
]

FORA_ESCOPO_TESTE: list[tuple[str, list[str]]] = [
    ("O abastecimento móvel não chega no povoado há quinze dias. Podem colocar nossa comunidade na rota do caminhão-tanque municipal?", ["comprovante_residencia"]),
    ("As valetas impedem a ambulância de chegar à fazenda. Solicito patrolamento do acesso vicinal.", []),
    ("O carnê do imposto predial veio duplicado. Quem revisa a cobrança imobiliária municipal?", []),
    ("A tensão da rede está oscilando e queimou o motor. Quero registrar reclamação na distribuidora.", ["documento_identidade"]),
    ("Renovei a apólice do automóvel e não recebi o certificado da seguradora. Podem cobrar a corretora?", []),
    ("Vim bater um papo: vocês preferem sanfona ou zabumba no forró de sábado?", []),
]

# ---------------------------------------------------------------------------
# 3) Pessoas e documentos fictícios
# ---------------------------------------------------------------------------
NOMES = ["Fulano de Tal", "Beltrana de Tal", "Ciclano da Silva Fictício", "Maria Exemplo dos Santos",
         "João Teste Pereira", "Ana Modelo Oliveira", "José Fictício Souza", "Francisca Amostra Lima",
         "Pedro Simulado Costa", "Joana Hipotética Rocha", "Antônio Inventado Alves", "Luzia Imaginária Ferreira",
         "Raimundo Exemplar Gomes", "Tereza Ficção Martins", "Severino de Tal Ribeiro", "Clara Protótipo Nunes"]
MAES = ["Mãe Fictícia de Tal", "Maria Exemplo da Silva", "Joana Modelo", "Rita Amostra Souza", "Helena Teste Lima"]
PAIS = ["Pai Fictício de Tal", "José Exemplo da Silva", "Carlos Modelo", "Paulo Amostra Souza", "Mário Teste Lima"]
COMUNIDADES = ["Sítio Amostra", "Comunidade Fictícia Mandacaru", "Assentamento Exemplo",
               "Sítio Teste Umbuzeiro", "Comunidade Modelo do Riacho"]


def carregar_municipios() -> list[dict[str, str]]:
    with (ROOT / "data" / "municipios_semiarido.csv").open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def sortear_localizacao(rng: random.Random, municipios: list[dict[str, str]]) -> dict[str, str]:
    # Pesos por posição no CSV: os quatro primeiros concentram demanda (8:5:3:2:1...).
    pesos = [8, 5, 3, 2]
    local = rng.choices(municipios, weights=[pesos[i] if i < len(pesos) else 1
                                           for i in range(len(municipios))], k=1)[0]
    return {campo: local[campo] for campo in ("municipio", "uf", "cod_ibge")}


def cpf_ficticio(rng: random.Random) -> str:
    """CPF com dígitos verificadores propositalmente INVÁLIDOS (nunca é um CPF real)."""
    base = [rng.randrange(10) for _ in range(9)]

    def dv(nums: list[int]) -> int:
        s = sum(v * w for v, w in zip(nums, range(len(nums) + 1, 1, -1)))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    d1 = dv(base)
    d2 = dv(base + [d1])
    d1_inv = (d1 + 1 + rng.randrange(8)) % 10  # garante d1 != correto
    d = base + [d1_inv, d2]
    s = "".join(map(str, d))
    return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"


def pessoa_ficticia(rng: random.Random, local: dict[str, str]) -> dict[str, str]:
    nome = rng.choice(NOMES)
    return {
        "nome": nome,
        "cpf": cpf_ficticio(rng),
        "rg": f"{rng.randrange(10, 99)}.{rng.randrange(100, 999)}.{rng.randrange(100, 999)}-{rng.randrange(10)}",
        "nasc": f"{rng.randrange(1, 28):02d}/{rng.randrange(1, 12):02d}/{rng.randrange(1950, 2006)}",
        "mae": rng.choice(MAES),
        "pai": rng.choice(PAIS),
        "cidade": f"{local['municipio']}/{local['uf']}",
        "endereco": f"{rng.choice(COMUNIDADES)}, lote fictício {rng.randrange(10, 999)} - Zona rural",
        "cep": f"00{rng.randrange(100, 999)}-000",
        "email": sem_acento(nome.split()[0].lower()) + f".ficticio{rng.randrange(10, 99)}@exemplo.com",
    }


def conteudo_documento(tipo: str, p: dict[str, str], rng: random.Random) -> tuple[str, str, list[tuple[str, str]]]:
    """(título, subtítulo, campos) de cada tipo canônico, com variação de redação."""
    if tipo == "documento_identidade":
        if rng.random() < 0.2:
            return ("CARTEIRA NACIONAL DE HABILITAÇÃO", "REPÚBLICA FEDERATIVA DO BRASIL - DEPARTAMENTO DE TRÂNSITO",
                    [("NOME", p["nome"]), ("DOC. IDENTIDADE", p["rg"]), ("CPF", p["cpf"]),
                     ("DATA NASCIMENTO", p["nasc"]), ("FILIAÇÃO", p["mae"]), ("CATEGORIA", "B"),
                     ("VALIDADE", "01/01/2030")])
        titulo = rng.choice(["REGISTRO GERAL / CARTEIRA DE IDENTIDADE", "CARTEIRA DE IDENTIDADE - REGISTRO GERAL",
                             "CARTEIRA DE IDENTIDADE"])
        return (titulo, "SECRETARIA DE SEGURANÇA PÚBLICA - INSTITUTO DE IDENTIFICAÇÃO",
                [("REGISTRO GERAL", p["rg"]), ("DATA DE EXPEDIÇÃO", "10/03/2020"), ("NOME", p["nome"]),
                 ("FILIAÇÃO", f"{p['mae']} / {p['pai']}"), ("NATURALIDADE", p["cidade"]),
                 ("DATA DE NASCIMENTO", p["nasc"]), ("CPF", p["cpf"])])
    if tipo == "cpf":
        titulo = rng.choice(["CADASTRO DE PESSOAS FÍSICAS", "COMPROVANTE DE INSCRIÇÃO NO CADASTRO DE PESSOAS FÍSICAS"])
        return (titulo, "MINISTÉRIO DA FAZENDA - RECEITA FEDERAL DO BRASIL",
                [("Nº DE INSCRIÇÃO", p["cpf"]), ("NOME", p["nome"]), ("DATA DE NASCIMENTO", p["nasc"]),
                 ("SITUAÇÃO CADASTRAL", "REGULAR"), ("DATA DA INSCRIÇÃO", "05/05/2005")])
    if tipo == "comprovante_residencia":
        if rng.random() < 0.6:
            titulo, emp, extra = ("COMPROVANTE DE RESIDÊNCIA - CONTA DE ENERGIA", "COMPANHIA FICTÍCIA DE ENERGIA ELÉTRICA",
                                  ("CONSUMO DO MÊS", f"{rng.randrange(80, 400)} kWh"))
        else:
            titulo, emp, extra = ("CONTA DE ÁGUA E ESGOTO - COMPROVANTE DE RESIDÊNCIA", "SANEAMENTO EXEMPLO S.A.",
                                  ("CONSUMO DO MÊS", f"{rng.randrange(5, 30)} m³"))
        return (titulo, emp,
                [("TITULAR", p["nome"]), ("ENDEREÇO", p["endereco"]), ("CEP / CIDADE", f"{p['cep']} {p['cidade']}"),
                 extra, ("VENCIMENTO", f"{rng.randrange(1, 28):02d}/10/2026"),
                 ("VALOR A PAGAR", f"R$ {rng.randrange(40, 300)},{rng.randrange(10, 99)}")])
    if tipo == "caf":
        return ("REGISTRO DE INSCRIÇÃO NO CADASTRO NACIONAL DA AGRICULTURA FAMILIAR - RICAF",
                "CAF - UNIDADE FAMILIAR DE PRODUÇÃO AGRÁRIA (FICTÍCIA)",
                [("NÚMERO DE INSCRIÇÃO FICTÍCIO", f"CAF-FICTICIO-{rng.randrange(100000, 999999)}"),
                 ("AGRICULTOR(A)", p["nome"]), ("CPF", p["cpf"]), ("MUNICÍPIO / UF", p["cidade"]),
                 ("ATIVIDADE", "Agricultura familiar de sequeiro"), ("VALIDADE", "05/11/2027")])
    if tipo == "comprovante_posse_terra":
        titulo = rng.choice(["CONTRATO DE ARRENDAMENTO RURAL", "ESCRITURA PÚBLICA DE IMÓVEL RURAL",
                             "DECLARAÇÃO DE POSSE - SINDICATO DOS TRABALHADORES RURAIS"])
        return (titulo, "COMPROVANTE DE POSSE OU PROPRIEDADE DA TERRA - MODELO FICTÍCIO",
                [("POSSUIDOR(A)", p["nome"]), ("CPF", p["cpf"]), ("IMÓVEL RURAL", p["endereco"]),
                 ("MUNICÍPIO / UF", p["cidade"]), ("ÁREA", f"{rng.randrange(2, 20)} hectares"),
                 ("FINALIDADE", "Cultivo familiar de milho e feijão")])
    if tipo == "certidao_civil":
        if rng.random() < 0.7:
            titulo, rot = "CERTIDÃO DE NASCIMENTO", "NASCIMENTO"
        else:
            titulo, rot = "CERTIDÃO DE CASAMENTO", "CASAMENTO"
        return (titulo, "REGISTRO CIVIL DAS PESSOAS NATURAIS - CARTÓRIO DO 1º OFÍCIO (FICTÍCIO)",
                [("NOME", p["nome"]), (f"DATA DO {rot}", p["nasc"]), ("LOCAL", p["cidade"]),
                 ("FILIAÇÃO", f"{p['mae']} e {p['pai']}"),
                 ("MATRÍCULA", f"000000 01 55 {rng.randrange(2000, 2025)} 1 00000 000 0000000-00")])
    if tipo == "comprovante_renda":
        titulo = rng.choice(["NOTA FISCAL DE PRODUTOR RURAL", "DECLARAÇÃO DE RENDA"])
        return (titulo, "RENDIMENTOS DA AGRICULTURA FAMILIAR - MODELO FICTÍCIO",
                [("PRODUTOR(A)", p["nome"]), ("CPF", p["cpf"]), ("LOCAL", p["cidade"]),
                 ("COMPETÊNCIA", "09/2026"), ("PRODUTO", "Feijão de corda e mandioca"),
                 ("RENDA DECLARADA", f"R$ {rng.randrange(100, 900)},00")])
    raise ValueError(tipo)


def fonte(nome: str, tam: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONTS_DIR / nome), tam)
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", tam)
        except OSError:
            return ImageFont.load_default(tam)


FAMILIAS = [("arial.ttf", "arialbd.ttf"), ("calibri.ttf", "calibrib.ttf"), ("times.ttf", "timesbd.ttf"),
            ("verdana.ttf", "verdanab.ttf"), ("tahoma.ttf", "tahomabd.ttf"), ("georgia.ttf", "georgiab.ttf")]


def _texto_ajustado(d: ImageDraw.ImageDraw, xy, txt, nome_fonte, tam, larg_max, **kw):
    """Desenha reduzindo a fonte até caber na largura."""
    while tam > 12:
        f = fonte(nome_fonte, tam)
        if d.textlength(txt, font=f) <= larg_max:
            break
        tam -= 2
    d.text(xy, txt, font=fonte(nome_fonte, tam), **kw)
    return tam


def _titulo_ajustado(d: ImageDraw.ImageDraw, xy, titulo: str, nome_fonte: str,
                     larg_max: int, cor, centralizado: bool = False) -> None:
    """Quebra títulos rurais extensos em duas linhas para preservar a leitura pelo OCR."""
    tam = 30
    while tam >= 16:
        linhas, linha = [], ""
        for palavra in titulo.split():
            tentativa = f"{linha} {palavra}".strip()
            if linha and d.textlength(tentativa, font=fonte(nome_fonte, tam)) > larg_max:
                linhas.append(linha)
                linha = palavra
            else:
                linha = tentativa
        linhas.append(linha)
        if len(linhas) <= 2:
            break
        tam -= 2
    x, y = xy
    for i, linha in enumerate(linhas):
        deslocamento = (larg_max - d.textlength(linha, font=fonte(nome_fonte, tam))) / 2 if centralizado else 0
        d.text((x + deslocamento, y + i * (tam + 3)), linha, font=fonte(nome_fonte, tam), fill=cor)


def renderizar_documento(tipo: str, p: dict[str, str], rng: random.Random) -> Image.Image:
    titulo, sub, campos = conteudo_documento(tipo, p, rng)
    W, H = rng.choice([(1100, 760), (1000, 720), (1200, 820), (1050, 780)])
    tons = [(255, 255, 255), (250, 247, 238), (240, 246, 250), (246, 250, 240), (252, 244, 244)]
    img = Image.new("RGB", (W, H), rng.choice(tons))
    d = ImageDraw.Draw(img)
    reg, neg = rng.choice(FAMILIAS)
    layout = rng.randrange(3)
    margem = rng.randrange(40, 70)
    cor_txt = rng.choice([(10, 10, 10), (20, 30, 60), (40, 20, 20)])

    if layout == 0:  # título centralizado, campos em uma coluna
        d.rectangle([12, 12, W - 12, H - 12], outline=(90, 90, 90), width=3)
        _titulo_ajustado(d, (margem, 30), titulo, neg, W - 2 * margem, cor_txt, centralizado=True)
        _texto_ajustado(d, (margem, 105), sub, reg, 22, W - 2 * margem, fill=(70, 70, 70))
        y = 170
        for rot, val in campos:
            _texto_ajustado(d, (margem, y), f"{rot}: {val}", reg, 25, W - 2 * margem, fill=cor_txt)
            y += rng.randrange(52, 64)
    elif layout == 1:  # faixa colorida no topo, campos em duas colunas
        faixa = rng.choice([(30, 80, 140), (20, 110, 70), (120, 40, 40), (60, 60, 60)])
        d.rectangle([0, 0, W, 130], fill=faixa)
        _titulo_ajustado(d, (margem, 15), titulo, neg, W - 2 * margem, (255, 255, 255))
        _texto_ajustado(d, (margem, 96), sub, reg, 20, W - 2 * margem, fill=(235, 235, 235))
        col_w = (W - 3 * margem) // 2
        for i, (rot, val) in enumerate(campos):
            x = margem + (i % 2) * (col_w + margem)
            y = 175 + (i // 2) * 105
            _texto_ajustado(d, (x, y), rot, neg, 18, col_w, fill=(90, 90, 90))
            _texto_ajustado(d, (x, y + 28), val, reg, 25, col_w, fill=cor_txt)
            d.line([x, y + 64, x + col_w, y + 64], fill=(180, 180, 180), width=1)
    else:  # título à esquerda em caixa, campos em tabela, quadro de foto em alguns tipos
        d.rectangle([margem - 15, 15, W - margem + 15, 130], outline=cor_txt, width=2)
        _titulo_ajustado(d, (margem, 24), titulo, neg, W - 2 * margem, cor_txt)
        _texto_ajustado(d, (margem, 103), sub, reg, 18, W - 2 * margem, fill=(80, 80, 80))
        x_tab = margem
        larg_tab = W - 2 * margem
        if tipo == "documento_identidade":
            d.rectangle([W - margem - 170, 150, W - margem, 360], outline=(120, 120, 120), width=2, fill=(225, 225, 225))
            d.text((W - margem - 120, 245), "FOTO", font=fonte(reg, 24), fill=(150, 150, 150))
            larg_tab = W - 2 * margem - 200
        y = 150
        for rot, val in campos:
            d.rectangle([x_tab, y, x_tab + larg_tab, y + 62], outline=(150, 150, 150), width=1)
            _texto_ajustado(d, (x_tab + 10, y + 4), rot, neg, 16, larg_tab - 20, fill=(100, 100, 100))
            _texto_ajustado(d, (x_tab + 10, y + 26), val, reg, 24, larg_tab - 20, fill=cor_txt)
            y += 70

    # rodapé e marca d'água (diagonal, translúcida)
    _texto_ajustado(d, (margem, H - 50), MARCA + " - dados inventados", reg, 18, W - 2 * margem, fill=(160, 40, 40))
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dc = ImageDraw.Draw(camada)
    fm = fonte(neg, 54)
    lm = dc.textlength(MARCA, font=fm)
    dc.text(((W - lm) / 2, H / 2 - 30), MARCA, font=fm, fill=(200, 60, 60, 45))
    camada = camada.rotate(rng.choice([18, 22, 25, -20]), resample=Image.BICUBIC)
    img = Image.alpha_composite(img.convert("RGBA"), camada).convert("RGB")

    if rng.random() < 0.3:  # leve inclinação, como foto de celular
        fundo = rng.choice([(255, 255, 255), (210, 210, 210)])
        img = img.rotate(rng.uniform(-2.0, 2.0), resample=Image.BICUBIC, expand=True, fillcolor=fundo)
    return img


def degradar(img: Image.Image, modo: str, nrng: np.random.Generator) -> Image.Image:
    """Torna o documento ilegível (categoria `ilegivel`)."""
    W, H = img.size
    if modo == "desfoque":
        img = img.resize((W // 4, H // 4)).resize((W, H)).filter(ImageFilter.GaussianBlur(7))
    elif modo == "ruido":
        img = img.filter(ImageFilter.GaussianBlur(3.5))
        arr = np.asarray(img).astype(np.float32)
        arr += nrng.normal(0, 95, arr.shape)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        img = ImageEnhance.Contrast(img).enhance(0.45)
    elif modo == "contraste":
        img = ImageEnhance.Contrast(img.filter(ImageFilter.GaussianBlur(4))).enhance(0.06)
        img = ImageEnhance.Brightness(img).enhance(1.5)
        arr = np.asarray(img).astype(np.float32) + nrng.normal(0, 18, (H, W, 3))
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    elif modo == "rotacao":
        img = img.rotate(118, resample=Image.BICUBIC, expand=True, fillcolor=(30, 30, 30))
        img = img.resize((img.width // 3, img.height // 3)).resize(img.size).filter(ImageFilter.GaussianBlur(5))
    elif modo == "pixelado":
        img = img.resize((W // 14, H // 14), Image.NEAREST).resize((W, H), Image.NEAREST)
        img = img.filter(ImageFilter.GaussianBlur(2.5))
    else:
        raise ValueError(modo)
    return img


# ---------------------------------------------------------------------------
# 4) PDF com camada de texto (sintaxe PDF mínima, sem bibliotecas extras)
# ---------------------------------------------------------------------------
def _pdf_str(s: str) -> bytes:
    b = s.encode("cp1252", errors="replace")
    return b"(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def escrever_pdf_texto(destino: Path, tipo: str, p: dict[str, str], rng: random.Random) -> None:
    titulo, sub, campos = conteudo_documento(tipo, p, rng)
    linhas: list[bytes] = []
    for i, linha in enumerate(textwrap.wrap(titulo, width=55)):
        linhas += [b"BT", b"/F2 15 Tf", f"50 {800 - i * 20} Td".encode(), _pdf_str(linha) + b" Tj", b"ET"]
    linhas += [b"BT", b"/F1 9 Tf", b"50 735 Td", _pdf_str(sub) + b" Tj", b"ET"]
    y = 715
    for rot, val in campos:
        linhas += [b"BT", b"/F1 12 Tf", f"50 {y} Td".encode(), _pdf_str(f"{rot}: {val}") + b" Tj", b"ET"]
        y -= 26
    linhas += [b"BT", b"/F2 10 Tf", b"50 60 Td", _pdf_str(MARCA) + b" Tj", b"ET"]
    conteudo = b"\n".join(linhas)
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(conteudo)).encode() + b" >>\nstream\n" + conteudo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    destino.write_bytes(bytes(out))


# ---------------------------------------------------------------------------
# 5) Montagem do conjunto de teste
# ---------------------------------------------------------------------------
MODOS_ILEGIVEL = ["desfoque", "ruido", "contraste", "rotacao", "pixelado"]


def plano_de_casos() -> list[dict]:
    """Distribui 60 casos pelo catálogo ativo, mantendo as proporções do contrato."""
    sids = [s["id"] for s in load_config()["services"]]
    casos: list[dict] = []
    for categoria, quantidade in (("tipico", 25), ("docs_faltando", 12), ("ilegivel", 5)):
        casos.extend({"categoria": categoria, "service_id": sids[i % len(sids)]}
                     for i in range(quantidade))
    for sid, alt, txt in AMBIGUOS:
        if sid in sids and alt in sids:
            casos.append({"categoria": "ambiguo", "service_id": sid, "alternativa": alt, "texto": txt})
    for txt, docs in FORA_ESCOPO_TESTE:
        casos.append({"categoria": "fora_escopo", "service_id": "fora_escopo", "texto": txt, "docs": docs})
    falhas = ["json_truncado", "json_aspas_simples", "sem_texto", "texto_vazio",
              "anexo_inexistente", "anexo_fora_da_inbox"]
    casos.extend({"categoria": "invalido", "service_id": sids[i % len(sids)], "falha": falha}
                 for i, falha in enumerate(falhas))
    return casos


def gerar_teste(rng: random.Random, nrng: np.random.Generator, out_dir: Path,
                casos: list[dict] | None = None, prefixo: str = "REQ") -> list[dict]:
    cfg = load_config()
    exigidos = {s["id"]: list(s["documentos_exigidos"]) for s in cfg["services"]}
    todos_tipos = list(cfg["document_types"])
    municipios = carregar_municipios()
    anexos_dir = out_dir / "anexos"
    anexos_dir.mkdir(parents=True, exist_ok=True)

    casos = plano_de_casos() if casos is None else casos
    ids = list(range(1, len(casos) + 1))
    rng.shuffle(ids)  # categorias espalhadas, não em blocos
    proximo_texto = {sid: 0 for sid in TEXTOS_TESTE}
    pdf_texto_tipos = set(todos_tipos)
    pdf_scan_restantes = 2
    modos = list(MODOS_ILEGIVEL)
    labels: list[dict] = []

    for caso, num in zip(casos, ids):
        rid = f"{prefixo}-{num:04d}"
        cat, sid = caso["categoria"], caso["service_id"]
        if "texto" in caso:
            texto = caso["texto"]
        elif cat == "invalido":
            texto = "Preciso de orientação para minha família de agricultores."
        else:
            texto = TEXTOS_TESTE[sid][proximo_texto[sid]]
            proximo_texto[sid] += 1

        req = exigidos.get(sid, [])
        if cat in ("tipico", "ambiguo", "ilegivel"):
            docs = list(req)
            if cat == "tipico" and rng.random() < 0.25:
                docs.append(rng.choice([t for t in todos_tipos if t not in req]))
        elif cat == "docs_faltando":
            n_remover = len(req) if len(req) == 1 else rng.choice([1, 1, 2])
            remover = set(rng.sample(req, n_remover))
            docs = [t for t in req if t not in remover]
            if rng.random() < 0.3:
                docs.append(rng.choice([t for t in todos_tipos if t not in req]))
        elif cat == "fora_escopo":
            docs = list(caso["docs"])
        else:  # invalido
            docs = list(req)[:2]
        rng.shuffle(docs)

        local = sortear_localizacao(rng, municipios)
        pessoa = pessoa_ficticia(rng, local)
        if texto and rng.random() < 0.6:
            texto += f" Sou de {local['municipio']}/{local['uf']}, {pessoa['endereco'].split(',')[0]}."
        anexos_rel: list[str] = []
        presentes: list[str] = []
        ilegiveis: list[str] = []
        obs = ""
        tipo_ilegivel = rng.choice(docs) if cat == "ilegivel" else None
        falha = caso.get("falha")

        for tipo in docs:
            if falha in ("anexo_inexistente", "anexo_fora_da_inbox"):
                break
            if cat == "tipico" and tipo in pdf_texto_tipos:
                nome = f"{rid}_{tipo}.pdf"
                escrever_pdf_texto(anexos_dir / nome, tipo, pessoa, rng)
                pdf_texto_tipos.remove(tipo)
            else:
                img = renderizar_documento(tipo, pessoa, rng)
                if tipo == tipo_ilegivel:
                    modo = modos.pop(0)
                    img = degradar(img, modo, nrng)
                    obs = f"anexo {tipo} degradado ({modo})"
                if cat == "tipico" and pdf_scan_restantes > 0 and tipo == "documento_identidade" \
                        and rng.random() < 0.5:
                    nome = f"{rid}_{tipo}.pdf"
                    # Datas fixas evitam que metadados do PDF quebrem o determinismo.
                    img.save(anexos_dir / nome, "PDF", resolution=100.0,
                             creationDate="D:20261105000000Z", modDate="D:20261105000000Z")
                    pdf_scan_restantes -= 1
                else:
                    nome = f"{rid}_{tipo}.png"
                    img.save(anexos_dir / nome, "PNG", optimize=True)
            anexos_rel.append(f"anexos/{nome}")
            (ilegiveis if tipo == tipo_ilegivel else presentes).append(tipo)

        dados = {
            "request_id": rid,
            "data_envio": f"2026-11-{rng.randrange(1, 5):02d}T{rng.randrange(7, 22):02d}:{rng.randrange(60):02d}:00-03:00",
            **local,
            "nome": pessoa["nome"],
            "email": pessoa["email"],
        }
        if rng.random() < 0.5:
            dados["cpf"] = pessoa["cpf"]
        dados["texto"] = texto
        dados["anexos"] = anexos_rel

        arq = out_dir / f"{rid}.json"
        if falha == "json_truncado":
            bruto = json.dumps(dados, ensure_ascii=False, indent=2)
            arq.write_text(bruto[: len(bruto) // 2], encoding="utf-8")
            obs = "JSON truncado (malformado)"
        elif falha == "json_aspas_simples":
            bruto = json.dumps(dados, ensure_ascii=False).replace('"', "'").rstrip("}") + ",}"
            arq.write_text(bruto, encoding="utf-8")
            obs = "JSON com aspas simples e vírgula sobrando (malformado)"
        else:
            if falha == "sem_texto":
                dados.pop("texto")
                obs = "campo texto ausente"
            elif falha == "texto_vazio":
                dados["texto"] = "   "
                obs = "campo texto vazio"
            elif falha == "anexo_inexistente":
                dados["anexos"] = [f"anexos/{rid}_rg.png", f"anexos/{rid}_comprovante.jpg"]
                obs = "anexos citados não existem no disco"
            elif falha == "anexo_fora_da_inbox":
                dados["anexos"] = ["../../segredos/cpf.png"]
                obs = "anexo aponta para fora da inbox (inexistente)"
            arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
            if falha in ("sem_texto", "texto_vazio", "anexo_inexistente", "anexo_fora_da_inbox"):
                presentes, ilegiveis = [], []

        if cat == "ambiguo":
            obs = f"alternativa={caso['alternativa']}"
        resultado = {"tipico": "resolvido", "docs_faltando": "resolvido", "invalido": "invalido"}.get(cat, "revisao_humana")
        if cat == "invalido" and falha in ("json_truncado", "json_aspas_simples"):
            presentes, ilegiveis = [], []
        labels.append({
            "request_id": rid, "service_id": sid, "docs_presentes": ";".join(presentes),
            "docs_ilegiveis": ";".join(ilegiveis), "resultado_esperado": resultado, "categoria": cat,
            "observacao": obs, **local,
        })
    labels.sort(key=lambda r: r["request_id"])
    return labels


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Gera conjuntos sintéticos separados")
    ap.add_argument("--validacao", action="store_true")
    args = ap.parse_args()
    if args.validacao:
        gerar_validacao()
        return
    rng = random.Random(SEED)
    nrng = np.random.default_rng(SEED)
    base = path("synthetic")
    base.mkdir(parents=True, exist_ok=True)

    treino = gerar_treino(rng)
    with open(base / "treino_classificador.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["texto", "service_id"])
        w.writerows(treino)

    inbox = base / "inbox_teste"
    destino = inbox.resolve()
    if destino != (ROOT / "data" / "synthetic" / "inbox_teste").resolve() or inbox.is_symlink():
        raise ValueError("Destino de regeneração fora de data/synthetic/inbox_teste")
    if inbox.exists():
        shutil.rmtree(destino)  # regeneração limpa (só a pasta gerada por este script)
    inbox.mkdir(parents=True)
    labels = gerar_teste(rng, nrng, inbox)
    campos = ["request_id", "service_id", "docs_presentes", "docs_ilegiveis", "resultado_esperado",
              "categoria", "observacao", "municipio", "uf", "cod_ibge"]
    with open(base / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(labels)

    from collections import Counter
    log.info("Treino: %d frases -> %s", len(treino), dict(Counter(s for _, s in treino)))
    log.info("Teste: %d solicitações -> %s", len(labels), dict(Counter(r["categoria"] for r in labels)))
    n_anexos = len(list((inbox / "anexos").iterdir()))
    log.info("Anexos gerados: %d em %s", n_anexos, inbox / "anexos")


def gerar_validacao() -> None:
    """Redação própria, semente distinta e mesma montagem de pessoas/anexos do teste."""
    from scripts.textos_validacao import TIPICOS, AMBIGUOS_VALIDACAO
    ativos = {s["id"] for s in load_config()["services"]}
    casos = [{"categoria": "tipico", "service_id": sid, "texto": texto}
             for sid, textos in TIPICOS.items() if sid in ativos for texto in textos]
    casos += [{"categoria": "ambiguo", "service_id": sid, "alternativa": alt, "texto": texto}
              for sid, alt, texto in AMBIGUOS_VALIDACAO if {sid, alt} <= ativos]
    base = path("synthetic")
    labels = gerar_teste(random.Random(20261109), np.random.default_rng(20261109),
                         base / "inbox_validacao", casos, "VAL")
    with (base / "labels_validacao.csv").open("w", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(fh, fieldnames=list(labels[0]))
        escritor.writeheader()
        escritor.writerows(labels)
    log.info("Validação gerada: %d pedidos; semente 20261109", len(labels))


if __name__ == "__main__":
    main()
