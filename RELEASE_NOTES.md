# NNNNN current development snapshot

The `arena/019fc7b1-nnnnn` branch contains the consolidated Universal Import implementation:

- One Import Report(s) entry point for XLSX/XLSM/CSV/PDF and batch files
- workbook scanning, table/column profiling and embedded DDR table extraction
- merged-cell normalization without duplicating merged labels
- workbook Activity Code catalog and company-agnostic mapping memory
- optional local Ollama AI mapping with persistent model selection
- complete import review matrix (scalar and row-oriented records)
- validation, duplicate detection, section/well identity resolution and rollback cleanup
- PDF table adapter (Camelot when installed, PyMuPDF fallback)
- report deletion cleanup and inventory carry-forward
- optional engineering/PDF capability adapters

Engineering calculation engines remain optional and are not enabled implicitly; they must be benchmarked against the built-in calculations before being used operationally.
