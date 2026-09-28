"""Run a real, external MinerU integration check against one input file.

This is intentionally a harness, not a bundled MinerU implementation.  On
Windows, run it with the DrillMaster Python and configure the existing MinerU
launcher, for example:

    $env:MINERU_EXECUTABLE = 'C:\\Users\\A-Eyvazi\\Desktop\\mineru-env\\Scripts\\mineru.exe'
    python tools/mineru_integration.py C:\\path\\to\\real-report.pdf

The command exits non-zero unless MinerU actually produces inspectable output
and canonical validation succeeds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from core.mineru_engine import DocumentNormalizer, MinerUAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a real external MinerU installation")
    parser.add_argument("input", type=Path, help="real PDF, DOCX, PPTX, XLSX, or image file")
    args = parser.parse_args(argv)

    adapter = MinerUAdapter()
    health = adapter.health_check()
    print(json.dumps({"health": health.to_dict()}, indent=2, ensure_ascii=False))
    if not health.available:
        print("MinerU is not available; configure MINERU_EXECUTABLE or MINERU_PYTHON.", file=sys.stderr)
        return 2

    result = adapter.parse_file(args.input)
    if not result.success or result.document is None:
        print(
            json.dumps(
                {
                    "success": False,
                    "error_type": result.error_type,
                    "error": result.error,
                },
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 3

    normalized = DocumentNormalizer().normalize(result.document)
    summary = {
        "success": normalized.validation.valid,
        "source": str(args.input),
        "backend": result.document.backend,
        "method": result.document.method,
        "pages": result.document.page_count,
        "tables": result.document.table_count,
        "fields_extracted": normalized.fields_extracted,
        "output_files": result.document.raw_files,
        "warnings": normalized.warnings,
        "validation_errors": normalized.validation.errors,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if normalized.validation.valid else 4


if __name__ == "__main__":
    raise SystemExit(main())
