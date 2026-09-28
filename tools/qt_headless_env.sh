#!/usr/bin/env bash
# DrillMaster headless-Qt test environment bootstrap (sandbox without libGL).
#
# The sandbox cannot install system packages (apt blocked), and PySide6's
# offscreen platform still requires libGL.so.1 / libEGL.so.1 /
# libxkbcommon.so.0 / libdbus-1.so.3 to be *loadable* (DT_NEEDED on
# libQt6Gui.so.6 / libQt6DBus.so.6).
#
# These are minimal no-op stubs: every function returns 0/NULL, i.e. the
# honest "capability absent" answer. Offscreen raster rendering never calls
# GL/EGL/xkb/dbus entry points, so widgets, fonts, dialogs and raster paint
# all work. Anything that genuinely requires OpenGL would NOT work here and
# must be treated as an environment limitation, not a code defect.
#
# Usage:  source tools/qt_headless_env.sh   (from the repo root, venv at .venv)
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STUB_DIR="${QT_STUB_DIR:-/home/user/qt-libs}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

collect_undefined() {  # $1=soname  -> symbol list on stdout
    local soname="$1" f
    for f in $(find "$REPO/.venv/lib" -name "*.so*"); do
        if readelf -d "$f" 2>/dev/null | grep -q "Shared library: \[$soname\]"; then
            nm -D --undefined-only "$f" 2>/dev/null | awk '{print $NF}' | sed 's/@.*//'
        fi
    done
}

build_stub() {  # $1=soname  $2=symbol-grep  $3=version-script (optional)
    local soname="$1" pat="$2" mapfile="$3"
    collect_undefined "$soname" | grep -E "$pat" | sort -u > "$WORK/syms"
    [ -s "$WORK/syms" ] || return 0
    { echo "/* no-op stub for headless offscreen Qt: $soname */"
      while read -r s; do echo "long $s(void) { return 0; }"; done < "$WORK/syms"
    } > "$WORK/stub.c"
    local extra=()
    [ -n "$mapfile" ] && extra=(-Wl,--version-script="$WORK/$mapfile")
    gcc -shared -fPIC -o "$STUB_DIR/$soname" "$WORK/stub.c" \
        -Wl,-soname,"$soname" "${extra[@]}"
}

mkdir -p "$STUB_DIR"
cat > "$WORK/xkb.map" <<'EOF'
V_0.5.0 {
  global:
    xkb_*;
  local:
    *;
};
EOF
cat > "$WORK/dbus.map" <<'EOF'
LIBDBUS_1_3 {
  global:
    dbus_*;
  local:
    *;
};
EOF

build_stub libGL.so.1        '^gl'      ''
build_stub libEGL.so.1       '^egl'     ''
build_stub libxkbcommon.so.0 '^xkb'     xkb.map
build_stub libdbus-1.so.3    '^dbus'    dbus.map

export QT_STUB_DIR="$STUB_DIR"
export LD_LIBRARY_PATH="$STUB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_QPA_PLATFORM=offscreen
echo "headless Qt environment ready (stubs: $STUB_DIR, platform: offscreen)"
