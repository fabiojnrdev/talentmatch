import re
import unicodedata
from collections.abc import Sequence

from app.schemas import ExtractionWire, ValidatedExtraction

MAX_ITEMS = 5
MAX_ITEM_CHARS = 200
MAX_JUSTIFICATION_CHARS = 600
MIN_EVIDENCE_CHARS = 3


class ExtractionInvalid(Exception):
    """Saída da LLM viola as regras de negócio. Mensagens NÃO contêm texto do currículo."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def _clean_list(items: list[str]) -> list[str]:
    cleaned = [i.strip()[:MAX_ITEM_CHARS] for i in items if i and i.strip()]
    return cleaned[:MAX_ITEMS]


def validate_extraction(
    wire: ExtractionWire, expected_keys: Sequence[str], cv_text: str
) -> ValidatedExtraction:
    errors: list[str] = []
    got = [item.key for item in wire.checklist]

    duplicated = sorted({k for k in got if got.count(k) > 1})
    missing = sorted(set(expected_keys) - set(got))
    unknown = sorted(set(got) - set(expected_keys))
    if duplicated:
        errors.append(f"requisitos duplicados no checklist: {duplicated}")
    if missing:
        errors.append(f"requisitos ausentes no checklist: {missing}")
    if unknown:
        errors.append(f"requisitos desconhecidos no checklist: {unknown}")

    haystack = normalize(cv_text)
    checklist: dict[str, bool] = {}
    evidence: dict[str, str | None] = {}
    for item in wire.checklist:
        if item.key in checklist or item.key not in expected_keys:
            continue
        quote = (item.evidence or "").strip()
        if item.met:
            if len(quote) < MIN_EVIDENCE_CHARS:
                errors.append(f"{item.key}: met=true exige evidence literal do currículo")
            elif normalize(quote) not in haystack:
                errors.append(f"{item.key}: evidence não é trecho literal do currículo")
        checklist[item.key] = item.met
        evidence[item.key] = quote if (item.met and quote) else None

    if not 0.0 <= wire.extraction_confidence <= 1.0:
        errors.append("extraction_confidence deve estar entre 0 e 1")
    justification = wire.justification.strip()[:MAX_JUSTIFICATION_CHARS]
    if not justification:
        errors.append("justification não pode ser vazia")

    if errors:
        raise ExtractionInvalid(errors)

    return ValidatedExtraction(
        checklist=checklist,
        evidence=evidence,
        strengths=_clean_list(wire.strengths),
        gaps=_clean_list(wire.gaps),
        extraction_confidence=wire.extraction_confidence,
        justification=justification,
    )
