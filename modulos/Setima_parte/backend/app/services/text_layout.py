"""Índice de texto por página que mapeia trechos de string de volta a coordenadas.

O texto da página é reconstruído a partir das palavras do PyMuPDF (cada uma com
bbox exato). Palavras da mesma linha são unidas por espaço e linhas por "\n";
assim, um trecho encontrado por regex ou pelo LLM pode ser convertido nas
palavras que o compõem e, daí, num retângulo por linha.
"""

import re
from dataclasses import dataclass

import pymupdf


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    line_key: tuple[int, int]
    start: int
    end: int


class PageTextIndex:
    def __init__(self, page: pymupdf.Page):
        self.page_number = page.number + 1
        self.words: list[Word] = []
        parts: list[str] = []
        pos = 0
        prev_key: tuple[int, int] | None = None
        for x0, y0, x1, y1, text, block, line, _ in page.get_text("words", sort=True):
            key = (block, line)
            if prev_key is not None:
                parts.append(" " if key == prev_key else "\n")
                pos += 1
            self.words.append(Word(x0, y0, x1, y1, text, key, pos, pos + len(text)))
            parts.append(text)
            pos += len(text)
            prev_key = key
        self.text = "".join(parts)

    def rects_for_span(self, start: int, end: int) -> list[pymupdf.Rect]:
        """Retângulos (um por linha) cobrindo todas as palavras tocadas pelo trecho.

        Palavras parcialmente cobertas entram inteiras: preferimos tarjar a mais
        a deixar um fragmento do dado visível.
        """
        rects: list[pymupdf.Rect] = []
        current_key = None
        for w in self.words:
            if w.end <= start or w.start >= end:
                continue
            r = pymupdf.Rect(w.x0, w.y0, w.x1, w.y1)
            if w.line_key == current_key:
                rects[-1] |= r
            else:
                rects.append(r)
                current_key = w.line_key
        return rects

    def find_phrase(self, phrase: str) -> list[tuple[int, int]]:
        """Localiza uma frase (ex.: devolvida pelo LLM) tolerando diferenças de espaçamento."""
        tokens = phrase.split()
        if not tokens:
            return []
        pattern = re.compile(r"\s+".join(re.escape(t) for t in tokens))
        spans = [m.span() for m in pattern.finditer(self.text)]
        if not spans:
            spans = [m.span() for m in re.compile(pattern.pattern, re.IGNORECASE).finditer(self.text)]
        return spans
