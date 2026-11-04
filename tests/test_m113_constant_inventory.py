"""M113: the unit-conversion constant inventory is current, finds every variant (code literals only), flags
the inconsistent quantities, and the document states the versioning strategy. No value is changed."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("constant_inventory", ROOT / "tools" / "quality" / "constant_inventory.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
DOC = (ROOT / "docs" / "engineering" / "M113_CONSTANT_INVENTORY.md").read_text(encoding="utf-8")


def test_the_committed_inventory_is_current():
    assert ci.scan() == json.loads(ci.OUT.read_text(encoding="utf-8"))


def test_inconsistent_quantities_are_flagged_with_their_difference():
    result = ci.scan()
    assert result["inconsistent"] == ["ft³ per bbl", "pcf per ppg (gal per ft³)"]
    pcf = result["quantities"]["pcf per ppg (gal per ft³)"]
    assert set(pcf["inconsistency"]["variants"]) == {"7.48052", "7.4805", "7.48"}
    assert abs(pcf["inconsistency"]["max_relative_difference"] - (7.48052 - 7.48) / 7.48) < 1e-8
    assert pcf["variants"]["7.48"]["files"]["core/engineering/well_control_kill_sheet.py"] == 1
    assert pcf["variants"]["7.48052"]["files"]["core/hydraulics_engine.py"] == 4


def test_comments_and_strings_are_not_counted(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "a.py").write_text('X = 7.48\n# 7.48052 in a comment\nY = "7.4805 in text"\nZ = 7.480\n',
                                            encoding="utf-8")
    pcf = ci.scan(tmp_path)["quantities"]["pcf per ppg (gal per ft³)"]
    assert {v: i["uses"] for v, i in pcf["variants"].items()} == {"7.48052": 0, "7.4805": 0, "7.48": 2}
    assert "inconsistency" not in pcf


def test_f_string_replacement_fields_count_on_every_python_version(tmp_path):
    """M118: v1 counted these only on Python >= 3.12 (tokenizer change), so CI 3.12/3.13 disagreed with 3.11."""
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "a.py").write_text(
        'A = f"{d * 3.28084:.1f} ft, {{0.3048}} escaped"\n'
        "B = f'{x!r:>10} {(lambda: 0.3048)()} {y = }'\n"
        'C = "{3.28084} is text"\n', encoding="utf-8")
    ft = ci.scan(tmp_path)["quantities"]["ft per m"]["variants"]
    assert (ft["3.28084"]["uses"], ft["0.3048"]["uses"]) == (1, 1)
    assert ci._code_tokens('f"{a!=2} {b[1:2]:{w}.3f}"') == ["2", "1", "2"]
    assert ci.scan()["version"] == "M113 constant inventory v2"


def test_conventions_and_the_document_agree_with_the_scan():
    result = ci.scan()
    for name in ("cost per length", "dog-leg severity unit", "temperature unit"):
        assert all(v["uses"] for v in result["conventions"][name].values()), name
    pcf = result["quantities"]["pcf per ppg (gal per ft³)"]["variants"]
    assert f"7.48052 ({pcf['7.48052']['uses']}), 7.48 ({pcf['7.48']['uses']}), 7.4805 ({pcf['7.4805']['uses']})" in DOC
    assert "No value was changed in M113" in DOC and "new method version" in DOC
    assert "the current constant is never assigned to them" in DOC
