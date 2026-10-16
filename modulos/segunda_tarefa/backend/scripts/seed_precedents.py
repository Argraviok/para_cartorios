"""Popula `legal_precedents` com uma ficha por vício comum em compra e venda. Idempotente.

ATENÇÃO: as fichas citam apenas dispositivos de lei federal e NÃO contêm jurisprudência.
Todas são gravadas com verified=false e exigem revisão jurídica antes do uso em produção.

Uso:
    python -m scripts.seed_precedents                    # gera embeddings (exige chave de API)
    python -m scripts.seed_precedents --skip-embeddings  # só busca textual funcionará
"""

import argparse
import asyncio

from app.core.config import get_settings
from app.core.database import create_client, get_database
from app.repositories.precedents import MongoPrecedentRepository, PrecedentRepository
from app.schemas.enums import VicioCode
from app.schemas.precedent_schema import NormativeRef, PrecedentBase
from app.services.embedding_service import Embedder, build_embedder

LRP = "Lei 6.015/1973"
CC = "Código Civil (Lei 10.406/2002)"

SEED: dict[str, PrecedentBase] = {
    "prec_quebra_continuidade_01": PrecedentBase(
        vicio_code=VicioCode.QUEBRA_CONTINUIDADE,
        title="Quebra do princípio da continuidade registral",
        normative_refs=[NormativeRef(diploma=LRP, artigo="195"), NormativeRef(diploma=LRP, artigo="237")],
        recommended_text=(
            "Verifica-se que o transmitente indicado no título não corresponde ao titular de domínio constante da "
            "matrícula, ou que sua qualificação diverge da registrada, o que impede o encadeamento ininterrupto das "
            "titularidades. Em observância ao princípio da continuidade, é necessário o prévio registro do título "
            "anterior ou a prévia averbação da alteração correspondente."
        ),
        suggested_solution=(
            "Apresentar o título aquisitivo anterior para prévio registro, ou o documento hábil à averbação da "
            "alteração da qualificação do titular, de modo a compatibilizar a matrícula com o título apresentado."
        ),
    ),
    "prec_itbi_nao_recolhido_01": PrecedentBase(
        vicio_code=VicioCode.ITBI_NAO_RECOLHIDO,
        title="Ausência de comprovação do recolhimento do ITBI",
        normative_refs=[
            NormativeRef(diploma=LRP, artigo="289"),
            NormativeRef(diploma="Constituição Federal", artigo="156, II"),
        ],
        recommended_text=(
            "Constata-se que não foi apresentada a guia de recolhimento do Imposto sobre a Transmissão de Bens Imóveis "
            "(ITBI) relativa à transmissão objeto do título, ou que a guia apresentada não corresponde ao imóvel, às "
            "partes ou ao valor da operação. Cumpre ao registrador fiscalizar o pagamento dos impostos devidos em razão "
            "dos atos que lhe são apresentados."
        ),
        suggested_solution=(
            "Apresentar a guia de ITBI emitida pelo Município de situação do imóvel, com o respectivo comprovante de "
            "pagamento, correspondente às partes, ao imóvel e ao valor da transmissão constantes do título."
        ),
    ),
    "prec_procuracao_sem_censec_01": PrecedentBase(
        vicio_code=VicioCode.PROCURACAO_SEM_CENSEC,
        title="Procuração pública sem certidão atualizada que ateste sua vigência",
        normative_refs=[
            NormativeRef(diploma=CC, artigo="682"),
            NormativeRef(diploma="Provimento CNJ nº 149/2023 (Código Nacional de Normas – Foro Extrajudicial)"),
        ],
        recommended_text=(
            "Verifica-se que o título foi outorgado por procurador, sem a apresentação de certidão atualizada da "
            "procuração que comprove a inexistência de revogação, renúncia ou outra causa de extinção do mandato. A "
            "verificação deve ser feita por certidão da serventia de origem ou por consulta à Central Notarial de "
            "Serviços Eletrônicos Compartilhados (CENSEC), no prazo de validade fixado pelas normas da Corregedoria local."
        ),
        suggested_solution=(
            "Apresentar certidão atualizada da procuração, expedida pelo tabelionato que a lavrou, acompanhada de "
            "consulta à CENSEC que ateste a inexistência de revogação, dentro do prazo de validade aplicável."
        ),
    ),
    "prec_outorga_conjugal_01": PrecedentBase(
        vicio_code=VicioCode.OUTORGA_CONJUGAL,
        title="Alienação de imóvel sem outorga do cônjuge",
        normative_refs=[NormativeRef(diploma=CC, artigo="1.647, I"), NormativeRef(diploma=CC, artigo="1.649")],
        recommended_text=(
            "Constata-se que o alienante é casado sob regime de bens que exige a autorização do cônjuge para a alienação "
            "de bens imóveis, não constando do título a anuência deste. Ressalvado o regime da separação absoluta, "
            "nenhum dos cônjuges pode alienar imóvel sem autorização do outro, sob pena de anulabilidade do ato."
        ),
        suggested_solution=(
            "Apresentar escritura de re-ratificação com o comparecimento e a anuência do cônjuge, ou instrumento público "
            "de outorga específica, ou suprimento judicial da outorga."
        ),
    ),
    "prec_descricao_tabular_divergente_01": PrecedentBase(
        vicio_code=VicioCode.DESCRICAO_TABULAR_DIVERGENTE,
        title="Descrição do imóvel no título divergente da constante da matrícula",
        normative_refs=[
            NormativeRef(diploma=LRP, artigo="176, § 1º, II, 3"),
            NormativeRef(diploma=LRP, artigo="225, § 2º"),
            NormativeRef(diploma=LRP, artigo="213"),
        ],
        recommended_text=(
            "Verifica-se que a caracterização do imóvel no título (medidas, confrontações, área ou localização) não "
            "coincide com a constante da matrícula. Em observância ao princípio da especialidade objetiva, consideram-se "
            "irregulares os títulos cuja caracterização do imóvel não coincida com a do registro anterior."
        ),
        suggested_solution=(
            "Apresentar escritura de re-ratificação que reproduza fielmente a descrição constante da matrícula, ou "
            "promover previamente a retificação do registro pelo procedimento cabível."
        ),
    ),
    "prec_debito_condominial_01": PrecedentBase(
        vicio_code=VicioCode.DEBITO_CONDOMINIAL,
        title="Ausência de prova de quitação das obrigações condominiais",
        normative_refs=[
            NormativeRef(diploma="Lei 4.591/1964", artigo="4º, parágrafo único"),
            NormativeRef(diploma=CC, artigo="1.345"),
        ],
        recommended_text=(
            "Constata-se que o título tem por objeto unidade autônoma em condomínio edilício e não foi apresentada prova "
            "de quitação das obrigações do alienante para com o condomínio, nem declaração expressa do adquirente "
            "assumindo eventuais débitos, nos termos admitidos pelas normas da Corregedoria local."
        ),
        suggested_solution=(
            "Apresentar declaração de quitação condominial firmada pelo síndico ou administradora, com prova da "
            "representação, ou a declaração do adquirente admitida pelas normas locais."
        ),
    ),
    "prec_cnd_municipal_ausente_01": PrecedentBase(
        vicio_code=VicioCode.CND_MUNICIPAL_AUSENTE,
        title="Ausência de certidão negativa de débitos municipais do imóvel",
        normative_refs=[
            NormativeRef(diploma="Lei 7.433/1985"),
            NormativeRef(diploma="Código Tributário Nacional (Lei 5.172/1966)", artigo="130"),
        ],
        recommended_text=(
            "Verifica-se que não foi apresentada certidão de débitos municipais relativa ao imóvel, nem consta do título "
            "sua apresentação ou a dispensa expressa pelo adquirente, nas hipóteses em que as normas locais a admitem. "
            "Os créditos tributários relativos ao imóvel sub-rogam-se na pessoa do adquirente, salvo quando conste do "
            "título a prova de sua quitação."
        ),
        suggested_solution=(
            "Apresentar certidão negativa (ou positiva com efeitos de negativa) de débitos imobiliários expedida pelo "
            "Município, dentro do prazo de validade, ou declaração de dispensa do adquirente quando admitida."
        ),
    ),
    "prec_averbacao_casamento_pendente_01": PrecedentBase(
        vicio_code=VicioCode.AVERBACAO_CASAMENTO_PENDENTE,
        title="Necessidade de prévia averbação de casamento do titular",
        normative_refs=[NormativeRef(diploma=LRP, artigo="167, II, 5"), NormativeRef(diploma=LRP, artigo="246")],
        recommended_text=(
            "Constata-se que o titular de domínio figura na matrícula com estado civil diverso do declarado no título, "
            "sendo necessária a prévia averbação do casamento, com indicação do regime de bens e de eventual alteração "
            "de nome, para que se preserve a continuidade e a especialidade subjetiva do registro."
        ),
        suggested_solution=(
            "Apresentar certidão de casamento atualizada e, se o regime não for o legal, a certidão do registro do pacto "
            "antenupcial, para prévia averbação na matrícula."
        ),
    ),
}


async def seed(repo: PrecedentRepository, embedder: Embedder | None) -> None:
    for prec_id, data in SEED.items():
        embedding = await embedder.embed(data.build_embedding_text(), task="document") if embedder else None
        await repo.upsert(prec_id, data, embedding, embedder.model if embedder else None)
        print(f"  ✓ {prec_id}")


async def main(skip_embeddings: bool) -> None:
    settings = get_settings()
    embedder = None if skip_embeddings else build_embedder(settings)
    client = create_client(settings)
    try:
        await seed(MongoPrecedentRepository(get_database(client, settings)), embedder)
    finally:
        await client.close()
    print(f"\n{len(SEED)} fichas criadas com verified=false — revisão jurídica obrigatória antes do uso em produção.")
    if skip_embeddings:
        print("Embeddings não gerados: apenas a busca textual funcionará até rodar scripts.reindex_embeddings.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-embeddings", action="store_true")
    asyncio.run(main(parser.parse_args().skip_embeddings))
