"""Build a structurally equivalent, de-identified copy of a DDR workbook.

The real workbook never enters the repository.  This tool runs on the owner's
machine against the original file and a *private* substitution spec (kept
outside the repository; see ``docs/privacy/ddr_sanitization_spec.example.json``
for the format) and writes a synthetic fixture that keeps everything an import
test needs:

* every worksheet, its name, visibility, cell positions, merged ranges,
  styles, number formats, data validations, tables, charts and drawings;
* formulas *and* their cached results (the import service opens a workbook
  twice -- formulas and cached values -- so a round trip through openpyxl,
  which drops cached values, would change what the pipeline sees);
* technical values (depths, mud properties, BHA, chemicals, activity codes).

What it changes, at the OOXML part level:

* ``text_substitutions`` -- exact, case-sensitive substrings replaced in every
  XML/VML part (shared strings, inline and cached formula strings, formulas,
  comments, chart caches, table definitions, drawings, document properties).
  Longest originals are applied first so a short token cannot split a longer one.
* ``cell_values`` -- numeric cells overwritten by sheet name and reference
  (for example exact coordinates stored as numbers).
* embedded raster images are replaced by blank images of identical size and
  format (logos, signatures and photos);
* printer-settings parts (which can carry device and user names) are removed;
* document properties (creator, last-modified-by, company, manager, title)
  are cleared.

After writing, the tool re-opens the output and verifies that no original
substitution token occurs in *any* part, binary parts included (as UTF-8 and
UTF-16-LE).  The originals are never printed; a failure names the part only.

Usage::

    python tools/privacy/sanitize_ddr_workbook.py ORIGINAL.xlsx OUT.xlsx --spec PRIVATE_SPEC.json
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

FIXED_DATE_TIME = (2024, 1, 1, 0, 0, 0)
TEXT_SUFFIXES = (".xml", ".vml", ".rels")
DOC_PROPERTY_TAGS = ("dc:creator", "cp:lastModifiedBy", "Company", "Manager", "dc:title", "dc:subject",
                     "dc:description", "cp:keywords", "cp:category")


class SanitizationError(RuntimeError):
    """The output still contains protected content or the spec is invalid."""


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    subs = spec.get("text_substitutions", [])
    if not isinstance(subs, list) or not all(isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) and s
                                                                                           for s in p) for p in subs):
        raise SanitizationError("text_substitutions must be a list of [original, replacement] string pairs")
    for original, replacement in subs:
        if original in replacement:
            raise SanitizationError("a replacement may not contain its own original token")
    cells = spec.get("cell_values", {})
    if not isinstance(cells, dict) or not all(isinstance(v, (int, float)) for v in cells.values()):
        raise SanitizationError("cell_values must map 'Sheet!A1' to a number")
    for key in cells:
        if "!" not in key or not re.fullmatch(r"[A-Z]{1,3}[0-9]{1,7}", key.rsplit("!", 1)[1]):
            raise SanitizationError("cell_values keys must look like 'Sheet name!A1'")
    return {"text_substitutions": sorted(subs, key=lambda p: -len(p[0])), "cell_values": cells,
            "verify_absent": [s for s in spec.get("verify_absent", []) if isinstance(s, str) and s]}


def _xml_forms(token: str) -> set[str]:
    """The ways a token can be spelled inside XML text."""
    return {token, escape(token), escape(token, {'"': "&quot;", "'": "&apos;"})}


def substitute_text(text: str, substitutions: list[list[str]]) -> str:
    for original, replacement in substitutions:
        for form in _xml_forms(original):
            text = text.replace(form, escape(replacement) if form != original else replacement)
    return text


def _sheet_parts(files: dict[str, bytes]) -> dict[str, str]:
    """Map sheet name -> worksheet part path using workbook.xml and its rels."""
    workbook = files["xl/workbook.xml"].decode("utf-8")
    rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    targets = dict(re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    targets.update({k: v for v, k in re.findall(r'<Relationship[^>]*Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
    out = {}
    for name, rid in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', workbook):
        target = targets[rid].lstrip("/")
        out[name.replace("&amp;", "&")] = target if target.startswith("xl/") else f"xl/{target}"
    return out


def _set_numeric_cell(xml: str, ref: str, value: float | int) -> str:
    pattern = re.compile(r'(<c r="%s"(?![^>]*t="(?:s|str|inlineStr)")[^>]*>)(.*?)(</c>)' % re.escape(ref), re.S)
    match = pattern.search(xml)
    if not match:
        raise SanitizationError(f"numeric cell {ref} not found (or not numeric)")
    body = match.group(2)
    if "<v>" not in body:
        raise SanitizationError(f"cell {ref} has no stored value")
    body = re.sub(r"<v>[^<]*</v>", f"<v>{value}</v>", body, count=1)
    return xml[:match.start()] + match.group(1) + body + match.group(3) + xml[match.end():]


def _blank_image(data: bytes, name: str) -> bytes:
    from PIL import Image  # pillow is a locked runtime dependency (matplotlib)

    with Image.open(io.BytesIO(data)) as source:
        size, fmt = source.size, (source.format or "PNG")
    blank = Image.new("RGB", size, (255, 255, 255))
    out = io.BytesIO()
    blank.save(out, format="JPEG" if fmt.upper() in ("JPEG", "JPG") else "PNG")
    return out.getvalue()


def _drop_printer_settings(files: dict[str, bytes]) -> None:
    printer_parts = [n for n in files if n.startswith("xl/printerSettings/")]
    for name in printer_parts:
        del files[name]
    for name in list(files):
        if not name.endswith(".rels"):
            continue
        text = files[name].decode("utf-8")
        removed_ids = re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="[^"]*printerSettings[^"]*"[^>]*/>', text)
        removed_ids += re.findall(r'<Relationship[^>]*Target="[^"]*printerSettings[^"]*"[^>]*Id="([^"]+)"[^>]*/>', text)
        if not removed_ids:
            continue
        text = re.sub(r'<Relationship[^>]*printerSettings[^>]*/>', "", text)
        files[name] = text.encode("utf-8")
        owner = name.replace("_rels/", "").removesuffix(".rels")
        if owner in files:
            owner_xml = files[owner].decode("utf-8")
            for rid in removed_ids:
                owner_xml = re.sub(r'\s+r:id="%s"' % re.escape(rid), "", owner_xml)
            files[owner] = owner_xml.encode("utf-8")
    ct = files["[Content_Types].xml"].decode("utf-8")
    ct = re.sub(r'<Override[^>]*PartName="/xl/printerSettings/[^"]*"[^>]*/>', "", ct)
    ct = re.sub(r'<Default[^>]*Extension="bin"[^>]*ContentType="[^"]*printerSettings[^"]*"[^>]*/>', "", ct)
    files["[Content_Types].xml"] = ct.encode("utf-8")


def _scrub_doc_properties(text: str) -> str:
    for tag in DOC_PROPERTY_TAGS:
        text = re.sub(r"(<%s(?:\s[^>]*)?>)[^<]*(</%s>)" % (re.escape(tag), re.escape(tag)), r"\1\2", text)
    return text


def protected_tokens(spec: dict) -> list[str]:
    return [p[0] for p in spec["text_substitutions"]] + spec["verify_absent"] + [
        str(v) for v in _original_cell_values(spec)]


def _original_cell_values(spec: dict) -> list:
    return spec.get("_original_cell_values", [])


def find_leaks(archive: bytes, tokens: list[str]) -> list[str]:
    """Return the names of parts that still contain any token (never the token)."""
    leaks = []
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for info in zf.infolist():
            data = zf.read(info)
            for token in tokens:
                forms = {token.encode("utf-8"), token.encode("utf-16-le"), escape(token).encode("utf-8")}
                if any(form in data for form in forms):
                    leaks.append(info.filename)
                    break
    return sorted(set(leaks))


def sanitize(original: bytes, spec: dict) -> bytes:
    with zipfile.ZipFile(io.BytesIO(original)) as zf:
        order = [i.filename for i in zf.infolist()]
        files = {name: zf.read(name) for name in order}

    sheets = _sheet_parts(files)
    originals = []
    for key, value in spec["cell_values"].items():
        sheet, ref = key.rsplit("!", 1)
        if sheet not in sheets:
            raise SanitizationError(f"sheet {sheet!r} not found")
        part = sheets[sheet]
        xml = files[part].decode("utf-8")
        found = re.search(r'<c r="%s"[^>]*>.*?<v>([^<]*)</v>' % re.escape(ref), xml, re.S)
        if found:
            originals.append(found.group(1))
        files[part] = _set_numeric_cell(xml, ref, value).encode("utf-8")
    spec["_original_cell_values"] = originals

    for name in list(files):
        lower = name.lower()
        if lower.endswith(TEXT_SUFFIXES):
            text = files[name].decode("utf-8")
            text = substitute_text(text, spec["text_substitutions"])
            if name.startswith("docProps/"):
                text = _scrub_doc_properties(text)
            files[name] = text.encode("utf-8")
        elif name.startswith("xl/media/") and lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
            files[name] = _blank_image(files[name], name)
        elif name.startswith("xl/media/") and lower.endswith((".emf", ".wmf")):
            raise SanitizationError(f"vector image {name} cannot be blanked safely; remove it from the source")

    _drop_printer_settings(files)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in order:
            if name in files:
                info = zipfile.ZipInfo(name, date_time=FIXED_DATE_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, files[name])
    archive = out.getvalue()

    tokens = [t for t in protected_tokens(spec) if t]
    leaks = find_leaks(archive, tokens)
    if leaks:
        raise SanitizationError("protected content remains in parts: " + ", ".join(leaks))
    return archive


def _substitute_value(value, substitutions: list[list[str]]):
    """Plain-value form of :func:`substitute_text` for cell dumps (JSON).

    A pair written ``[">X<", ">Y<"]`` is anchored to a whole XML text node in
    the workbook; in a value dump the same anchor means whole-value equality.
    """
    if not isinstance(value, str):
        return value
    for original, replacement in substitutions:
        if original.startswith(">") and original.endswith("<"):
            if value == original[1:-1]:
                value = replacement[1:-1]
        else:
            value = value.replace(original, replacement)
    return value


def sanitize_cell_dump(dump: dict, spec: dict) -> dict:
    """De-identify a ``{sheet: {ref: {"value": ...}}}`` cell dump with the same spec."""
    out = {}
    for sheet, cells in dump.items():
        out[sheet] = {}
        for ref, record in cells.items():
            record = dict(record)
            key = f"{sheet}!{ref}"
            if key in spec["cell_values"]:
                record["value"] = spec["cell_values"][key]
            else:
                record["value"] = _substitute_value(record.get("value"), spec["text_substitutions"])
            out[sheet][ref] = record
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="De-identify a DDR workbook (see module docstring).")
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--spec", type=Path, required=True, help="private substitution spec (never commit it)")
    parser.add_argument("--cell-dump", action="store_true",
                        help="treat ORIGINAL/OUTPUT as a JSON cell dump instead of an .xlsx workbook")
    args = parser.parse_args(argv)
    if args.output.resolve() == args.original.resolve() and not args.cell_dump:
        parser.error("refusing to overwrite the original workbook")
    spec = load_spec(args.spec)
    if args.cell_dump:
        dump = sanitize_cell_dump(json.loads(args.original.read_text(encoding="utf-8")), spec)
        text = json.dumps(dump, indent=2, ensure_ascii=False)
        leaks = [t for t in protected_tokens(spec) if t and t in text]
        if leaks:
            print(f"FAIL: {len(leaks)} protected token(s) remain in the cell dump", file=sys.stderr)
            return 1
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}; protected tokens verified absent")
        return 0
    try:
        archive = sanitize(args.original.read_bytes(), spec)
    except SanitizationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(archive)
    print(f"wrote {args.output} ({len(archive)} bytes); protected tokens verified absent in every part")
    return 0


if __name__ == "__main__":
    sys.exit(main())
