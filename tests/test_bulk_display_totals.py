from core.bulk_material_semantics import summarize_bulk_display_rows


def test_unknown_stock_totals_stay_unknown_while_known_movements_are_counted():
    totals = summarize_bulk_display_rows([
        {"initial": "10.0", "received": "2.0", "used": "1.0", "current": "11.0"},
        {"initial": "—", "received": "3.0", "used": "1.0", "current": "—"},
    ])

    assert totals == {
        "initial": None,
        "received": 5.0,
        "used": 2.0,
        "current": None,
        "count": 2,
    }


def test_explicit_zero_is_preserved_and_empty_table_matches_existing_contract():
    zero = summarize_bulk_display_rows([
        {"initial": "0", "received": "0", "used": "0", "current": "0"},
    ])
    assert zero == {
        "initial": 0.0, "received": 0.0, "used": 0.0, "current": 0.0, "count": 1,
    }

    assert summarize_bulk_display_rows([]) == {
        "initial": 0.0, "received": 0.0, "used": 0.0, "current": 0.0, "count": 0,
    }


def test_blank_movements_mean_no_movement_but_blank_stock_is_unknown():
    totals = summarize_bulk_display_rows([
        {"initial": "", "received": "", "used": "", "current": ""},
    ])
    assert totals == {
        "initial": None, "received": 0.0, "used": 0.0, "current": None, "count": 1,
    }


def test_malformed_or_non_finite_display_values_do_not_make_a_zero_total():
    totals = summarize_bulk_display_rows([
        {"initial": "bad", "received": "nan", "used": "2", "current": "inf"},
    ])
    assert totals == {
        "initial": None, "received": None, "used": 2.0, "current": None, "count": 1,
    }
