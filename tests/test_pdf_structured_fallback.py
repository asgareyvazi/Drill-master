from core.import_adapters.pdf_tables import _pymupdf_structured_tables


class _Table:
    bbox = (1, 2, 3, 4)

    def __init__(self, rows):
        self._rows = rows

    def extract(self):
        return self._rows


class _Found:
    def __init__(self, tables):
        self.tables = tables


class _Page:
    def __init__(self, rows):
        self.rows = rows

    def find_tables(self):
        return _Found([_Table(self.rows)])


def test_find_tables_fallback_preserves_time_log_sections_and_bbox():
    rows = [["", "", "", "", "", "", "", "", "", "", "", "", "", ""] for _ in range(18)]
    rows[2] = ["Summary of Activities in Last 24:00 hours:"] + [None] * 13
    rows[3] = ["summary text"] + [None] * 13
    rows[4] = ["Operation Forecast for next 24 hour"] + [None] * 13
    rows[5] = ["forecast text"] + [None] * 13
    header = ["From", "To", None, "hrs", None, "Main\nPhase", None, "Code", None, "Sub\nCode", "Status", "NPT/ Unplan\nAttributed", None, "Rig Activity"]
    rows[6] = header
    rows[7] = ["00:00", "06:00", None, "6", None, "DRL", None, "2", None, "1", "PLN", None, None, "Drilling"]
    rows[9] = ["From", "To", None, "hrs.", None, "Main\nPhase", None, "Code", None, "Sub\nCode", "Status", "NPT/ Unplan\nAttributed", None, "Rig Activity"]
    rows[10] = ["00:00", "01:00", None, "1", None, "DRL", None, "2", None, "1", "PLN", None, None, "Morning"]

    sections = _pymupdf_structured_tables(_Page(rows), 3)
    by_name = {item["report"].get("section"): item for item in sections}
    assert by_name["time_log"]["data"][0]["Code"] == "2"
    assert by_name["time_log_morning"]["data"][0]["Morning Code"] == "2"
    assert by_name["daily_report_text"]["data"][0]["Summary"] == "summary text"
    assert by_name["time_log"]["report"]["bbox"] == (1, 2, 3, 4)
