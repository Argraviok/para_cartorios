"""Gera PDFs fictícios de matrícula, memorial e contrato para testes e demonstração.

Uso: python test_samples/generate_samples.py
Todos os nomes, números e documentos são fictícios.
"""

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import docx
import pymupdf

OUT = Path(__file__).parent


def write_pdf(name: str, text: str) -> None:
    doc = pymupdf.open()
    lines = text.strip("\n").splitlines()
    per_page = 60
    for i in range(0, max(len(lines), 1), per_page):
        page = doc.new_page(width=595, height=842)
        page.insert_textbox(
            pymupdf.Rect(40, 40, 555, 802), "\n".join(lines[i : i + per_page]), fontsize=8.5, fontname="helv"
        )
    doc.save(OUT / name)


def write_docx(name: str, text: str, table: list[list[str]] | None = None) -> None:
    doc = docx.Document()
    for line in text.strip("\n").splitlines():
        doc.add_paragraph(line)
    if table:
        t = doc.add_table(rows=0, cols=len(table[0]))
        t.style = "Table Grid"
        for row in table:
            cells = t.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = value
    doc.save(OUT / name)


def docx_to_doc(name: str) -> None:
    """Gera a versão Word 97-2003 (.doc) via LibreOffice, se instalado."""
    soffice = shutil.which("soffice")
    if not soffice:
        print("LibreOffice ausente: .doc de exemplo não gerado")
        return
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [soffice, f"-env:UserInstallation=file://{tmp}/p", "--headless", "--convert-to", "doc",
             "--outdir", str(OUT), str(OUT / name)],
            check=True, capture_output=True, timeout=120,
        )
        (OUT / name).unlink()


def br(n: float, decimals: int = 3) -> str:
    s = f"{n:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def dms(az: float) -> str:
    d = int(az)
    m_full = (az - d) * 60
    m = int(m_full)
    s = (m_full - m) * 60
    return f"{d}°{m:02d}'{s:05.2f}\"".replace(".", ",")


MATRICULA = """
1º OFICIAL DE REGISTRO DE IMÓVEIS DE CAMPINAS/SP
LIVRO Nº 2 - REGISTRO GERAL
MATRÍCULA Nº 89.214            FICHA 01            Data: 12/03/1998

IMÓVEL: Lote 13 da Quadra F do loteamento "Jardim das Acácias", com frente para a Rua das Acácias,
com área total de 1.500,00 m², confrontando pela frente com a Rua das Acácias, pelo lado direito com o
Espólio de Benedito Souza, pelo lado esquerdo com Área Pública Municipal e pelos fundos com o Lote 14.
PROPRIETÁRIO: ANTONIO CARLOS SOUZA. REGISTRO ANTERIOR: Transcrição nº 45.112 deste Registro.

R-1 - 12/03/1998 - COMPRA E VENDA
Por escritura de 02/03/1998 do 3º Tabelião de Notas de Campinas.
TRANSMITENTE: ANTONIO CARLOS SOUZA, brasileiro, casado.
ADQUIRENTE: JOSÉ ANTONIO PEREIRA, brasileiro, casado.
Valor: R$ 85.000,00.

R-2 - 20/08/2005 - HIPOTECA
DEVEDOR: JOSÉ ANTONIO PEREIRA.
CREDOR: Banco do Brasil S.A.
Cédula de crédito bancário nº 2005/8812, valor R$ 120.000,00.

AV-3 - 15/09/2010 - CANCELAMENTO
Fica cancelada a hipoteca objeto do R-2, por autorização do credor.

R-4 - 10/05/2016 - PARTILHA
Formal de partilha extraído dos autos de inventário nº 1002233-11.2015.8.26.0114.
AUTOR DA HERANÇA: ESPÓLIO DE JOSÉ ANTONIO PEREIRA.
HERDEIRO: CARLOS EDUARDO PEREIRA, brasileiro, solteiro.

AV-5 - 22/02/2024 - PENHORA
Penhora determinada pela 2ª Vara Cível da Comarca de Campinas, processo nº 1015566-77.2023.8.26.0114.
EXECUTADO: CARLOS EDUARDO PEREIRA.
EXEQUENTE: Construtora Horizonte Ltda.
"""

MATRICULA_GEORREF = """
2º OFICIAL DE REGISTRO DE IMÓVEIS DE CAMPINAS/SP
MATRÍCULA Nº 77.001            FICHA 01            Data: 05/06/2019

IMÓVEL: Gleba urbana com frente para a Rua das Acácias, com área total de 1.500,00 m², com o seguinte
perímetro georreferenciado (UTM, Datum SIRGAS 2000, Fuso 23):
{VERTICES}
PROPRIETÁRIA: HELENA DUARTE. REGISTRO ANTERIOR: Matrícula nº 70.500 deste Registro.

R-1 - 05/06/2019 - COMPRA E VENDA
TRANSMITENTE: HELENA DUARTE.
ADQUIRENTE: PAULO HENRIQUE LIMA.
"""

CONTRATO = """
INSTRUMENTO PARTICULAR DE COMPROMISSO DE COMPRA E VENDA

VENDEDOR: MARCOS VINICIUS PEREIRA, brasileiro, solteiro, CPF 000.000.000-00.
COMPRADOR: ANA LUIZA FERRAZ, brasileira, casada, CPF 111.111.111-11.

OBJETO: Lote 13 da Quadra F, Jardim das Acácias, Campinas/SP, matrícula nº 89.214 do
1º Oficial de Registro de Imóveis de Campinas/SP.
PREÇO: R$ 450.000,00.
"""


def memorial_utm(as_table: bool = False):
    # Poligonal irregular de ~1.500 m² a partir de V-01 (Campinas, fuso 23S)
    start = (288627.507, 7465450.274)
    legs = [  # (azimute, distância, confrontante, direção)
        (72.258333, 30.40, "Rua das Acácias", "Norte"),
        (162.0, 49.80, "Espólio de Benedito Souza, matrícula nº 41.877", "Leste"),
        (252.5, 30.10, "Lote 14 de propriedade de João Silveira, matrícula nº 52.310", "Sul"),
        (None, None, "Área Pública Municipal", "Oeste"),
    ]
    pts = [start]
    x, y = start
    for az, d, *_ in legs[:-1]:
        x += d * math.sin(math.radians(az))
        y += d * math.cos(math.radians(az))
        pts.append((x, y))
    # último lado: volta para V-01 com 1,8 cm de erro de fechamento
    dx, dy = start[0] - x, start[1] - y
    last_d = math.hypot(dx, dy) + 0.018
    last_az = math.degrees(math.atan2(dx, dy)) % 360
    legs[-1] = (last_az, last_d, legs[-1][2], legs[-1][3])

    if as_table:
        header = "MEMORIAL DESCRITIVO\nImóvel: Lote 13 da Quadra F - Jardim das Acácias - Campinas/SP - Matrícula 89.214\n" \
            "Sistema de coordenadas: UTM, Datum SIRGAS 2000, Fuso 23 Sul.\nÁrea total de 1.500,00 m², perímetro de 160,40 m."
        rows = [["Vértice", "Coordenada E (m)", "Coordenada N (m)", "Azimute", "Distância (m)", "Confrontante"]]
        for i, ((az, d, conf, _), (e, n)) in enumerate(zip(legs, pts)):
            rows.append([f"V-{i + 1:02d}", br(e), br(n), dms(az), br(d, 2), conf])
        return header, rows

    lines = [
        "MEMORIAL DESCRITIVO",
        "Imóvel: Lote 13 da Quadra F - Jardim das Acácias - Campinas/SP - Matrícula 89.214",
        "Sistema de coordenadas: UTM, Datum SIRGAS 2000, Fuso 23 Sul.",
        "",
        "Inicia-se a descrição deste perímetro no vértice V-01, conforme segue:",
    ]
    for i, ((az, d, conf, direction), (e, n)) in enumerate(zip(legs, pts)):
        nxt = f"V-{(i + 1) % 4 + 1:02d}"
        lines.append(
            f"V-{i + 1:02d} E={br(e)} N={br(n)} Az={dms(az)} D={br(d, 2)}m até {nxt}, "
            f"lado {direction}, confrontante: {conf}"
        )
    lines += ["", "Área total de 1.500,00 m², perímetro de 160,40 m.", "Responsável técnico: Eng. Agrimensor (CREA fictício)."]
    return "\n".join(lines)


MEMORIAL_NAO_FECHA = """
MEMORIAL DESCRITIVO - LEVANTAMENTO POR AZIMUTES E DISTÂNCIAS
Imóvel: Gleba B - Sítio Boa Vista - Matrícula 12.345

V-01 Az=90°00'00" D=40,00m confrontante: Estrada Municipal CPS-040
V-02 Az=180°00'00" D=25,00m confrontante: Gleba A, matrícula nº 12.344
V-03 Az=270°00'00" D=43,00m confrontante: Córrego Boa Vista
V-04 Az=0°00'00" D=25,00m confrontante: Gleba C

Área total de 1.000,00 m².
"""

if __name__ == "__main__":
    write_pdf("matricula_89214.pdf", MATRICULA)
    write_pdf("memorial_89214.pdf", memorial_utm())
    write_pdf("contrato_compra_venda.pdf", CONTRATO)
    write_pdf("memorial_nao_fecha.pdf", MEMORIAL_NAO_FECHA)
    write_pdf("vazio_escaneado.pdf", "")
    # Matrícula com perímetro georreferenciado na própria descrição (sem memorial separado)
    vertex_lines = [ln for ln in memorial_utm().splitlines() if ln.startswith("V-")]
    write_pdf("matricula_georref_77001.pdf", MATRICULA_GEORREF.replace("{VERTICES}", "\n".join(vertex_lines)))
    # Versões Word: memorial com tabela de vértices (.docx) e matrícula no formato antigo (.doc)
    write_docx("memorial_89214_tabela.docx", *memorial_utm(as_table=True))
    write_docx("contrato_compra_venda.docx", CONTRATO)
    write_docx("matricula_89214.docx", MATRICULA)
    docx_to_doc("matricula_89214.docx")
    print("Exemplos gerados em", OUT)
