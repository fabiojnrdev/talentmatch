import pytest
from pydantic import ValidationError

from app.schemas import JobCreate, MustHave, ValidatedExtraction


def _job(**kw):
    base = {"title": "Vaga X", "must_have": [{"key": "fastapi", "description": "FastAPI"}]}
    base.update(kw)
    return base


def test_valid_job_defaults_weight():
    job = JobCreate(**_job())
    assert job.must_have[0].weight == 1.0


@pytest.mark.parametrize("bad", [
    _job(title="ab"),
    _job(must_have=[]),
    _job(must_have=[{"key": "Bad Key", "description": "xxx"}]),
    _job(must_have=[{"key": "ok_key", "description": "xxx", "weight": 0}]),
    _job(must_have=[{"key": "ok_key", "description": "xxx", "weight": 11}]),
    _job(must_have=[{"key": "ok_key", "description": "xx"}]),
    _job(extra_field=1),
    _job(must_have=[{"key": f"k{i:02d}", "description": "xxx"} for i in range(16)]),
])
def test_invalid_jobs(bad):
    with pytest.raises(ValidationError):
        JobCreate(**bad)


def test_duplicate_keys_rejected():
    with pytest.raises(ValidationError, match="duplicadas"):
        JobCreate(**_job(must_have=[{"key": "aa", "description": "xxx"}, {"key": "aa", "description": "yyy"}]))


def test_must_have_forbids_extra():
    with pytest.raises(ValidationError):
        MustHave(key="aa", description="xxx", foo=1)


def test_validated_extraction_confidence_bounds():
    with pytest.raises(ValidationError):
        ValidatedExtraction(checklist={}, evidence={}, strengths=[], gaps=[], extraction_confidence=1.5,
                            justification="x")
