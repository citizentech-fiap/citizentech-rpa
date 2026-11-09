"""Textos sintéticos exclusivos da validação; não usados para treinar o modelo."""
TIPICOS = {
    "garantia_safra": [
        "A estiagem arrasou o cultivo de algodão e estou inscrito no Garantia-Safra. Onde acompanho minha compensação?",
        "O município confirmou a perda agrícola. Quero apresentar os papéis do seguro safra.",
        "Adesão ao Garantia Safra feita, lavoura perdida: falta alguma etapa para receber?"],
    "caf": [
        "Nossa unidade familiar começou a produzir mel. Como abrimos o CAF pela primeira vez?",
        "A validade do registro CAF terminou ontem. Quem faz a renovação para nós?",
        "Preciso acrescentar meu filho ao cadastro da agricultura familiar e emitir outro extrato."],
    "pronaf": [
        "Quero contratar Pronaf para um pequeno trator, devolvendo o empréstimo com a produção.",
        "O banco atende financiamento familiar de estufa? Preciso conhecer o crédito do Pronaf.",
        "Planejo ampliar o galinheiro com empréstimo agrícola subsidiado. Como entregar a proposta?"],
    "aposentadoria_rural": [
        "Cheguei à idade de me aposentar como trabalhador rural e reuni comprovantes de quinze safras.",
        "Minha esposa agricultora quer protocolar aposentadoria por idade no INSS. Qual atendimento procurar?",
        "Produzo em economia familiar desde jovem e agora busco aposentadoria rural, com prova do trabalho."],
    "salario_maternidade_rural": [
        "Minha bebê nasceu nesta semana. Trabalho na roça e quero requerer salário-maternidade rural.",
        "Durante o afastamento pelo parto, como a segurada especial pede auxílio maternidade?",
        "Adotei um recém-nascido e preciso interromper o cultivo. Solicito o salário maternidade da agricultora."],
    "cadunico": [
        "Nossa família mudou de comunidade. Quero atualizar endereço no Cadastro Único.",
        "Vou ao CRAS cadastrar os rendimentos de todos os moradores no CadÚnico. Que documentos levo?",
        "Precisamos fazer a entrevista inicial para inscrição no cadastro social único do governo."],
    "bolsa_familia": [
        "Já atualizei os dados e quero consultar a concessão do Bolsa Família para meus filhos.",
        "Recebia Bolsa Família até mês passado. Como descubro o motivo do bloqueio das parcelas?",
        "Estou aguardando aprovação no programa Bolsa Família. Onde consulto o repasse?"],
    "bpc": [
        "Tenho deficiência e nenhuma renda. Preciso iniciar o requerimento do BPC LOAS.",
        "Minha tia idosa sem contribuição quer solicitar benefício assistencial de prestação continuada.",
        "Quais papéis apresento para a perícia do BPC do meu filho com deficiência?"],
    "cpf": [
        "Preciso regularizar CPF suspenso na Receita Federal antes de abrir conta.",
        "O número do CPF saiu com meu nome incorreto. Como solicitar alteração cadastral?",
        "Quero emitir a primeira inscrição CPF para meu filho, que só tem certidão."],
}

AMBIGUOS_VALIDACAO = [
    ("garantia_safra", "pronaf", "Preciso receber Garantia Safra pela seca e obter Pronaf para irrigação. Tenho dois requerimentos."),
    ("pronaf", "garantia_safra", "Além de contratar financiamento Pronaf, quero cobrar as parcelas da perda agrícola. Como peço ambos?"),
    ("caf", "pronaf", "Peço renovação do CAF e também empréstimo para comprar sementes. Quero tratar das duas solicitações."),
    ("pronaf", "caf", "Meu projeto do Pronaf precisa sair, mas também quero cadastrar minha unidade familiar no CAF."),
    ("cadunico", "bolsa_familia", "Desejo nova inscrição no CadÚnico e solicitar a transferência Bolsa Família para as crianças."),
    ("bolsa_familia", "cadunico", "Quero desbloquear parcelas do Bolsa Família e corrigir o endereço na entrevista do Cadastro Único."),
    ("aposentadoria_rural", "bpc", "Sou idoso sem renda, trabalhei no campo. Não sei se solicito aposentadoria rural ou BPC LOAS."),
    ("bpc", "aposentadoria_rural", "Minha mãe tem idade para o amparo assistencial, mas também anos de agricultura. BPC ou aposentadoria?"),
    ("cpf", "caf", "Tenho que corrigir o CPF na Receita e renovar o CAF no sindicato, podem ajudar com os dois?"),
    ("salario_maternidade_rural", "bolsa_familia", "Acabei de dar à luz e quero salário maternidade rural e inclusão no Bolsa Família ao mesmo tempo."),
    ("caf", "garantia_safra", "Preciso fazer o cadastro da agricultura familiar e requerer indenização do Garantia-Safra pela lavoura seca."),
    ("cadunico", "bpc", "Meu filho tem deficiência. Vim atualizar Cadastro Único e dar entrada no BPC, são dois pedidos."),
]
