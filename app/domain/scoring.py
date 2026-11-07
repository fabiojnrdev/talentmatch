from collections.abc import Sequence

from app.schemas import MustHave


def compute_match_score(must_have: Sequence[MustHave], checklist: dict[str, bool]) -> float:
    """Score determinístico: soma dos pesos atendidos / soma total dos pesos * 100.

    A LLM NUNCA calcula o score; ela apenas extrai evidências.
    """
    total = sum(m.weight for m in must_have)
    if total <= 0:
        raise ValueError("must_have vazio ou com peso total inválido")
    missing = [m.key for m in must_have if m.key not in checklist]
    if missing:
        raise ValueError(f"checklist sem os requisitos: {missing}")
    achieved = sum(m.weight for m in must_have if checklist[m.key])
    return round(100.0 * achieved / total, 1)
