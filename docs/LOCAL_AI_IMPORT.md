# Optional local AI import assistance

The importer works without AI. For ambiguous labels only, install Ollama and a local instruct model:

```powershell
# Install Ollama from https://ollama.com/download
ollama pull qwen2.5:7b-instruct
```

Enable the assistant before starting DrillMaster:

```powershell
$env:DRILLMASTER_AI_IMPORT="1"
$env:DRILLMASTER_AI_MODEL="qwen2.5:7b-instruct"
python run.py
```

The default endpoint is `http://127.0.0.1:11434`. Override it with
`DRILLMASTER_OLLAMA_URL` if necessary.

AI proposals are never written directly to the database. They are restricted
to a canonical field allow-list, carry source coordinates and confidence, and
are marked `REVIEW` before the normal validation/save pipeline.

If Ollama is unavailable, Smart Import silently falls back to deterministic
normalization, workbook code catalogs and profile rules.
