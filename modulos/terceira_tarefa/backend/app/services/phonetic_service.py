"""Chave fonética para nomes em português com grafias históricas.

Inspirada no BuscaBR, mas ajustada às variações ortográficas comuns nos livros
cartorários dos séculos XIX e XX: Manoel/Manuel, Souza/Sousa, Thereza/Teresa,
Ignacio/Inácio, Phelippe/Felipe, Christovão/Cristóvão, Luiz/Luís, Joaquim/Joaquin.
O objetivo é que duas grafias da mesma pessoa gerem o mesmo código.
"""
import re
import unicodedata

# Partículas que não ajudam a identificar a pessoa.
_PARTICLES = {"DE", "DA", "DO", "DAS", "DOS", "E", "D", "DI", "DU"}

# Regras aplicadas em ordem, sobre palavras já em caixa alta e sem acentos.
_RULES: list[tuple[str, str]] = [
    (r"Y", "I"),
    (r"W", "V"),
    (r"PH", "F"),
    (r"TH", "T"),
    (r"CHR", "KR"),
    (r"CH", "X"),
    (r"SH", "X"),
    (r"LH", "LI"),
    (r"NH", "NI"),
    (r"H", ""),
    (r"GN", "N"),
    (r"CT", "T"),
    (r"PT", "T"),
    (r"MN", "N"),
    (r"SC(?=[EI])", "S"),
    (r"XC(?=[EI])", "S"),
    (r"QU(?=[EI])", "K"),
    (r"QU", "K"),
    (r"Q", "K"),
    (r"G(?=[EI])", "J"),
    (r"GU(?=[EI])", "G"),
    (r"C(?=[EI])", "S"),
    (r"C", "K"),
    (r"Ç", "S"),
    (r"Z", "S"),
    (r"M$", "N"),
    (r"N(?=[BP])", "M"),
    # Classes vocálicas: O/U e E/I alternam livremente nas grafias antigas.
    (r"O", "U"),
    (r"E", "I"),
]


def _strip_accents(text: str) -> str:
    text = text.upper().replace("Ç", "Ç")
    decomposed = unicodedata.normalize("NFD", text)
    out = []
    for ch in decomposed:
        if ch == "̧":  # cedilha vira S fonético
            if out and out[-1] == "C":
                out[-1] = "Ç"
            continue
        if unicodedata.category(ch) != "Mn":
            out.append(ch)
    return "".join(out)


def phonetic_word(word: str) -> str:
    w = re.sub(r"[^A-ZÇ]", "", _strip_accents(word))
    if not w:
        return ""
    for pattern, repl in _RULES:
        w = re.sub(pattern, repl, w)
    # Consoantes/vogais duplicadas: Pinheiro/Pinhero, Ferreira/Fereira, Mattos/Matos.
    w = re.sub(r"(.)\1+", r"\1", w)
    # Ditongo final "AU" e nasal "AN" se confundem (João/Joam, Christovão/Christovam).
    w = re.sub(r"AN$", "AU", w)
    return w


def _split_words(text: str) -> list[str]:
    # "d'Oliveira" -> ["D", "Oliveira"]; "M.el" -> ["M", "el"] (abreviações são tratadas pelo VLM)
    return [p for p in re.split(r"[\s'’.,;:\-/()\[\]]+", text) if p]


def phonetic_tokens(text: str) -> list[str]:
    tokens = []
    for word in _split_words(text):
        if _strip_accents(word) in _PARTICLES:
            continue
        code = phonetic_word(word)
        if len(code) >= 2:
            tokens.append(code)
    return tokens


def phonetic_name(name: str) -> str:
    return " ".join(phonetic_tokens(name))
