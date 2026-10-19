# Privacy check — rule reference

`tools/privacy/privacy_check.py` scans the tracked population (`git ls-files`)
with the rules in `tools/privacy/policy.json`. It runs in the test suite
(`tests/test_privacy_check.py::test_tracked_repository_population_is_clean`),
so the Source release gate enforces it on every push.

```bash
python tools/privacy/privacy_check.py              # whole tracked tree
python tools/privacy/privacy_check.py path/a path/b
```

Exit status: `0` clean, `1` findings, `2` configuration error. Output names the
rule, the file (and the archive member) and the line — **never the matched
text**, so it is safe in public CI logs.

## Rules

| Policy key | Rule id | Meaning |
|---|---|---|
| `prohibited_filename_patterns` | `prohibited-filename` | file names that follow a real operational convention (`NN-DDR …`), key/keystore files, `.env`, SQLite databases and backups — anywhere in the tree |
| `data_file_suffixes` + `allowlisted_data_files` | `data-file-not-allowlisted`, `allowlisted-data-file-changed` | spreadsheets, PDFs, Office files, images and archives must be listed by path **and** SHA-256; a different file under an approved name fails |
| `text_patterns` | `windows-user-profile-path`, `private-key-block`, `github-token`, `aws-access-key`, `slack-token`, `openai-style-key` | text files and the XML members of `.xlsx/.xlsm/.docx/.pptx` files |
| `allowed_email_domains` | `email-outside-allowed-domains` | any address outside the listed domains |
| `denylist_sha256` | `denylisted-identity-token` | word tokens (and their `.`/`-` parts) whose salted SHA-256 digest is listed; numbers are compared without thousands separators |

Spreadsheets are **not** rejected wholesale: synthetic fixtures are legitimate
and are allowlisted after review.

## Adding an approved data file

1. Confirm it is synthetic or explicitly authorised and sanitized.
2. Run the check: an Office file is also scanned inside.
3. Add `{"path", "sha256", "provenance"}` to `allowlisted_data_files`.

## Adding a protected token

Compute the digest locally and add only the digest:

```bash
python tools/privacy/privacy_check.py --digest "Surname"
```

Do not paste protected values into issues, CI logs or commit messages.

**Limitation.** A digest of a short, common token (a surname, a 6–7 digit
number) can be recovered by a dictionary search. The digest list is a strict
improvement over plaintext — and the values it protects are, until a history
purge, still in old commits — but it is not a secrecy mechanism.

## What the check does not do

- It cannot recognise every name or every location; it detects the configured
  patterns and the known tokens. Review remains necessary for new data files.
- It does not inspect Git history (see `HISTORY_PURGE_PLAN.md`).
- It does not scan PDFs or images for text; those must be reviewed and
  allowlisted by hash.
