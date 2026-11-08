# Third-party notices

Drill-master contains **no copied third-party source code** from the repositories reviewed in M52
(see `docs/engineering/OPEN_SOURCE_ADOPTION_REGISTER.md`). The entries below credit the projects
whose documented methods were independently re-implemented. Runtime dependencies and their
licences are listed in `pyproject.toml` / `requirements-lock.txt`; M52 added none.

## cement-calc (method reference)

* Upstream: https://github.com/wjwhitmire/cement-calc at `2a6145007f32e45e72d33099e1f959896bd7d92c`
* Used for: the balanced-plug method (equal column heights inside and outside the pipe, spacer
  behind = spacer ahead x pipe capacity / annular capacity, under-displacement) behind
  `CementEngine.balanced_plug` in `core/engineering/engines/cement.py`.
* Re-implemented independently and tested against hand-calculated references
  (`tests/test_m52_balanced_plug.py`); no upstream code or test vectors were copied.
* Licence text of the upstream project:

```
MIT License

Copyright (c) 2026 Will Whitmire

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## welleng (method reference)

* Upstream: https://github.com/jonnymaserati/welleng at `d29adf906b38e08e3f8b5a10409305bb1c058992`,
  Apache License 2.0.
* Used for: ideas only (minimum-curvature interpolation along the arc and continuous closest
  approach) behind `core/trajectory_compare.py`. No code, data or NOTICE material was copied;
  welleng is not a dependency. Its ISCWSA error models are not used (owner review required).

<!-- BEGIN GENERATED: bundled runtime licences (tools/quality/dependency_audit.py --write) -->

## Bundled runtime libraries (generated)

Every distribution pinned in `requirements-lock.txt` is bundled into the Windows application. The licence below is the one its installed metadata declares; the bundle carries each distribution's metadata folder (`*.dist-info`, with the licence files its wheel includes) next to this file. Copyleft entries are owner gates — shipping a licence text does not by itself meet AGPL or LGPL distribution obligations (source offer, relinking); no legal approval is implied.

| Distribution | Version | Licence (installed metadata) | Class | Owner gate |
|---|---|---|---|---|
| bcrypt | 4.2.1 | Apache-2.0 [Apache Software License] | permissive | — |
| contourpy | 1.3.3 | BSD 3-Clause License [BSD License] | permissive | — |
| cycler | 0.12.1 | Copyright (c) 2015, matplotlib project [BSD License] | permissive | — |
| et_xmlfile | 2.0.0 | MIT [MIT License] | permissive | — |
| fonttools | 4.64.0 | MIT | permissive | — |
| greenlet | 3.5.5 | MIT AND PSF-2.0 | permissive | — |
| kiwisolver | 1.5.1 | BSD License | permissive | — |
| matplotlib | 3.9.3 | License agreement for matplotlib versions 1.3.0 and later [Python Software Foundation License] | permissive | — |
| numpy | 2.1.3 | Copyright (c) 2005-2024, NumPy Developers. [BSD License] | permissive | — |
| openpyxl | 3.1.5 | MIT [MIT License] | permissive | — |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | permissive | — |
| pandas | 2.2.3 | BSD 3-Clause License [BSD License] | permissive | — |
| pillow | 12.3.0 | MIT-CMU | permissive | — |
| PyMuPDF | 1.24.14 | GNU AFFERO GPL 3.0 | strong copyleft (AGPL) | PyMuPDF (AGPL-3.0) |
| pyparsing | 3.3.2 | MIT | permissive | — |
| pyqtgraph | 0.13.7 | MIT [MIT License] | permissive | — |
| PySide6 | 6.8.1.1 | LGPL [GNU Library or Lesser General Public License (LGPL); Other/Proprietary License] | weak copyleft (LGPL) | Qt for Python (LGPL-3.0) distribution obligations |
| PySide6_Addons | 6.8.1.1 | LGPL [GNU Library or Lesser General Public License (LGPL); Other/Proprietary License] | weak copyleft (LGPL) | Qt for Python (LGPL-3.0) distribution obligations |
| PySide6_Essentials | 6.8.1.1 | LGPL [GNU Library or Lesser General Public License (LGPL); Other/Proprietary License] | weak copyleft (LGPL) | Qt for Python (LGPL-3.0) distribution obligations |
| python-dateutil | 2.9.0.post0 | Dual License [BSD License; Apache Software License] | permissive | — |
| pytz | 2026.3.post1 | MIT [MIT License] | permissive | — |
| shiboken6 | 6.8.1.1 | LGPL [GNU Library or Lesser General Public License (LGPL); Other/Proprietary License] | weak copyleft (LGPL) | Qt for Python (LGPL-3.0) distribution obligations |
| six | 1.17.0 | MIT [MIT License] | permissive | — |
| SQLAlchemy | 2.0.36 | MIT [MIT License] | permissive | — |
| typing_extensions | 4.16.0 | PSF-2.0 | permissive | — |
| tzdata | 2026.3 | Apache-2.0 | permissive | — |

<!-- END GENERATED: bundled runtime licences -->
