"""Regras determinísticas para padrões fixos de dados sensíveis em documentos brasileiros.

Cada regra pode definir um grupo nomeado `pii`: quando presente, apenas esse
grupo é tarjado (ex.: o valor em "saldo de R$ 10.000,00", não a palavra "saldo").
"""

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RegexRule:
    category: str
    pii_type: str
    pattern: re.Pattern[str]
    validator: Callable[[str], bool] | None = None


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def is_valid_cpf(raw: str) -> bool:
    d = _digits(raw)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        total = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (total * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def passes_luhn(raw: str) -> bool:
    d = _digits(raw)
    if not 13 <= len(d) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(d)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


# Trecho até o fim da frase (atravessa quebras de linha), permitindo pontos decimais (ex.: "CID F20.0").
_UNTIL_STOP = r"(?:[^.;]|\.(?=\d))"

_BANK_NAME = r"(?:Banco|Bco\.?)\s+(?:(?:do|da|de)\s+)?[A-ZÀ-Ý][\wÀ-ÿ&]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ&]*){0,3}"
_AGENCIA = r"(?i:ag(?:[êe]ncia|\.)?)\s*(?i:n[º°o]\.?\s*)?:?\s*\d{3,5}(?:-[\dXx])?"
_CONTA = (
    r"(?i:c/c|c/p|conta(?:\s+(?:corrente|poupan[çc]a|sal[áa]rio|de\s+pagamento))?)"
    r"\s*(?i:n[º°o]\.?\s*)?:?\s*\d[\d.]{2,13}-?[\dXx]"
)

_MEDICAL_LEADIN = (
    r"(?i:portador[a]?\s+d[eoa]s?|diagnosticad[oa]\s+com|acometid[oa]\s+(?:de|por)|sofre\s+de"
    r"|diagn[óo]stico\s+de|quadro\s+(?:cl[íi]nico\s+)?de|em\s+tratamento\s+(?:para|de))"
)
_MEDICAL_TERMS = (
    r"(?i:esquizofrenia|transtorno\s+(?:bipolar|mental|psic[óo]tico|depressivo|de\s+personalidade|do\s+espectro\s+autista)"
    r"|dem[êe]ncia|alzheimer|parkinson|defici[êe]ncia\s+(?:intelectual|mental)|retardo\s+mental"
    r"|autismo|psicose|depress[ãa]o|depend[êe]ncia\s+qu[íi]mica|alcoolismo|hiv|aids|neoplasia|c[âa]ncer"
    r"|epilepsia|interna[çc][ãa]o\s+psiqui[áa]trica)"
)
_ADOPTION_TERMS = (
    r"(?i:ado[çc][ãa]o|adotad[oa]|adotante|pai\s+biol[óo]gico|m[ãa]e\s+biol[óo]gica|genitor[a]?\s+biol[óo]gic[oa]"
    r"|filia[çc][ãa]o\s+(?:anterior|original|biol[óo]gica)|destitui[çc][ãa]o\s+do\s+poder\s+familiar"
    r"|investiga[çc][ãa]o\s+de\s+paternidade)"
)
_FINANCIAL_LEADIN = (
    r"(?i:saldo|aplica[çc](?:[ãa]o|[õo]es)|investimentos?|rendimentos?|sal[áa]rio|renda(?:\s+mensal)?"
    r"|remunera[çc][ãa]o|d[íi]vidas?|patrim[ôo]nio|pens[ãa]o(?:\s+aliment[íi]cia)?|proventos|benef[íi]cio)"
)
_BRL = r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?"

RULES: list[RegexRule] = [
    # --- Bancário ---------------------------------------------------------
    RegexRule(
        "DADO_BANCARIO",
        "CONTA_BANCARIA",
        re.compile(rf"(?:{_BANK_NAME}[\s,–-]*)?{_AGENCIA}(?:[\s,/–-]*(?:e\s+)?{_CONTA})?"),
    ),
    RegexRule("DADO_BANCARIO", "CONTA_BANCARIA", re.compile(_CONTA)),
    RegexRule("DADO_BANCARIO", "CHAVE_PIX", re.compile(r"(?i:chave\s+pix)\s*[:\-–]?\s*(?P<pii>[^\s,;]+?)(?=[.,;]?(?:\s|$))")),
    RegexRule(
        "DADO_BANCARIO",
        "CARTAO_CREDITO",
        re.compile(r"(?<!\d)(?<!\d[ .-])(?:\d{4}[ -]?){3}\d{1,7}(?![ -]?\d)"),
        passes_luhn,
    ),
    # --- Financeiro -------------------------------------------------------
    RegexRule(
        "DADO_FINANCEIRO",
        "VALOR_PATRIMONIAL",
        re.compile(rf"{_FINANCIAL_LEADIN}[^.;\n]{{0,60}}?(?P<pii>{_BRL})"),
    ),
    # --- Saúde ------------------------------------------------------------
    RegexRule(
        "DADO_MEDICO",
        "CID_DIAGNOSTICO",
        re.compile(r"\(?(?i:CID(?:[- ]?1[01])?)\s*[:\-–]?\s*[A-Z]\d{2}(?:\.\d{1,2})?\)?"),
    ),
    RegexRule("DADO_MEDICO", "CONDICAO_SAUDE", re.compile(rf"{_MEDICAL_LEADIN}\s+{_UNTIL_STOP}{{3,160}}")),
    RegexRule("DADO_MEDICO", "CONDICAO_SAUDE", re.compile(rf"\b{_MEDICAL_TERMS}\b")),
    # --- Filiação sob sigilo (frase inteira em que o termo aparece) ------
    RegexRule(
        "FILIACAO_PROTEGIDA",
        "ORIGEM_FILIACAO",
        re.compile(rf"[^.;]{{0,200}}?\b{_ADOPTION_TERMS}\b[^.;]{{0,200}}"),
    ),
    # --- Documentos pessoais (aprovação a critério do operador) ----------
    RegexRule(
        "DOCUMENTO_PESSOAL",
        "CPF",
        re.compile(r"(?<![\d.])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d-])"),
        is_valid_cpf,
    ),
]


@dataclass(frozen=True)
class RegexMatch:
    start: int
    end: int
    category: str
    pii_type: str


def find_matches(text: str) -> list[RegexMatch]:
    matches: list[RegexMatch] = []
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            group = "pii" if "pii" in rule.pattern.groupindex else 0
            start, end = m.span(group)
            value = text[start:end]
            if rule.validator and not rule.validator(value):
                continue
            # Ignora espaços/quebras nas pontas do trecho.
            stripped = value.strip()
            if not stripped:
                continue
            start += len(value) - len(value.lstrip())
            matches.append(RegexMatch(start, start + len(stripped), rule.category, rule.pii_type))
    return matches
