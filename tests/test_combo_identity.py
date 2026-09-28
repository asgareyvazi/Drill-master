from core.combo_identity import ComboCatalog, DEFAULT_ACTIVITY_CATALOG, normalize_label


def test_ddr_one_based_ordinals_resolve_to_application_identity():
    main = DEFAULT_ACTIVITY_CATALOG.resolve_main("2")
    sub = DEFAULT_ACTIVITY_CATALOG.resolve_sub("1", "2")
    assert main.accepted and main.identity == "2 - Drilling"
    assert sub.accepted and sub.identity == "2.1 - Vertical Drilling"
    assert main.method == "ordinal"
    assert sub.method == "ordinal"


def test_code_label_normalized_label_and_alias_all_resolve_without_index_fallback():
    assert DEFAULT_ACTIVITY_CATALOG.resolve_main("2 - Drilling").identity == "2 - Drilling"
    assert DEFAULT_ACTIVITY_CATALOG.resolve_main("Drilling").identity == "2 - Drilling"
    assert DEFAULT_ACTIVITY_CATALOG.resolve_main("  DRILLING ").method == "normalized_label"
    assert DEFAULT_ACTIVITY_CATALOG.resolve_main("DRL").identity == "2 - Drilling"
    assert DEFAULT_ACTIVITY_CATALOG.resolve_main("DRL").method == "alias"
    assert normalize_label("Drilling—Operation") == "drilling operation"


def test_blank_invalid_and_out_of_range_values_are_reviewable_not_first_item():
    for value in (None, "", "not-a-code", "999", "0", "-1"):
        result = DEFAULT_ACTIVITY_CATALOG.resolve_main(value)
        assert not result.accepted
        assert result.status == "REVIEW_REQUIRED"
        assert result.identity is None
    result = DEFAULT_ACTIVITY_CATALOG.resolve_sub("999", "2")
    assert result.status == "REVIEW_REQUIRED"
    assert result.identity is None


def test_ambiguous_label_is_not_resolved_to_the_first_combo_item():
    catalog = ComboCatalog(main_labels={"1": "Same", "2": "Same"})
    result = catalog.resolve_main("same", ordinal_mode="application")
    assert result.status == "REVIEW_REQUIRED"
    assert result.method == "ambiguous"
    assert result.identity is None
    assert result.candidates == ("1 - Same", "2 - Same")


def test_sub_numeric_requires_authoritative_parent():
    result = DEFAULT_ACTIVITY_CATALOG.resolve_sub("1")
    assert result.status == "REVIEW_REQUIRED"
    assert result.method == "unresolved"
    assert result.identity is None
