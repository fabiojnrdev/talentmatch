import pytest

from app.domain.scoring import compute_match_score
from app.schemas import MustHave

MH = [MustHave(key="aa", description="desc a", weight=2), MustHave(key="bb", description="desc b", weight=1),
      MustHave(key="cc", description="desc c", weight=1)]


def test_weighted_score():
    assert compute_match_score(MH, {"aa": True, "bb": False, "cc": True}) == 75.0
    assert compute_match_score(MH, {"aa": True, "bb": True, "cc": True}) == 100.0
    assert compute_match_score(MH, {"aa": False, "bb": False, "cc": False}) == 0.0


def test_deterministic_and_rounded():
    mh = [MustHave(key="aa", description="desc a"), MustHave(key="bb", description="desc b"),
          MustHave(key="cc", description="desc c")]
    results = {compute_match_score(mh, {"aa": True, "bb": False, "cc": False}) for _ in range(50)}
    assert results == {33.3}


def test_missing_key_and_empty_raise():
    with pytest.raises(ValueError):
        compute_match_score(MH, {"aa": True})
    with pytest.raises(ValueError):
        compute_match_score([], {})
