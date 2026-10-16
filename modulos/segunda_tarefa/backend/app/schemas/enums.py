from enum import Enum


class VicioCode(str, Enum):
    QUEBRA_CONTINUIDADE = "quebra_continuidade"
    ITBI_NAO_RECOLHIDO = "itbi_nao_recolhido"
    PROCURACAO_SEM_CENSEC = "procuracao_sem_censec"
    OUTORGA_CONJUGAL = "outorga_conjugal"
    DESCRICAO_TABULAR_DIVERGENTE = "descricao_tabular_divergente"
    DEBITO_CONDOMINIAL = "debito_condominial"
    CND_MUNICIPAL_AUSENTE = "cnd_municipal_ausente"
    AVERBACAO_CASAMENTO_PENDENTE = "averbacao_casamento_pendente"
    OUTRO = "outro"


VICIO_LABELS: dict[VicioCode, str] = {
    VicioCode.QUEBRA_CONTINUIDADE: "Quebra do Princípio da Continuidade",
    VicioCode.ITBI_NAO_RECOLHIDO: "Ausência de comprovação do recolhimento do ITBI",
    VicioCode.PROCURACAO_SEM_CENSEC: "Procuração sem certidão atualizada / CENSEC",
    VicioCode.OUTORGA_CONJUGAL: "Ausência de outorga conjugal",
    VicioCode.DESCRICAO_TABULAR_DIVERGENTE: "Descrição do imóvel divergente da matrícula",
    VicioCode.DEBITO_CONDOMINIAL: "Ausência de prova de quitação condominial",
    VicioCode.CND_MUNICIPAL_AUSENTE: "Ausência de CND Municipal",
    VicioCode.AVERBACAO_CASAMENTO_PENDENTE: "Averbação de casamento pendente",
    VicioCode.OUTRO: "Outro",
}
