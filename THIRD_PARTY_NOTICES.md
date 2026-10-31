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
