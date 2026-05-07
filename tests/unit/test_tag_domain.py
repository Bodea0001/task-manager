from domain.tags import normalize_tag_name


def test_tag_name_is_normalized() -> None:
    # Act
    sut = normalize_tag_name("  Client   Report  ")

    # Assert
    assert sut == "client report"


def test_empty_tag_name_is_normalized_to_empty_string() -> None:
    # Act
    sut = normalize_tag_name("   ")

    # Assert
    assert sut == ""
