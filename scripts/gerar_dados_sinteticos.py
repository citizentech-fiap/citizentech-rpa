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
- fora_escopo (6)    -> assunto que não é um dos 10 serviços federais    -> revisao_humana
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
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robo.config import load_config, path  # noqa: E402

SEED = 20261105
MARCA = "DOCUMENTO FICTÍCIO - USO ACADÊMICO"
FONTS_DIR = Path("C:/Windows/Fonts")

# ---------------------------------------------------------------------------
# 1) Conjunto de TREINO do classificador (modelos + vocabulário)
# ---------------------------------------------------------------------------
NUCLEOS: dict[str, list[str]] = {
    "seguro_desemprego": [
        "como dou entrada no seguro desemprego", "quero pedir o seguro-desemprego",
        "tenho direito ao seguro desemprego", "quantas parcelas do seguro eu recebo",
        "onde solicito o seguro desemprego", "preciso dar entrada no seguro",
        "como faço pra receber o seguro desemprego", "qual o prazo pra pedir o seguro-desemprego",
        "o seguro desemprego pode ser pedido pela internet", "quero saber do meu seguro desemprego",
        "como requerer o benefício do seguro-desemprego", "posso pedir seguro desemprego pelo app",
        "como libero as parcelas do seguro desemprego",
    ],
    "cadunico": [
        "como faço o cadastro único", "quero me inscrever no CadÚnico", "preciso fazer o cadastro no cadunico",
        "onde atualizo meu cadastro único", "como entro no cadastro único pra receber bolsa família",
        "o que precisa pra fazer o cad único", "quero me cadastrar nos programas sociais do governo",
        "como agendo o cadastro no CRAS", "meu cadastro único está desatualizado, como resolvo",
        "quero tirar o NIS pelo cadastro único", "inscrição no cadastro único para baixa renda",
        "preciso do cadúnico pra tarifa social de energia", "como atualizar o cadúnico da minha família",
    ],
    "passaporte": [
        "como tiro o passaporte", "quero emitir passaporte", "quanto custa o passaporte e como agenda na polícia federal",
        "preciso de passaporte pra viajar", "como agendar atendimento pra passaporte na PF",
        "meu passaporte venceu, como renovo", "quero fazer o passaporte comum",
        "qual o passo a passo pra tirar passaporte", "como pago a GRU do passaporte",
        "perdi meu passaporte, preciso de outro", "quanto tempo demora pra ficar pronto o passaporte",
        "quais documentos pra solicitar passaporte", "como renovar passaporte vencido",
    ],
    "carteira_trabalho_digital": [
        "como acesso a carteira de trabalho digital", "quero baixar a carteira de trabalho digital",
        "como ativo a CTPS digital", "não consigo entrar na carteira de trabalho digital",
        "como emitir a carteira de trabalho pelo celular", "preciso da carteira de trabalho digital pro emprego novo",
        "onde vejo minha carteira de trabalho digital", "a carteira de trabalho agora é digital? como faço",
        "como tiro minha primeira carteira de trabalho", "quero ver meus contratos na carteira digital",
        "o aplicativo da carteira de trabalho não mostra meus dados", "como cadastrar na CTPS digital com o gov.br",
        "como pego o número da minha carteira de trabalho",
    ],
    "antecedentes_criminais": [
        "como tiro a certidão de antecedentes criminais", "preciso do atestado de antecedentes",
        "onde emito certidão negativa criminal da polícia federal", "como pego o atestado de bons antecedentes",
        "quero emitir antecedentes criminais online", "certidão de antecedentes criminais federal",
        "como consigo o nada consta criminal", "a certidão de antecedentes é de graça",
        "onde faço o atestado de antecedentes pela internet", "preciso comprovar que não tenho ficha criminal",
        "como emitir antecedentes da PF", "como validar a certidão de antecedentes criminais",
        "preciso de folha corrida criminal",
    ],
    "mei": [
        "como abro um MEI", "quero me formalizar como microempreendedor individual", "como faço pra virar MEI",
        "quero abrir CNPJ de MEI", "como emitir o CCMEI", "o que preciso pra ser MEI", "quero formalizar meu negócio",
        "como me cadastro como microempreendedor", "como abrir empresa MEI pelo portal do empreendedor",
        "quanto custa pra abrir MEI", "quero ter CNPJ pra emitir nota", "como me inscrevo no MEI pelo gov.br",
        "quero sair da informalidade e abrir meu CNPJ",
    ],
    "cpf": [
        "como tiro o CPF", "preciso fazer meu CPF", "meu CPF está suspenso, como regularizo",
        "como regularizar CPF pendente de regularização", "quero inscrever meu filho no CPF",
        "como fazer o CPF pela receita federal", "meu cpf tá irregular", "como atualizo os dados do meu CPF",
        "quero tirar CPF pela primeira vez", "como resolvo CPF cancelado", "preciso emitir o número do CPF",
        "como faz o CPF do meu bebê", "como corrijo o nome errado no CPF",
    ],
    "bpc": [
        "como peço o BPC", "quero solicitar o benefício de prestação continuada", "como dar entrada no LOAS",
        "meu filho autista tem direito ao BPC", "como pedir o benefício para idoso de baixa renda",
        "quero o BPC LOAS pro meu pai", "como solicitar o benefício assistencial no INSS",
        "pessoa com deficiência tem direito a um salário mínimo, como pede",
        "qual a renda pra ter direito ao BPC", "como agendo a perícia do BPC", "como pede o BPC pelo meu INSS",
        "o loas precisa de cadastro único", "quero o benefício assistencial da pessoa com deficiência",
    ],
    "aposentadoria_idade": [
        "como peço aposentadoria por idade", "quero me aposentar por idade", "já posso me aposentar",
        "como dar entrada na aposentadoria no INSS", "quanto tempo de contribuição precisa pra aposentar por idade",
        "como solicitar aposentadoria pelo meu INSS", "quero dar entrada na minha aposentadoria",
        "aposentadoria urbana por idade, como faz", "como simular minha aposentadoria",
        "quero requerer aposentadoria por idade", "qual a idade mínima pra aposentar",
        "como agendar a aposentadoria no INSS", "quero saber se já completei o tempo pra aposentar",
    ],
    "titulo_eleitor": [
        "como tiro o título de eleitor", "quero emitir meu primeiro título", "como faço o título de eleitor pela internet",
        "preciso regularizar meu título", "meu título foi cancelado, o que faço", "como transferir o título de eleitor",
        "como pego o e-título", "quero tirar título pra votar", "como emitir título de eleitor pelo titulo net",
        "como emito a segunda via do título", "onde faço o alistamento eleitoral", "como regularizo a situação eleitoral",
        "como pago a multa por não votar e regularizo o título",
    ],
    "fora_escopo": [
        "como pago o IPTU atrasado", "quero segunda via do IPTU da prefeitura", "tem um buraco enorme na minha rua",
        "o caminhão do lixo não passa aqui há uma semana", "a luz do poste da minha rua está queimada",
        "como recorrer de multa de trânsito municipal", "qual o horário do posto de saúde do bairro",
        "quero vaga na creche municipal pro meu filho", "minha internet cai toda hora e a operadora não resolve",
        "oi tudo bem com vocês", "quem ganhou o jogo ontem", "me passa uma receita de bolo de cenoura",
        "vai chover amanhã", "qual o melhor celular barato pra comprar",
        "comprei uma geladeira e veio quebrada e a loja não troca", "o vizinho faz barulho toda noite",
        "quero denunciar o som alto do bar da esquina", "como tiro alvará da prefeitura pra construir muro",
        "queria parcelar minha conta de água atrasada", "o ônibus da linha 302 vive atrasado",
        "só queria agradecer o atendimento", "vocês vendem passagem de ônibus",
        "quero cancelar minha assinatura de tv a cabo", "testando 123", "meu cachorro fugiu, alguém viu",
        "como peço licença pra festa junina na praça", "qual a senha do wifi",
        "o banco cobrou uma tarifa indevida no meu cartão",
    ],
}

CONTEXTOS: dict[str, list[str]] = {
    "seguro_desemprego": [
        "fui demitido sem justa causa", "fui mandado embora da firma", "a empresa me dispensou mês passado",
        "perdi meu emprego depois de 2 anos", "fiquei desempregado", "me demitiram semana passada",
        "fui desligado da empresa", "o patrão me mandou embora e deu a rescisão",
    ],
    "cadunico": [
        "estou sem renda nenhuma", "sou mãe solo com 3 filhos", "minha família é de baixa renda",
        "a assistente social mandou eu procurar", "ganho menos de meio salário mínimo", "estou passando necessidade",
        "me disseram que preciso disso pro bolsa família", "moro com meus avós e a renda é pouca",
    ],
    "passaporte": [
        "vou viajar pra Portugal ano que vem", "vou fazer intercâmbio", "quero conhecer a Argentina",
        "minha filha mora nos Estados Unidos", "ganhei uma viagem pra Europa", "vou trabalhar fora do país",
        "tenho uma viagem marcada em março", "nunca saí do Brasil",
    ],
    "carteira_trabalho_digital": [
        "vou começar no primeiro emprego", "o RH pediu minha carteira de trabalho", "perdi a carteira de papel",
        "nunca trabalhei registrado", "a empresa disse que agora é tudo digital", "tenho 18 anos e consegui um estágio",
        "fui contratado ontem", "minha carteira física molhou",
    ],
    "antecedentes_criminais": [
        "a empresa pediu pra contratação", "vou trabalhar como motorista de aplicativo", "é pra um concurso público",
        "pediram pro meu visto", "vou ser vigilante", "é pra um processo de adoção", "meu novo emprego exige",
        "pediram no processo seletivo",
    ],
    "mei": [
        "vendo bolo em casa", "sou manicure e atendo em casa", "faço entregas de moto", "tenho uma lojinha de roupas",
        "sou eletricista autônomo", "trabalho com artesanato", "quero vender na internet", "faço unhas e cabelo",
    ],
    "cpf": [
        "meu bebê nasceu mês passado", "não consigo abrir conta no banco", "deu CPF irregular na loja",
        "mudei de nome depois do casamento", "sou estrangeiro morando no Brasil", "nunca tive documento nenhum",
        "o sistema diz que meu CPF está suspenso", "perdi o cartão do cpf",
    ],
    "bpc": [
        "tenho 66 anos e nunca contribuí", "meu filho tem deficiência", "minha mãe é idosa e não tem renda",
        "sou cadeirante", "tenho doença grave e não consigo trabalhar", "moro sozinho e tenho 70 anos",
        "minha filha tem síndrome de down", "não tenho aposentadoria nenhuma",
    ],
    "aposentadoria_idade": [
        "fiz 65 anos", "tenho 62 anos e contribuí 15 anos", "trabalhei a vida toda registrado",
        "minha mãe completou 62 anos", "tenho mais de 20 anos de carteira assinada",
        "estou cansado de trabalhar e já tenho idade", "contribuí como autônomo por muitos anos", "meu marido fez 65",
    ],
    "titulo_eleitor": [
        "fiz 16 anos", "vou votar pela primeira vez", "mudei de cidade", "não votei nas últimas eleições",
        "perdi meu título", "fiz 18 anos e preciso pro alistamento", "o concurso pediu quitação eleitoral",
        "me mudei de estado",
    ],
    "fora_escopo": [
        "moro aqui faz 10 anos", "já reclamei várias vezes", "sou de Recife", "tô sem paciência",
        "é a terceira vez que escrevo", "ninguém resolve nada", "minha vizinha falou pra perguntar aqui",
    ],
}

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
    c = rng.choice(CONTEXTOS[sid])
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
    for sid in NUCLEOS:
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
    "seguro_desemprego": [
        "Boa tarde. Trabalhei 3 anos numa padaria e semana passada o dono fechou as portas e dispensou todo mundo. "
        "Recebi o acerto. Queria saber como faço para receber as parcelas do auxílio para quem ficou sem trabalho.",
        "fui dispensado da metalurgica dia 20, ja tenho o TRCT em maos. o que preciso mandar pra liberar o seguro?",
        "Prezados, após minha demissão sem justa causa gostaria de requerer o seguro-desemprego. Segue documentação "
        "em anexo. Meu CPF é 000.111.222-30.",
        "me mandaram embora do mercado e o gerente falou q eu tenho direito a umas parcelas do governo, como pede isso",
        "Olá, é a primeira vez que fico desempregada. Como funciona o pedido do benefício do desemprego? "
        "Telefone (11) 90000-1234.",
        "Perdi o emprego em outubro. Dá pra solicitar o seguro desemprego por aqui mesmo? Estou enviando meus documentos.",
    ],
    "cadunico": [
        "Bom dia, a moça do CRAS falou que eu tenho que me registrar no cadastro do governo pra conseguir o Bolsa "
        "Família. Como faço?",
        "sou diarista, crio meus dois netos sozinha e nao tenho cadastro em programa social nenhum. quero fazer a inscrição",
        "Gostaria de incluir minha família no CadÚnico, estamos sem renda fixa desde o começo do ano.",
        "preciso atualizar o cad unico porque mudei de endereço e nasceu mais um filho",
        "Olá! Quero ter acesso à tarifa social de luz e me disseram que precisa estar no Cadastro Único. Como me inscrevo?",
        "Minha renda é muito baixa e queria participar dos programas sociais federais. Envio meus documentos para o cadastro.",
    ],
    "passaporte": [
        "Olá, vou visitar minha irmã no Canadá em julho e nunca tive passaporte. Como faço para emitir o meu?",
        "Preciso renovar meu passaporte que venceu ano passado, segue documentação.",
        "como agenda na policia federal pra fazer o documento de viagem internacional? passaporte mesmo",
        "Boa noite, fui roubado e levaram meu passaporte. Preciso tirar um novo antes da viagem de dezembro.",
        "Quero solicitar o passaporte comum para meu intercâmbio na Irlanda, quais são os passos?",
        "Envio meus documentos para pedir o passaporte. Já paguei a taxa.",
    ],
    "carteira_trabalho_digital": [
        "Fui aprovado num processo seletivo e o RH pediu o número da minha carteira de trabalho, mas eu nunca tirei. "
        "Como consigo a digital?",
        "nao acho minha ctps no aplicativo, como faço pra habilitar a carteira digital?",
        "Olá, gostaria de obter a Carteira de Trabalho Digital. Anexo meu CPF.",
        "Minha carteira de trabalho de papel rasgou toda. Agora tem a versão no celular? Como ativo?",
        "Tenho 17 anos e vou ser jovem aprendiz, preciso da carteira de trabalho, como emito?",
        "como eu vejo meus registros de emprego na carteira de trabalho pelo celular?",
    ],
    "antecedentes_criminais": [
        "Bom dia. Estou me cadastrando como motorista de aplicativo e pediram certidão de antecedentes da Polícia "
        "Federal. Como emito?",
        "preciso de um documento que prove que eu nao tenho passagem pela policia, pra entregar na empresa",
        "Olá, para o meu visto de trabalho precisam de um atestado criminal federal. Onde solicito?",
        "Como emitir a certidão negativa de antecedentes criminais? É para posse em concurso.",
        "Me pediram o nada consta da PF pra vaga de segurança. como tiro?",
        "Quero tirar o atestado de antecedentes, segue meu RG e CPF.",
    ],
    "mei": [
        "Faço docinhos para festa há dois anos e quero ter CNPJ para vender para empresas. Como me formalizo?",
        "quero sair da informalidade, sou pedreiro. abrir o mei é complicado?",
        "Olá, gostaria de me registrar como microempreendedor individual. Seguem documentos.",
        "Como faço pra ter um CNPJ pequeno pra emitir nota fiscal dos meus serviços de design?",
        "Boa tarde, tenho um food truck e quero me formalizar como MEI, o que preciso?",
        "Quero abrir minha empresinha de costura como MEI, meu e-mail é costura.ficticia@exemplo.com",
    ],
    "cpf": [
        "Minha filha nasceu ontem e preciso fazer o CPF dela. Como funciona?",
        "Fui no banco abrir conta e disseram que meu cadastro na Receita está suspenso. Como regularizo?",
        "nunca tirei cpf, tenho 19 anos, como faço a inscrição?",
        "Casei e mudei de sobrenome, preciso atualizar os dados no CPF. Segue certidão.",
        "meu cpf aparece pendente de regularização na receita federal, o que faço pra resolver?",
        "Gostaria de inscrever meu enteado no Cadastro de Pessoas Físicas.",
    ],
    "bpc": [
        "Meu filho tem paralisia cerebral e eu não trabalho para cuidar dele. Ouvi falar de um benefício de um "
        "salário mínimo, como peço?",
        "minha avó tem 68 anos, nunca pagou inss e vive com a gente sem renda. ela pode receber o loas?",
        "Gostaria de solicitar o Benefício de Prestação Continuada para pessoa com deficiência. Seguem documentos.",
        "Sou deficiente visual e estou desempregado há anos, queria saber do benefício assistencial do INSS.",
        "Como dou entrada no BPC idoso pra minha mãe de 72 anos?",
        "tenho uma doença que me impede de trabalhar e minha família é pobre, tenho direito ao bpc?",
    ],
    "aposentadoria_idade": [
        "Completei 65 anos mês passado e tenho 18 anos de contribuição. Como faço para me aposentar?",
        "minha mae ja tem 63 anos e trabalhou de carteira assinada a vida toda, como ela pede a aposentadoria?",
        "Prezados, venho requerer minha aposentadoria por idade urbana. Documentos anexos.",
        "quero parar de trabalhar, ja tenho idade pra aposentar? como dou entrada no inss?",
        "Boa tarde, quais os passos pra pedir a aposentadoria do meu pai que fez 66?",
        "Gostaria de dar entrada no benefício de aposentadoria, já tenho a idade mínima e o tempo de contribuição.",
    ],
    "titulo_eleitor": [
        "Fiz 18 anos e quero votar na próxima eleição. Como tiro meu título?",
        "Me mudei de Salvador pra Curitiba e preciso transferir meu domicílio eleitoral.",
        "faltei em 3 eleições seguidas e acho q meu título foi cancelado, como regularizo?",
        "Olá, preciso de quitação eleitoral para tomar posse, mas nunca fiz o alistamento. Como emito o título?",
        "Quero fazer meu primeiro título de eleitor, tenho 16 anos.",
        "Perdi meu título, como faço pra emitir outro? Envio meus documentos.",
    ],
}

AMBIGUOS: list[tuple[str, str, str]] = [
    ("seguro_desemprego", "aposentadoria_idade",
     "Fui demitido e já tenho 65 anos, não sei se peço o seguro-desemprego ou já dou entrada na aposentadoria."),
    ("mei", "cpf", "Quero abrir um MEI mas meu CPF está suspenso, o que faço primeiro?"),
    ("bpc", "cadunico", "Minha mãe idosa não tem renda nenhuma, ela precisa fazer o cadastro único ou pedir o BPC?"),
    ("passaporte", "titulo_eleitor",
     "Vou viajar pro exterior e meu título de eleitor está cancelado, isso atrapalha? O que preciso regularizar?"),
    ("seguro_desemprego", "mei",
     "Perdi meu emprego e quero começar a trabalhar por conta própria, peço o seguro ou abro um MEI?"),
    ("carteira_trabalho_digital", "antecedentes_criminais",
     "Preciso da carteira de trabalho e também de certidão de antecedentes para a nova vaga, por onde começo?"),
]

FORA_ESCOPO_TESTE: list[tuple[str, list[str]]] = [
    ("Gostaria de saber como emitir a guia do IPTU deste ano, o carnê não chegou em casa.", ["comprovante_residencia"]),
    ("A rua da minha casa está sem asfalto e alaga toda vez que chove. Quem resolve?", []),
    ("Oi, vocês sabem me dizer se a farmácia do shopping abre domingo?", []),
    ("boa noite, qual time vocês torcem?", []),
    ("Recebi uma multa da guarda municipal e quero recorrer, como faço?", ["documento_identidade"]),
    ("Comprei um celular pela internet e não entregaram, quero meu dinheiro de volta.", []),
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
CIDADES = ["São Paulo/SP", "Recife/PE", "Belo Horizonte/MG", "Porto Alegre/RS", "Salvador/BA", "Manaus/AM",
           "Fortaleza/CE", "Curitiba/PR", "Goiânia/GO", "Belém/PA"]
RUAS = ["Rua Fictícia", "Avenida Exemplo", "Travessa Imaginária", "Rua das Amostras", "Alameda do Teste"]
EMPRESAS = ["Padaria Fictícia Ltda", "Metalúrgica Exemplo S.A.", "Mercado Imaginário Ltda", "Comércio Teste ME",
            "Indústria Modelo Ltda"]


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


def pessoa_ficticia(rng: random.Random) -> dict[str, str]:
    nome = rng.choice(NOMES)
    return {
        "nome": nome,
        "cpf": cpf_ficticio(rng),
        "rg": f"{rng.randrange(10, 99)}.{rng.randrange(100, 999)}.{rng.randrange(100, 999)}-{rng.randrange(10)}",
        "nasc": f"{rng.randrange(1, 28):02d}/{rng.randrange(1, 12):02d}/{rng.randrange(1950, 2006)}",
        "mae": rng.choice(MAES),
        "pai": rng.choice(PAIS),
        "cidade": rng.choice(CIDADES),
        "endereco": f"{rng.choice(RUAS)}, {rng.randrange(10, 999)} - Bairro Exemplo",
        "cep": f"00{rng.randrange(100, 999)}-000",
        "empresa": rng.choice(EMPRESAS),
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
    if tipo == "carteira_trabalho":
        return ("CARTEIRA DE TRABALHO E PREVIDÊNCIA SOCIAL", "MINISTÉRIO DO TRABALHO E EMPREGO - CTPS",
                [("NÚMERO", f"{rng.randrange(1000000, 9999999)}"), ("SÉRIE", f"{rng.randrange(100, 999)}-SP"),
                 ("NOME", p["nome"]), ("CPF", p["cpf"]), ("CONTRATO DE TRABALHO - EMPREGADOR", p["empresa"]),
                 ("DATA DE ADMISSÃO", f"02/0{rng.randrange(1, 9)}/20{rng.randrange(10, 23)}"),
                 ("CARGO", rng.choice(["Auxiliar Administrativo", "Operador", "Vendedor(a)", "Padeiro(a)"]))])
    if tipo == "termo_rescisao":
        return ("TERMO DE RESCISÃO DO CONTRATO DE TRABALHO", "TRCT - IDENTIFICAÇÃO DO EMPREGADOR E DO TRABALHADOR",
                [("EMPREGADOR", p["empresa"]), ("CNPJ", "00.000.000/0001-00"), ("TRABALHADOR", p["nome"]),
                 ("CPF", p["cpf"]), ("CAUSA DO AFASTAMENTO", "DISPENSA SEM JUSTA CAUSA"),
                 ("DATA DE AFASTAMENTO", f"{rng.randrange(1, 28):02d}/09/2026"),
                 ("TOTAL DAS VERBAS RESCISÓRIAS", f"R$ {rng.randrange(1500, 9000)},00")])
    if tipo == "titulo_eleitor":
        titulo = rng.choice(["TÍTULO ELEITORAL", "TÍTULO DE ELEITOR"])
        return (titulo, "JUSTIÇA ELEITORAL - TRIBUNAL SUPERIOR ELEITORAL",
                [("NOME DO ELEITOR", p["nome"]), ("INSCRIÇÃO", f"0000 {rng.randrange(1000, 9999)} {rng.randrange(1000, 9999)}"),
                 ("ZONA", f"{rng.randrange(1, 400):03d}"), ("SEÇÃO", f"{rng.randrange(1, 900):04d}"),
                 ("MUNICÍPIO / UF", p["cidade"]), ("DATA DE EMISSÃO", "15/08/2022")])
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
        titulo = rng.choice(["COMPROVANTE DE RENDIMENTOS", "DEMONSTRATIVO DE PAGAMENTO - CONTRACHEQUE",
                             "HOLERITE - COMPROVANTE DE RENDIMENTOS"])
        bruto = rng.randrange(900, 3000)
        return (titulo, p["empresa"].upper(),
                [("FUNCIONÁRIO", p["nome"]), ("CPF", p["cpf"]), ("COMPETÊNCIA", "09/2026"),
                 ("SALÁRIO BRUTO", f"R$ {bruto},00"), ("DESCONTOS (INSS/IRRF)", f"R$ {bruto // 10},00"),
                 ("VALOR LÍQUIDO", f"R$ {bruto - bruto // 10},00")])
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
        tam = 36
        larg = d.textlength(titulo, font=fonte(neg, tam))
        while larg > W - 2 * margem and tam > 14:
            tam -= 2
            larg = d.textlength(titulo, font=fonte(neg, tam))
        d.text(((W - larg) / 2, 45), titulo, font=fonte(neg, tam), fill=cor_txt)
        _texto_ajustado(d, (margem, 105), sub, reg, 22, W - 2 * margem, fill=(70, 70, 70))
        y = 170
        for rot, val in campos:
            _texto_ajustado(d, (margem, y), f"{rot}: {val}", reg, 25, W - 2 * margem, fill=cor_txt)
            y += rng.randrange(52, 64)
    elif layout == 1:  # faixa colorida no topo, campos em duas colunas
        faixa = rng.choice([(30, 80, 140), (20, 110, 70), (120, 40, 40), (60, 60, 60)])
        d.rectangle([0, 0, W, 130], fill=faixa)
        _texto_ajustado(d, (margem, 28), titulo, neg, 34, W - 2 * margem, fill=(255, 255, 255))
        _texto_ajustado(d, (margem, 82), sub, reg, 20, W - 2 * margem, fill=(235, 235, 235))
        col_w = (W - 3 * margem) // 2
        for i, (rot, val) in enumerate(campos):
            x = margem + (i % 2) * (col_w + margem)
            y = 175 + (i // 2) * 105
            _texto_ajustado(d, (x, y), rot, neg, 18, col_w, fill=(90, 90, 90))
            _texto_ajustado(d, (x, y + 28), val, reg, 25, col_w, fill=cor_txt)
            d.line([x, y + 64, x + col_w, y + 64], fill=(180, 180, 180), width=1)
    else:  # título à esquerda em caixa, campos em tabela, quadro de foto em alguns tipos
        d.rectangle([margem - 15, 30, W - margem + 15, 120], outline=cor_txt, width=2)
        _texto_ajustado(d, (margem, 45), titulo, neg, 32, W - 2 * margem, fill=cor_txt)
        _texto_ajustado(d, (margem, 88), sub, reg, 18, W - 2 * margem, fill=(80, 80, 80))
        x_tab = margem
        larg_tab = W - 2 * margem
        if tipo in ("documento_identidade", "carteira_trabalho", "titulo_eleitor"):
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
    linhas: list[bytes] = [b"BT", b"/F2 18 Tf", b"50 780 Td", _pdf_str(titulo) + b" Tj", b"ET",
                           b"BT", b"/F1 11 Tf", b"50 755 Td", _pdf_str(sub) + b" Tj", b"ET"]
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
ABREV = {"documento_identidade": "rg", "cpf": "cpf", "comprovante_residencia": "residencia",
         "carteira_trabalho": "ctps", "termo_rescisao": "trct", "titulo_eleitor": "titulo",
         "certidao_civil": "certidao", "comprovante_renda": "renda"}
MODOS_ILEGIVEL = ["desfoque", "ruido", "contraste", "rotacao", "pixelado"]


def plano_de_casos() -> list[dict]:
    """Lista de casos (categoria, serviço) na ordem de alocação dos textos de teste."""
    sids = list(TEXTOS_TESTE)
    casos: list[dict] = []
    for sid in sids * 2 + ["seguro_desemprego", "cadunico", "bpc", "aposentadoria_idade", "mei"]:
        casos.append({"categoria": "tipico", "service_id": sid})
    for sid in sids + ["seguro_desemprego", "passaporte"]:
        casos.append({"categoria": "docs_faltando", "service_id": sid})
    for sid in ["seguro_desemprego", "passaporte", "cpf", "bpc", "titulo_eleitor"]:
        casos.append({"categoria": "ilegivel", "service_id": sid})
    for sid, alt, txt in AMBIGUOS:
        casos.append({"categoria": "ambiguo", "service_id": sid, "alternativa": alt, "texto": txt})
    for txt, docs in FORA_ESCOPO_TESTE:
        casos.append({"categoria": "fora_escopo", "service_id": "fora_escopo", "texto": txt, "docs": docs})
    casos += [
        {"categoria": "invalido", "service_id": "cadunico", "falha": "json_truncado"},
        {"categoria": "invalido", "service_id": "mei", "falha": "json_aspas_simples"},
        {"categoria": "invalido", "service_id": "antecedentes_criminais", "falha": "sem_texto"},
        {"categoria": "invalido", "service_id": "aposentadoria_idade", "falha": "texto_vazio"},
        {"categoria": "invalido", "service_id": "titulo_eleitor", "falha": "anexo_inexistente"},
        {"categoria": "invalido", "service_id": "carteira_trabalho_digital", "falha": "anexo_fora_da_inbox"},
    ]
    return casos


def gerar_teste(rng: random.Random, nrng: np.random.Generator, out_dir: Path) -> list[dict]:
    cfg = load_config()
    exigidos = {s["id"]: list(s["documentos_exigidos"]) for s in cfg["services"]}
    todos_tipos = list(cfg["document_types"])
    anexos_dir = out_dir / "anexos"
    anexos_dir.mkdir(parents=True, exist_ok=True)

    casos = plano_de_casos()
    ids = list(range(1, len(casos) + 1))
    rng.shuffle(ids)  # categorias espalhadas, não em blocos
    proximo_texto = {sid: 0 for sid in TEXTOS_TESTE}
    pdf_texto_restantes, pdf_scan_restantes = 6, 2
    modos = list(MODOS_ILEGIVEL)
    labels: list[dict] = []

    for caso, num in zip(casos, ids):
        rid = f"REQ-{num:04d}"
        cat, sid = caso["categoria"], caso["service_id"]
        if "texto" in caso:
            texto = caso["texto"]
        elif caso.get("falha") in ("sem_texto", "texto_vazio"):
            texto = ""
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

        pessoa = pessoa_ficticia(rng)
        anexos_rel: list[str] = []
        presentes: list[str] = []
        ilegiveis: list[str] = []
        obs = ""
        tipo_ilegivel = rng.choice(docs) if cat == "ilegivel" else None
        falha = caso.get("falha")

        for tipo in docs:
            if falha in ("anexo_inexistente", "anexo_fora_da_inbox"):
                break
            if (cat == "tipico" and tipo in ("comprovante_residencia", "comprovante_renda", "certidao_civil")
                    and pdf_texto_restantes > 0 and rng.random() < 0.6):
                nome = f"{rid}_{ABREV[tipo]}.pdf"
                escrever_pdf_texto(anexos_dir / nome, tipo, pessoa, rng)
                pdf_texto_restantes -= 1
            else:
                img = renderizar_documento(tipo, pessoa, rng)
                if tipo == tipo_ilegivel:
                    modo = modos.pop(0)
                    img = degradar(img, modo, nrng)
                    obs = f"anexo {ABREV[tipo]} degradado ({modo})"
                if cat == "tipico" and pdf_scan_restantes > 0 and tipo in ("documento_identidade", "titulo_eleitor") \
                        and rng.random() < 0.5:
                    nome = f"{rid}_{ABREV[tipo]}.pdf"
                    img.save(anexos_dir / nome, "PDF", resolution=100.0)  # PDF escaneado (sem texto)
                    pdf_scan_restantes -= 1
                else:
                    nome = f"{rid}_{ABREV[tipo]}.png"
                    img.save(anexos_dir / nome, "PNG", optimize=True)
            anexos_rel.append(f"anexos/{nome}")
            (ilegiveis if tipo == tipo_ilegivel else presentes).append(tipo)

        dados = {
            "request_id": rid,
            "data_envio": f"2026-11-{rng.randrange(1, 5):02d}T{rng.randrange(7, 22):02d}:{rng.randrange(60):02d}:00-03:00",
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
            "observacao": obs,
        })
    labels.sort(key=lambda r: r["request_id"])
    return labels


def main() -> None:
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
    if inbox.exists():
        shutil.rmtree(inbox)  # regeneração limpa (só a pasta gerada por este script)
    inbox.mkdir(parents=True)
    labels = gerar_teste(rng, nrng, inbox)
    campos = ["request_id", "service_id", "docs_presentes", "docs_ilegiveis", "resultado_esperado",
              "categoria", "observacao"]
    with open(base / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(labels)

    from collections import Counter
    print(f"Treino: {len(treino)} frases -> {dict(Counter(s for _, s in treino))}")
    print(f"Teste: {len(labels)} solicitações -> {dict(Counter(r['categoria'] for r in labels))}")
    n_anexos = len(list((inbox / "anexos").iterdir()))
    print(f"Anexos gerados: {n_anexos} em {inbox / 'anexos'}")


if __name__ == "__main__":
    main()
