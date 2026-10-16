"""Catálogo inicial: atos atendidos (act_requirements) e tabelas de emolumentos (fee_schedules).

ATENÇÃO: os valores de emolumentos abaixo são ILUSTRATIVOS, para demonstração do MVP.
Antes de usar com o público, substitua-os pela tabela oficial vigente publicada pela
Corregedoria-Geral da Justiça do seu estado (em SP: Lei Estadual 11.331/2002 e tabelas anuais).
"""

ILLUSTRATIVE_SOURCE = (
    "Valores ilustrativos do MVP — substituir pela tabela oficial vigente da Corregedoria-Geral da Justiça."
)

ID_TYPES = ["RG", "CNH", "Carteira de Identidade", "Passaporte", "Carteira profissional (OAB, CRM etc.)"]

ACT_REQUIREMENTS: list[dict] = [
    {
        "act_type": "inventario_extrajudicial",
        "name": "Inventário Extrajudicial",
        "summary": (
            "Partilha dos bens de quem faleceu feita em cartório, sem processo judicial. "
            "Exige que todos os herdeiros estejam de acordo e a presença de um advogado."
        ),
        "keywords": ["inventario", "inventário", "partilha", "heranca", "herança", "faleceu", "falecimento",
                     "obito", "óbito", "espolio", "espólio", "herdeiro"],
        "requires_declared_value": True,
        "value_question": (
            "Qual é o valor total aproximado dos bens deixados (imóveis, veículos, saldos bancários etc.)? "
            "Pode responder algo como \"450 mil\"."
        ),
        "documents": [
            {"doc_name": "Certidão de Óbito do Autor da Herança",
             "description": "Certidão de óbito de quem faleceu.",
             "accepted_types": ["Certidão de Óbito"]},
            {"doc_name": "Comprovante de Inexistência de Testamento (CENSEC)",
             "description": "Certidão da Central Notarial (CENSEC) informando se há testamento.",
             "accepted_types": ["Certidão CENSEC", "Certidão negativa de testamento"]},
            {"doc_name": "Certidão de Casamento do Falecido (atualizada 90 dias)",
             "description": "Ou certidão de nascimento, se era solteiro. Emitida há no máximo 90 dias.",
             "max_age_days": 90,
             "accepted_types": ["Certidão de Casamento", "Certidão de Nascimento"]},
            {"doc_name": "Documentos Pessoais dos Herdeiros (RG e CPF)",
             "description": "Documento de identidade com foto de cada herdeiro.",
             "accepted_types": ID_TYPES},
            {"doc_name": "IPTU / ITR dos Imóveis",
             "description": "Carnê ou certidão de valor venal do IPTU (urbano) ou ITR/CCIR (rural).",
             "accepted_types": ["Carnê de IPTU", "Certidão de valor venal", "ITR", "CCIR"]},
        ],
        "fee_rule": {"kind": "tiered", "service_type": "inventario_extrajudicial"},
        "notes": [
            "É obrigatória a assistência de advogado(a) ou defensor(a) público(a).",
            "O ITCMD (imposto estadual sobre herança) é recolhido à parte e não está incluído na estimativa.",
        ],
    },
    {
        "act_type": "escritura_compra_venda",
        "name": "Escritura de Compra e Venda de Imóvel",
        "summary": "Escritura pública que formaliza a compra e venda de um imóvel.",
        "keywords": ["escritura", "compra e venda", "comprar imovel", "comprar imóvel", "vender imovel",
                     "vender imóvel", "compra de imovel", "compra de imóvel", "venda de imovel", "venda de imóvel"],
        "requires_declared_value": True,
        "value_question": "Qual é o valor da venda do imóvel (ou o valor venal, se for maior)?",
        "documents": [
            {"doc_name": "RG e CPF de Compradores e Vendedores",
             "description": "Documento de identidade com foto de todas as partes.",
             "accepted_types": ID_TYPES},
            {"doc_name": "Certidão de Matrícula do Imóvel (atualizada 30 dias)",
             "description": "Emitida pelo Registro de Imóveis há no máximo 30 dias.",
             "max_age_days": 30,
             "accepted_types": ["Certidão de Matrícula"]},
            {"doc_name": "Certidão de Estado Civil dos Vendedores (atualizada 90 dias)",
             "description": "Certidão de nascimento ou casamento emitida há no máximo 90 dias.",
             "max_age_days": 90,
             "accepted_types": ["Certidão de Casamento", "Certidão de Nascimento"]},
            {"doc_name": "Guia de ITBI Paga",
             "description": "Guia do imposto municipal de transmissão com comprovante de pagamento.",
             "accepted_types": ["Guia de ITBI", "Comprovante de pagamento de ITBI"]},
        ],
        "fee_rule": {"kind": "tiered", "service_type": "escritura_com_valor"},
        "notes": ["O ITBI e o registro no Registro de Imóveis são pagos à parte."],
    },
    {
        "act_type": "habilitacao_casamento",
        "name": "Habilitação de Casamento",
        "summary": "Processo que antecede o casamento civil, verificando se o casal pode se casar.",
        "keywords": ["casamento", "casar", "habilitacao", "habilitação", "noivo", "noiva", "matrimonio",
                     "matrimônio", "proclamas"],
        "requires_declared_value": False,
        "documents": [
            {"doc_name": "Certidão de Nascimento Atualizada (90 dias)",
             "description": "De cada um dos noivos, emitida há no máximo 90 dias.",
             "max_age_days": 90,
             "accepted_types": ["Certidão de Nascimento", "Certidão de Casamento com averbação de divórcio"]},
            {"doc_name": "Documento de Identidade com Foto",
             "description": "RG, CNH ou passaporte de cada noivo.",
             "accepted_types": ID_TYPES},
            {"doc_name": "Comprovante de Residência",
             "description": "Conta de água, luz, telefone ou internet dos últimos 90 dias.",
             "max_age_days": 90,
             "accepted_types": ["Comprovante de Residência", "Conta de consumo"]},
        ],
        "fee_rule": {"kind": "fixed", "service_type": "atos_valor_fixo", "fixed_key": "habilitacao_casamento"},
        "notes": ["São necessárias duas testemunhas maiores de 18 anos no dia da habilitação."],
    },
    {
        "act_type": "procuracao_imovel",
        "name": "Procuração Pública de Imóvel",
        "summary": "Procuração lavrada em cartório para que outra pessoa represente você em atos sobre um imóvel.",
        "keywords": ["procuracao", "procuração", "procurador", "representar", "outorgar", "outorgante"],
        "requires_declared_value": False,
        "documents": [
            {"doc_name": "RG e CPF do Outorgante",
             "description": "Documento de identidade com foto de quem dá a procuração.",
             "accepted_types": ID_TYPES},
            {"doc_name": "Certidão de Matrícula do Imóvel",
             "description": "Para identificar corretamente o imóvel na procuração.",
             "max_age_days": 30,
             "accepted_types": ["Certidão de Matrícula"]},
            {"doc_name": "Certidão de Estado Civil do Outorgante",
             "description": "Certidão de nascimento ou casamento.",
             "accepted_types": ["Certidão de Casamento", "Certidão de Nascimento"]},
        ],
        "fee_rule": {"kind": "fixed", "service_type": "atos_valor_fixo", "fixed_key": "procuracao_imovel"},
        "notes": ["Os dados completos do procurador (nome, CPF, endereço) serão solicitados no balcão."],
    },
    {
        "act_type": "certidao_breve_relato",
        "name": "Certidão de Breve Relato",
        "summary": "Certidão resumida de um ato já lavrado (escritura, procuração etc.).",
        "keywords": ["breve relato", "certidao resumida", "certidão resumida", "segunda via", "2a via", "2ª via"],
        "requires_declared_value": False,
        "documents": [
            {"doc_name": "Documento de Identidade do Solicitante",
             "description": "RG, CNH ou passaporte de quem está pedindo a certidão.",
             "accepted_types": ID_TYPES},
        ],
        "fee_rule": {"kind": "fixed", "service_type": "atos_valor_fixo", "fixed_key": "certidao_breve_relato"},
        "notes": ["Informe, se souber, o livro e a folha do ato original para agilizar a busca."],
    },
    {
        "act_type": "certidao_inteiro_teor",
        "name": "Certidão de Inteiro Teor",
        "summary": "Cópia integral e fiel de um ato já lavrado.",
        "keywords": ["inteiro teor", "certidao completa", "certidão completa", "copia integral", "cópia integral"],
        "requires_declared_value": False,
        "documents": [
            {"doc_name": "Documento de Identidade do Solicitante",
             "description": "RG, CNH ou passaporte de quem está pedindo a certidão.",
             "accepted_types": ID_TYPES},
        ],
        "fee_rule": {"kind": "fixed", "service_type": "atos_valor_fixo", "fixed_key": "certidao_inteiro_teor"},
        "notes": ["Informe, se souber, o livro e a folha do ato original para agilizar a busca."],
    },
]


def _tiers(rows: list[tuple]) -> list[dict]:
    return [
        {"min_value": lo, "max_value": hi, "notary_fee": fee, "state_fund": fund, "municipal_tax_percent": 5.0}
        for lo, hi, fee, fund in rows
    ]


FEE_SCHEDULES: list[dict] = [
    {
        "_id": "fee_escritura_sp_2026",
        "state": "SP",
        "service_type": "escritura_com_valor",
        "label": "Escrituras com valor declarado",
        "valid_from": "2026-01-01",
        "source": ILLUSTRATIVE_SOURCE,
        "municipal_tax_percent": 5.0,
        "tiers": _tiers([
            (0.0, 50000.0, 420.50, 85.10),
            (50000.01, 150000.0, 890.00, 180.20),
            (150000.01, 300000.0, 1350.00, 273.40),
            (300000.01, 500000.0, 1980.00, 400.80),
            (500000.01, 1000000.0, 2740.00, 554.70),
            (1000000.01, None, 3600.00, 728.80),
        ]),
        "fixed_services": {},
    },
    {
        "_id": "fee_inventario_sp_2026",
        "state": "SP",
        "service_type": "inventario_extrajudicial",
        "label": "Inventário e partilha extrajudicial",
        "valid_from": "2026-01-01",
        "source": ILLUSTRATIVE_SOURCE,
        "municipal_tax_percent": 5.0,
        "tiers": _tiers([
            (0.0, 50000.0, 510.00, 103.30),
            (50000.01, 150000.0, 960.00, 194.40),
            (150000.01, 300000.0, 1420.00, 287.60),
            (300000.01, 500000.0, 1920.00, 434.80),
            (500000.01, 1000000.0, 2860.00, 579.20),
            (1000000.01, None, 3950.00, 799.90),
        ]),
        "fixed_services": {},
    },
    {
        "_id": "fee_atos_fixos_sp_2026",
        "state": "SP",
        "service_type": "atos_valor_fixo",
        "label": "Atos de valor fixo",
        "valid_from": "2026-01-01",
        "source": ILLUSTRATIVE_SOURCE,
        "municipal_tax_percent": 5.0,
        "tiers": [],
        "fixed_services": {
            "certidao_breve_relato": {"label": "Certidão de breve relato", "notary_fee": 45.20, "state_fund": 9.15},
            "certidao_inteiro_teor": {"label": "Certidão de inteiro teor", "notary_fee": 78.40, "state_fund": 15.90},
            "procuracao_imovel": {"label": "Procuração pública de imóvel", "notary_fee": 120.00,
                                  "state_fund": 24.30},
            "habilitacao_casamento": {"label": "Habilitação de casamento", "notary_fee": 180.00,
                                      "state_fund": 36.45},
        },
    },
]
