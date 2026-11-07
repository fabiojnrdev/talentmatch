import pytest

from app.domain.validation import ExtractionInvalid, normalize, validate_extraction
from app.schemas import ExtractionWire
from tests.helpers import CV, good_payload

KEYS = ["fastapi_experience", "async_architecture", "pytest_coverage"]


def _wire(**kw):
    return ExtractionWire(**good_payload(**kw))


def test_valid_extraction():
    v = validate_extraction(_wire(), KEYS, CV)
    assert v.checklist == {"fastapi_experience": True, "async_architecture": True, "pytest_coverage": False}
    assert v.evidence["pytest_coverage"] is None


def test_evidence_match_is_case_and_whitespace_insensitive():
    payload = good_payload()
    payload["checklist"][0]["evidence"] = "apis   ASSÍNCRONAS\ncom fastapi"
    assert validate_extraction(ExtractionWire(**payload), KEYS, CV).checklist["fastapi_experience"]


def test_missing_unknown_duplicated_keys():
    payload = good_payload()
    payload["checklist"] = [
        {"key": "fastapi_experience", "met": False, "evidence": None},
        {"key": "fastapi_experience", "met": False, "evidence": None},
        {"key": "invented", "met": False, "evidence": None},
    ]
    with pytest.raises(ExtractionInvalid) as exc:
        validate_extraction(ExtractionWire(**payload), KEYS, CV)
    joined = " ".join(exc.value.errors)
    assert "duplicados" in joined and "ausentes" in joined and "desconhecidos" in joined


def test_met_true_requires_literal_evidence():
    payload = good_payload()
    payload["checklist"][0]["evidence"] = None
    payload["checklist"][1]["evidence"] = "texto que não existe no currículo"
    with pytest.raises(ExtractionInvalid) as exc:
        validate_extraction(ExtractionWire(**payload), KEYS, CV)
    assert len(exc.value.errors) == 2
    assert "não existe" not in " ".join(exc.value.errors)  # erro não ecoa conteúdo


def test_evidence_dropped_when_not_met():
    payload = good_payload()
    payload["checklist"][2] = {"key": "pytest_coverage", "met": False, "evidence": "Pytest"}
    assert validate_extraction(ExtractionWire(**payload), KEYS, CV).evidence["pytest_coverage"] is None


@pytest.mark.parametrize("conf", [-0.1, 1.01])
def test_confidence_out_of_range(conf):
    with pytest.raises(ExtractionInvalid):
        validate_extraction(_wire(extraction_confidence=conf), KEYS, CV)


def test_empty_justification():
    with pytest.raises(ExtractionInvalid):
        validate_extraction(_wire(justification="   "), KEYS, CV)


def test_lists_are_trimmed_and_truncated():
    v = validate_extraction(_wire(strengths=["a" * 500, "", "  ", "b", "c", "d", "e", "f"], gaps=[],
                                  justification="j" * 900), KEYS, CV)
    assert len(v.strengths) == 5 and len(v.strengths[0]) == 200
    assert len(v.justification) == 600 and v.gaps == []


def test_normalize():
    assert normalize("  Á  b\n C ") == "á b c"
