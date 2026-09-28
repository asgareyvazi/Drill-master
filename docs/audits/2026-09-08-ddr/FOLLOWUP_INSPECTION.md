# Follow-up inspection (before implementation)

Baseline: eb8041de79d44f6ac6099ca84e569116af0d617c on arena/01a0801f-drill-master; clean checkout and FETCH_HEAD confirmed. Previous 56-file change set is in this commit and is not being redone.

Fresh baseline: 609 passed / 0 failed / 0 errors / 7 skipped, 616 collected. Native desktop startup fails on libGL.so.1. HTTP and HTTPS package mirror attempts failed; this is environmental, not an importer failure.

Inspection traced ExcelImportDialog -> DDRImportService -> ExcelIntelligence/canonical mapper -> DatabaseManager/domain adapters -> repositories -> w2/w3/w4/w6/w7/w8/w10 widget load/save -> existing TrajectoryCalculator/TrajectoryEngine -> plot_series -> pyqtgraph/Matplotlib and export paths. AST inventory enumerated 498 lifecycle/query methods in tabs, repositories, database and db_services. Collection-returning .all() helpers in database/repositories do not return None; remaining .all()+None candidates are side-effect-only widget loaders, not collection APIs.

Confirmed remaining defects:

1. Drilling Save All returns True when only one subtab saved; logistics/downhole aggregate boolean failures lose section diagnostics.
2. Survey persistence keys edits by MD, ignores ID, does not persist deletion, loses calculation metadata, and computes duplicate-MD checks across unrelated contexts. UI Add starts with fabricated zero measurements. Calculate button aborts every valid row on one invalid row.
3. Safety collection sync deletes existing children before replacing only valid edited rows; invalid source can delete stored data. Well-only safety header query and child queries use different report scopes. JSON text `null` violates collection_value's empty contract.
4. BHARepository bypasses named adapter; BHA/downhole/formation managers already retain hidden provenance (verified and preserved); empty tables are not saved, preventing deletion of the last row. BHA cumulative values can become stale after editing length. Formation Add equates TVD to MD without engineering evidence.
5. Mud's source unit is known, but ReviewItem normalized value is forcibly NULL. Non-PCF densities are converted to ppg and put into a PCF-native model/widget. Chemical provenance/missingness is linked by row ordinal and breaks when deleting/reordering rows. Non-composition mud NULLs can become widget defaults on save.
6. Scalar field detection recognizes only a small list of headers, so weather labels are treated as invalid measurements. A whitespace-only morning narrative becomes the literal string None. These reviews are not evidence of invalid weather measurements.
7. POB partial save emits success before reporting rejected rows; empty dates work in the database but actionable batch outcomes are not shared with Save All.

No fixes will invent azimuth, expand the chemical taxonomy without authoritative support, reinterpret projected northing/easting as latitude/longitude, or fabricate a second Golden workbook. The 65 existing ReviewItems are being individually audited against the source, not blanket-suppressed.
