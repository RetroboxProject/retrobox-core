"""``python3 -m retrobox.startup``: start Retrobox (the frontend session)."""

import sys

try:
    from .run import main
except ModuleNotFoundError as error:
    if (error.name or "retrobox").startswith("retrobox"):
        raise
    # a Python dependency is missing: say which, rather than a traceback
    print(f"[ERR ] Retrobox can't start, a Python module is missing ({error.name}). "
          "Run 'retrobox --doctor' to see what to install.", file=sys.stderr)
    sys.exit(1)

sys.exit(main())
