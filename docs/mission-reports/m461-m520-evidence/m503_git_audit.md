# M503: Git audit (M461–M520)

- **Branch:** `arena/72010272-drill-master`, the only branch written.
- **Other branches:** `drill-Master` is untouched at `e3fa42a3257e981d9bdf9d012c97919e3352a53a`; `ls-remote` shows no
  `main` on the remote. Nothing was merged.
- **Start:** the remote tip was `e5610729f9f3370341a8cb2a6fb8b7b28ec523f5`, the M401–M460 closure. It is an ancestor of
  every M461–M520 commit (`git merge-base --is-ancestor`).
- **History handling:** no force-push, amend, rebase, reset `--hard` or clean. Every push was a fast-forward and was
  verified with `git ls-remote`.

## Commits (oldest first)

| SHA | Content | CI |
|---|---|---|
| `3b4c29709986c630617ca685a4600d5a91b34757` | M461–M468: baseline, backlog, EOWR source-data sections | Source `45573236613`, Windows `45573236762`: both **cancelled** (superseded by the next push, concurrency group; kept) |
| `842c35c29496bc0fd265fa344706f300754df204` | M469–M472 (U2): citation passages | Source `45575011827`, Windows `45575011856`: both **cancelled** (superseded; kept) |
| `20c05d02a4af93883daccf4000601a92f727c2cf` | M473–M474 (U3): historical mutation re-run, anchor pin | Source `45575372817`, Windows `45575372898`: both **cancelled** (superseded; kept) |
| `f7075a0d28e2fc73114371384ac954574b72c33d` | M475–M485: robust drill-off v2, Erge NOT VERIFIED, owner packages | Windows `45578429709` **SUCCESS** (31m12s). Source `45578429792`: see the report, §1. |
| `44d3fb4cba276c928c8b90db8e6593fdb9d8f5f5` | M488–M492: consistency tests, plain-text dialog summaries | Pushed together with the M494–M503 documents. The CI of the pushed tip is given in the report and the hand-over. |

Every commit carries the label `PARTIAL - UNSIGNED - NOT RELEASE-APPROVED - NOT FIELD-ACCEPTED`. Files were staged by
explicit path; `git commit -a` was never used.

## Unchanged by rule

- `docs/mission-reports/M401_M460_INTEGRATED_ENGINEERING_DELIVERY_REPORT.md`
- the M460 catalogue and roadmap
- `requirements-lock.txt` (sha256 `697124ea…edcfadd`)
- packaging
- the CI workflows, including the 60 min timeout

The first three are historical records that must stay as they are. The lock and packaging are unchanged because no
owner decision (P1–P19) approved a change, and the workflows because D88 (keep the 60 min timeout and the current
workflow) is unresolved.
