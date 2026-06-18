#!/bin/sh
# Dispatch between the web service and the fhr CLI from a single image.
#
#   docker run IMG                      -> web service (default CMD=["web"])
#   docker run IMG web [uvicorn args]   -> web service
#   docker run IMG analyze FILE ...     -> fhr CLI subcommand
#   docker run IMG fhr --help           -> passthrough (run any command)
#   docker run IMG sh                   -> passthrough (debug shell)
#
# NOTE: portal-* subcommands drive a headed browser via agent-browser and are
# NOT supported in-container by design — run those natively (uvx/pipx). See docs.
set -e

case "${1:-web}" in
  web)
    shift || true
    exec uvicorn server.main:app \
      --host "${UVICORN_HOST:-0.0.0.0}" \
      --port "${UVICORN_PORT:-8000}" "$@"
    ;;
  analyze | export | import | reasons | \
  portal-fetch | portal-sync | portal-balances | portal-apply)
    exec fhr "$@"
    ;;
  *)
    # Passthrough: arbitrary command (fhr, python, sh, ...).
    exec "$@"
    ;;
esac
