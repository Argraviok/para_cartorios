"""Gera PDFs de exemplo com dados 100% fictícios para testes e demonstração.

Uso: python test_samples/generate_samples.py
"""

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pymupdf

HERE = Path(__file__).parent

PAGE_1 = """REPÚBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE INTERDIÇÃO - INTEIRO TEOR

Certifico que, revendo o Livro E-12, folha 88, sob o número de ordem 1.921,
consta o registro da sentença de interdição de FULANO DE TAL FICTÍCIO,
CPF 529.982.247-25, nascido em 03/04/1971, proferida nos autos 88192.
Curador nomeado: BELTRANO EXEMPLO DA SILVA, CPF 111.444.777-35.
"""

PAGE_2 = """Do laudo pericial juntado aos autos consta que o interditando é
portador de esquizofrenia paranoide (CID F20.0), com histórico de
internação psiquiátrica em 2019. O perito concluiu pela incapacidade
relativa para os atos da vida civil de natureza patrimonial.
"""

PAGE_3 = """Para fins de prestação de contas, o curador informou os seguintes bens:
pensão por invalidez creditada no Banco Santander Ag. 0918 C/C 0109283-4,
com saldo de R$ 48.320,15 em 31/12/2025. Chave PIX: fulano.ficticio@example.com.
Cartão vinculado nº 4111 1111 1111 1111.

Registra-se, ainda, que o interditando foi adotado, constando como mãe biológica
CICRANA DE EXEMPLO, conforme averbação anterior.

O referido é verdade e dou fé. Município Exemplo, 14 de outubro de 2026.
"""


def _write_page(doc: pymupdf.Document, text: str) -> pymupdf.Page:
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(60, 60, 540, 800), text, fontname="helv", fontsize=11, lineheight=1.5)
    return page


def build_certidao(path: Path) -> None:
    doc = pymupdf.open()
    for text in (PAGE_1, PAGE_2, PAGE_3):
        _write_page(doc, text)
    # Nota adesiva sobre o diagnóstico: o sanitizador deve removê-la junto.
    page2 = doc[1]
    hit = page2.search_for("esquizofrenia")[0]
    page2.add_text_annot(hit.tl, "Diagnóstico: esquizofrenia paranoide")
    doc.set_metadata({"author": "Escrevente Exemplo", "title": "Interdição Fulano de Tal Fictício"})
    doc.save(path, garbage=3, deflate=True)
    doc.close()


def build_scanned(path: Path) -> None:
    """Página digitalizada: só imagem, sem camada de texto."""
    src = pymupdf.open()
    _write_page(src, PAGE_3)
    pix = src[0].get_pixmap(dpi=150)
    src.close()
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(path, deflate=True)
    doc.close()


_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def build_docx(path: Path) -> None:
    """Mesma certidão em Word (.docx mínimo, sem dependências), uma página por bloco."""
    paragraphs = []
    for n, text in enumerate((PAGE_1, PAGE_2, PAGE_3)):
        if n:
            paragraphs.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        for line in text.strip().split("\n"):
            paragraphs.append(f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(paragraphs)
        + "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/document.xml", document)


if __name__ == "__main__":
    build_certidao(HERE / "certidao_interdicao_ficticia.pdf")
    build_scanned(HERE / "certidao_digitalizada_ficticia.pdf")
    build_docx(HERE / "certidao_interdicao_ficticia.docx")
    print("Amostras geradas em", HERE)
