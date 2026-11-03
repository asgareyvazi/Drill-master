# Survey references, depth datums and CRS — technical scope (M105)

Status: **implemented within the scope below; datum/CRS scope is an owner decision (open).**
UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.

This page states exactly which survey references Drill-master models, which it
transforms, and which it deliberately does not touch. Everything runs offline;
no value is fetched from a network service, magnetic model or GIS library.

## 1. What every survey revision records

| Field | Values | Rule |
|---|---|---|
| Depth unit | `m`, `ft` (converted to m on import; the source unit is kept) | declared, never guessed |
| Azimuth reference | `true`, `grid`, `magnetic` | declared; an unknown reference is never treated as true north |
| Depth datum | free label (for example `RKB`, `DF`, `GL`, `MSL`) | declared; never inferred |
| Station hash | SHA-256 of the canonical stations | verified on every read |
| Results hash (M105) | SHA-256 of the canonical derived results, versioned `M105 survey results hash v1` | new revisions only; older revisions show **NOT RECORDED** and are never backfilled |

Every engineering use of a revision (plan tie-in, azimuth transform, datum shift,
revision compare, trajectory compare) first calls `verify_for_use`. It refuses
the revision if the station hash fails, the recorded results hash fails, or a
recomputation of all nine result fields (md, inc, azi, tvd, north, east, vs, hd,
dls; per-field tolerances; azimuth compared on the circle) disagrees with the
stored results. A failed revision is reported. It is never repaired.

## 2. Transforms that are supported

Both transforms produce a **new** revision whose parent is the source. The source
revision is never changed. Parameters are explicit, carry their source, and are
stored in the new revision's provenance.

* **Azimuth reference** (M85, `M85 azimuth reference transform v1`): declination
  and/or grid convergence given by the user, each with its sign and source; a
  declination also needs the date it applies to.
* **Vertical depth-datum shift** (M105, `M105 vertical depth-datum shift v1`):
  * Inputs: the elevations of the source datum and the target datum, in metres,
    positive upwards, both measured from one stated reference (for example
    MSL), plus the source of the values.
  * Calculation: `offset = source elevation − target elevation`. Every station's
    MD and TVD becomes `depth − offset`. Inclination, azimuth, north and east are
    unchanged.
  * The shift is exact only when the hole above the first station is vertical,
    so a first station with non-zero inclination is refused.
  * A station that would end up above the new datum is refused. Stations are
    never dropped or clamped.
  * A missing elevation is never assumed to be zero, and a zero shift is
    refused.

## 3. What is NOT modelled (by design)

* Geodetic datums, ellipsoids, map projections, EPSG codes and coordinate
  reference system transformations. Grid convergence is never computed.
* Magnetic field models (WMM, IGRF, BGGM). Declination is never looked up online
  or estimated.
* Tidal, water-depth or air-gap corrections, and datum changes over time beyond
  the single explicit vertical shift above.
* Well-to-well comparison across different CRSs. The trajectory comparison
  needs the user to confirm that both wellheads share one CRS, and uses the
  recorded surface coordinates as given.

## 4. Plan references

* A directional plan saved from M105 onwards declares `azimuth_reference` and
  `depth_datum` in its inputs.
* When the plan is tied to a survey revision, the revision supplies these values
  and a contradicting declaration is refused.
* Plans saved earlier report **NOT DECLARED**. Nothing is assumed for them.
* Plan files declare their references in a leading comment row:

  ```
  # azimuth_reference=true; depth_datum=RKB
  MD (m),Inc (deg),Azi (deg)
  ...
  ```

* `key: value` is accepted as well. The plan CSV export writes the declaration.
* For plan-vs-actual, the comparison is **refused** when the plan and the survey
  revision declare different values. When either side does not declare a value,
  the comparison runs, but the result says which reference was not declared
  and that it was not verified.

## 5. Owner decisions (open)

Whether a full CRS/geodetic capability is in scope, which library would provide
it (licence review), and which magnetic model, if any, is acceptable remain
owner decisions. They are listed in the owner register of the product capability
matrix. Nothing in this page approves a datum, CRS or magnetic reference for
field use.
