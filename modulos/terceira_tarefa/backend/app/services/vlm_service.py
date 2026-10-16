"""Transcrição paleográfica + extração de entidades via Claude (multimodal)."""
import base64
import logging

import anthropic

from app.core.config import get_settings
from app.schemas.transcription_schema import HistoricalTranscriptionResult

logger = logging.getLogger(__name__)

BOOK_TYPE_CONTEXT = {
    "transcricao_imobiliaria": (
        "Livro 3 de Transcrição das Transmissões do Registro de Imóveis. Partes típicas: transmitente "
        "(alienante) e adquirente; registre também o título (escritura, formal de partilha), o valor e o "
        "tabelião quando houver. Em `confrontants_or_parents` liste os confrontantes do imóvel."
    ),
    "nascimento": (
        "Livro A de Registro Civil de Nascimento. Partes típicas: registrado, pai, mãe, declarante, "
        "testemunhas. Em `confrontants_or_parents` liste a filiação e os avós paternos e maternos."
    ),
    "casamento": (
        "Livro B de Registro Civil de Casamento. Partes típicas: nubentes (contraente varão e virago), "
        "testemunhas, celebrante. Em `confrontants_or_parents` liste os pais de cada nubente."
    ),
    "obito": (
        "Livro C de Registro Civil de Óbito. Partes típicas: falecido, declarante, médico atestante, "
        "cônjuge. Em `confrontants_or_parents` liste a filiação do falecido."
    ),
}

SYSTEM_PROMPT = """Você é um paleógrafo especialista em documentação cartorária luso-brasileira dos séculos XIX e XX \
(Registro de Imóveis e Registro Civil). Você lê caligrafia cursiva oitocentista, tinta ferrogálica desbotada, \
papel amarelado e páginas datilografadas, e conhece as abreviaturas e arcaísmos da época.

Sua tarefa é produzir, para o assento da imagem, duas camadas ao mesmo tempo:

1. `transcription_raw` — transcrição LITERAL e diplomática:
   - Preserve a grafia original: "mez", "escriptura", "freguezia", "baptizado", "pharmacia", "d'Oliveira", "Snr.", "D.ª", "Ill.mo".
   - Não modernize, não corrija concordância, não expanda abreviaturas nesta camada.
   - Preserve números como escritos (por extenso ou em algarismos).
   - Marque cada trecho que você não consegue decifrar com segurança como [ilegível]. Nunca invente texto
     para preencher lacunas; um [ilegível] é muito mais útil ao escrevente do que um palpite.
   - Se a página tiver mais de um assento ou colunas duplas, transcreva o assento principal (o mais completo)
     e siga a ordem natural de leitura de cada coluna. Separe parágrafos com quebra de linha.
   - Anotações marginais (averbações) vão ao final, precedidas de "[Margem]".

2. Entidades normalizadas:
   - `name_standardized`: nome completo em CAIXA ALTA com grafia contemporânea e abreviaturas expandidas
     ("M.el" → "MANOEL", "Joaq.m" → "JOAQUIM", "d'Oliveira" → "DE OLIVEIRA"). Nunca abrevie nesta camada.
     Mantenha a forma do nome como o documento a usa (Manoel continua MANOEL; não troque por MANUEL).
   - `name_original`: o nome exatamente como escrito no manuscrito, inclusive formas abreviadas.
   - `entry_date_iso`: converta a data por extenso ("aos dezoito dias do mez de maio de mil novecentos e
     quarenta e dois") para YYYY-MM-DD. Use null se o ano não puder ser determinado.
   - `entry_number`: o número do assento/transcrição/ordem como aparece (ex.: "18.490", "N.º 312").

`confidence_score`: sua confiança global na leitura, de 0.0 a 1.0. Seja calibrado: abaixo de 0.6 se houver
vários [ilegível] ou nomes incertos; acima de 0.9 apenas para textos nítidos, datilografados ou de leitura inequívoca.
O operador humano revisará trechos com baixa confiança."""


class VLMError(RuntimeError):
    pass


_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key, max_retries=3)
    return _client


async def transcribe_page(
    image_jpeg: bytes,
    book_type: str,
    book_number: str,
    page_number: int,
) -> HistoricalTranscriptionResult:
    settings = get_settings()
    image_b64 = base64.standard_b64encode(image_jpeg).decode("ascii")
    user_text = (
        f"Contexto do acervo: {BOOK_TYPE_CONTEXT.get(book_type, book_type)}\n"
        f"Livro {book_number}, folha {page_number}.\n\n"
        "A imagem já foi convertida para tons de cinza com realce de contraste (CLAHE). "
        "Transcreva o assento e extraia as entidades no formato solicitado."
    )

    try:
        response = await get_client().messages.parse(
            model=settings.vlm_model,
            max_tokens=settings.vlm_max_tokens,
            system=SYSTEM_PROMPT,
            output_config={"effort": settings.vlm_effort},
            output_format=HistoricalTranscriptionResult,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": user_text},
                ],
            }],
        )
    except TypeError as exc:
        # O SDK levanta TypeError quando nenhuma credencial foi encontrada no ambiente.
        if "authentication" not in str(exc):
            raise
        raise VLMError("Credencial da API Anthropic não configurada (defina ANTHROPIC_API_KEY no backend/.env).") from exc
    except anthropic.AuthenticationError as exc:
        raise VLMError("Credencial da API Anthropic inválida ou ausente (ANTHROPIC_API_KEY).") from exc
    except anthropic.BadRequestError as exc:
        raise VLMError(f"Requisição rejeitada pelo VLM: {exc.message}") from exc
    except anthropic.RateLimitError as exc:
        raise VLMError("Limite de requisições do VLM atingido; tente novamente em instantes.") from exc
    except anthropic.APIStatusError as exc:
        raise VLMError(f"Erro do serviço VLM ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        raise VLMError("Não foi possível conectar ao serviço VLM.") from exc

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise VLMError(f"O modelo recusou a transcrição (categoria: {category}).")
    if response.stop_reason == "max_tokens":
        raise VLMError("A transcrição excedeu o limite de tokens; divida a página ou aumente VLM_MAX_TOKENS.")
    if response.parsed_output is None:
        raise VLMError("O modelo não retornou a estrutura esperada.")

    logger.info(
        "VLM %s: livro %s fl. %s, %s in / %s out tokens",
        settings.vlm_model, book_number, page_number,
        response.usage.input_tokens, response.usage.output_tokens,
    )
    result = response.parsed_output
    result.confidence_score = min(1.0, max(0.0, result.confidence_score))
    return result
