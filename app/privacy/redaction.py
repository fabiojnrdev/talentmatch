"""Pseudonimização best-effort ANTES de qualquer envio à LLM ou persistência.

Limitações (documentadas em docs/LGPD.md): regex + heurística de cabeçalho não
substituem NER; revisar com amostras reais antes de qualquer uso produtivo.
"""
import re
from dataclasses import dataclass

REPORT_KEYS = ("name", "email", "url", "cpf", "phone", "date", "cep", "address", "sensitive_lines")

_PARTICLES = {"de", "da", "do", "dos", "das", "e"}
_NAME_WORD = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'’\-]+$")

_SENSITIVE_LABEL = re.compile(
    r"^\s*(estado\s+civil|nacionalidade|naturalidade|data\s+de\s+nascimento|nascimento|nasc\.?|"
    r"sexo|g[eê]nero|ra[cç]a|cor|etnia|religi[aã]o|filia[cç][aã]o|idade|"
    r"orienta[cç][aã]o\s+sexual|pcd)\s*[:\-–]",
    re.IGNORECASE,
)
_SENSITIVE_ANY = re.compile(
    r"\b(pcd|pessoa\s+com\s+defici[eê]ncia|cid-?10|sindicato|sindicalizad[oa])\b", re.IGNORECASE
)

_SUBSTITUTIONS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    (
        "url",
        re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin\.com|github\.com|gitlab\.com|behance\.net)/\S+", re.I),
        "[URL]",
    ),
    ("cpf", re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"), "[CPF]"),
    ("phone", re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[-.\s]?\d{4}(?!\d)"), "[TELEFONE]"),
    ("date", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"), "[DATA]"),
    ("cep", re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)"), "[CEP]"),
    (
        "address",
        re.compile(r"\b(?:rua|avenida|av\.|av|travessa|alameda|rodovia|estrada)(?=\s)[^\n]{0,80}", re.I),
        "[ENDERECO]",
    ),
)


@dataclass(frozen=True)
class RedactionResult:
    text: str
    report: dict[str, int]  # apenas contagens, nunca os valores removidos


def _looks_like_name(line: str) -> bool:
    words = line.split()
    if not 2 <= len(words) <= 6:
        return False
    for w in words:
        if not _NAME_WORD.match(w):
            return False
        if w.lower() in _PARTICLES:
            continue
        if not w[0].isupper():
            return False
    return True


def redact(text: str) -> RedactionResult:
    report = dict.fromkeys(REPORT_KEYS, 0)

    kept: list[str] = []
    for line in text.splitlines():
        if _SENSITIVE_LABEL.match(line) or _SENSITIVE_ANY.search(line):
            report["sensitive_lines"] += 1
            continue
        kept.append(line)

    name_parts: list[str] = []
    for i, line in enumerate(kept):
        if line.strip():
            if _looks_like_name(line.strip()):
                name_parts = [w for w in line.split() if w.lower() not in _PARTICLES and len(w) >= 3]
                kept[i] = "[NOME]"
                report["name"] += 1
            break

    result = "\n".join(kept)
    for key, pattern, placeholder in _SUBSTITUTIONS:
        result, n = pattern.subn(placeholder, result)
        report[key] += n
    if name_parts:  # o nome também aparece no corpo (assinatura, "Eu, Maria...")
        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(p) for p in sorted(set(name_parts), key=len, reverse=True)) + r")\b",
            re.IGNORECASE,
        )
        result, n = pattern.subn("[NOME]", result)
        report["name"] += n
    return RedactionResult(text=result, report=report)
