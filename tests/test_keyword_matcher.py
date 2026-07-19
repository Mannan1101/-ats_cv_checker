from services.keyword_matcher import (
    find_weak_verbs,
    has_quantified_result,
    match_terms,
    starts_with_strong_verb,
    text_contains_term,
)


def test_text_contains_term_direct_match():
    assert text_contains_term("Experienced in Python and Docker", "Python")


def test_text_contains_term_alias_match():
    assert text_contains_term("Built services on AWS", "Amazon Web Services")
    assert text_contains_term("Skilled in JS and TS", "JavaScript")


def test_text_contains_term_short_alias_avoids_false_positive():
    # "ml" should not match inside "html"
    assert not text_contains_term("Built responsive HTML pages", "machine learning")


def test_match_terms_splits_matched_and_missing():
    result = match_terms("Python, Docker, PostgreSQL", ["Python", "Kubernetes", "Docker"])
    assert set(result.matched) == {"Python", "Docker"}
    assert result.missing == ["Kubernetes"]
    assert result.match_ratio == round(100 * 2 / 3, 2)


def test_match_ratio_is_100_when_no_terms_required():
    result = match_terms("anything", [])
    assert result.match_ratio == 100.0


def test_find_weak_verbs_detects_known_phrases():
    assert find_weak_verbs("Responsible for managing the team") == ["responsible for"]
    assert find_weak_verbs("Led the migration project") == []


def test_starts_with_strong_verb():
    assert starts_with_strong_verb("Led a team of five engineers")
    assert not starts_with_strong_verb("Worked on the backend service")


def test_has_quantified_result():
    assert has_quantified_result("Reduced latency by 30%")
    assert not has_quantified_result("Improved system performance")
