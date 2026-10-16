"""Catálogo de categorias de dado sensível e respectiva fundamentação.

Os textos de fundamentação são editáveis e devem ser validados pelo jurídico /
oficial da serventia antes do uso em produção. O Provimento CNJ 134/2022 foi
consolidado no Código Nacional de Normas do Foro Extrajudicial (Provimento CNJ
149/2023); ajuste as remissões conforme a norma vigente adotada pela serventia.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryPolicy:
    label: str
    legal_basis: str
    # Sugestões da IA nascem aprovadas por padrão? O operador sempre pode alternar.
    approved_by_default: bool


CATEGORY_POLICIES: dict[str, CategoryPolicy] = {
    "DADO_MEDICO": CategoryPolicy(
        label="Dado de saúde",
        legal_basis="LGPD arts. 5º, II e 11 (dado pessoal sensível referente à saúde); Provimento CNJ 134/2022",
        approved_by_default=True,
    ),
    "DADO_BANCARIO": CategoryPolicy(
        label="Dado bancário",
        legal_basis="LGPD art. 6º, III (necessidade); LC 105/2001 (sigilo bancário); Provimento CNJ 134/2022",
        approved_by_default=True,
    ),
    "DADO_FINANCEIRO": CategoryPolicy(
        label="Dado financeiro",
        legal_basis="LGPD art. 6º, III (necessidade): informação patrimonial desnecessária ao teor da certidão",
        approved_by_default=True,
    ),
    "FILIACAO_PROTEGIDA": CategoryPolicy(
        label="Filiação sob sigilo",
        legal_basis="ECA art. 47, §§ 3º e 4º (sigilo da origem na adoção); Lei 6.015/73; Provimento CNJ 134/2022",
        approved_by_default=True,
    ),
    "DOCUMENTO_PESSOAL": CategoryPolicy(
        label="Documento pessoal",
        legal_basis="LGPD art. 6º, III (necessidade): avaliar se o identificador integra o teor obrigatório do ato",
        # CPF/RG das partes frequentemente integram o teor do ato: decisão do operador.
        approved_by_default=False,
    ),
}

MANUAL_LEGAL_BASIS = "Tarja manual do operador (LGPD art. 6º, III – necessidade)"


def policy_for(category: str) -> CategoryPolicy:
    return CATEGORY_POLICIES[category]
