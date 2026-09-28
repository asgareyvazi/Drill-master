"""Development/source-tree runner for DrillMaster.

Installed deployments should use the ``drillmaster`` console entry point.
This file remains for local source checkouts and deliberately does not print
passwords or exception details to the console.
"""

from __future__ import annotations

import logging
import sys

from app import DrillMasterApp

logger = logging.getLogger(__name__)


def main() -> int:
    try:
        application = DrillMasterApp(sys.argv)
        return application.exec()
    except Exception:
        logger.exception("Fatal DrillMaster runner error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
