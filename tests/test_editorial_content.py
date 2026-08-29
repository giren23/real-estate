from scripts.validate_editorial_content import DEFAULT_PATH, validate


def test_editorial_content_matches_schema() -> None:
    assert validate(DEFAULT_PATH) == []
