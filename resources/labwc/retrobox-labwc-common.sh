#!/usr/bin/env bash
# Shared constants and helpers for the labwc gaming-session scripts.
# This file is meant to be sourced, never executed directly.
#
# No path is hardcoded: RETROBOX_ROOT is derived from this file's own
# real location (resources/labwc/ -> repo root), so the whole set of
# scripts works from any checkout. It can still be overridden by
# exporting RETROBOX_ROOT beforehand.
#
# Safe to source more than once and from an interactive shell
# (~/.bashrc.d): no "readonly", no "exit", every helper returns.

if [[ -n "${RETROBOX_LABWC_COMMON_SOURCED:-}" ]]; then
  return 0 2>/dev/null || true
fi
RETROBOX_LABWC_COMMON_SOURCED=1

if [[ -z "${RETROBOX_ROOT:-}" || ! -d "${RETROBOX_ROOT:-}" ]]; then
  RETROBOX_LABWC_DIR="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" &>/dev/null && pwd -P)"
  RETROBOX_ROOT="$(cd -- "${RETROBOX_LABWC_DIR}/../.." &>/dev/null && pwd -P)"
else
  RETROBOX_LABWC_DIR="${RETROBOX_ROOT}/resources/labwc"
fi

RETROBOX_TTYSAVE="${RETROBOX_TTYSAVE:-/tmp/retrobox-ttysave}"
# Where to return to when no origin TTY was saved (session started by
# hand on the gaming TTY instead of through retrobox-enter-tty).
RETROBOX_FALLBACK_TTY="${RETROBOX_FALLBACK_TTY:-1}"

# Prints the value of "key" under "[section]" in an INI file.
# Returns 1 (prints nothing) if the file, section or key is missing.
read_ini_value() {
  local file="$1"
  local section="$2"
  local key="$3"

  [[ -r "${file}" ]] || return 1

  awk -F '=' -v section="[${section}]" -v key="${key}" '
    $0 == section { in_section = 1; next }
    /^\[/         { in_section = 0 }
    in_section && $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
      value = $2
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      print value
      found = 1
      exit
    }
    END { exit !found }
  ' "${file}"
}

# True if $1 is a valid VT number (1-12).
is_valid_tty() {
  [[ "${1:-}" =~ ^[0-9]+$ ]] && ((10#${1} >= 1 && 10#${1} <= 12))
}

# Prints the configured gaming TTY (retrobox.ini, [advanced] labwc_tty).
# Returns 1 with a message on stderr if it is missing or out of range;
# callers decide what to do (scripts exit, ~/.bashrc.d just gives up).
get_gaming_tty() {
  local tty

  # retrobox.ini is layered (/etc/retrobox, ~/.config/retrobox, each with its
  # retrobox.ini.d/), so ask the shared path library for the merged value.
  # Kept lazy: this file is sourced by every interactive shell through
  # ~/.bashrc.d, most of which never get here.
  local py="${RETROBOX_PYTHON:-}"
  if [[ -z "${py}" ]]; then
    if [[ -x "${RETROBOX_ROOT}/venv/bin/python3" ]]; then py="${RETROBOX_ROOT}/venv/bin/python3"; else py="python3"; fi
  fi
  tty="$(cd "${RETROBOX_ROOT}" && "${py}" -W ignore -m runtime.paths --get advanced.labwc_tty 2>/dev/null)"
  if [[ -z "${tty}" ]]; then
    echo "error: missing [advanced] labwc_tty in retrobox.ini (~/.config/retrobox/retrobox.ini or /etc/retrobox/retrobox.ini)" >&2
    return 1
  fi

  if ! is_valid_tty "${tty}"; then
    echo "error: labwc_tty must be an integer between 1 and 12, got '${tty}'" >&2
    return 1
  fi

  printf '%s\n' "${tty}"
}

# Prints the VT number this process is attached to, or nothing.
get_current_tty() {
  local dev
  dev="$(tty 2>/dev/null)" || return 1
  [[ "${dev}" =~ ^/dev/tty([0-9]+)$ ]] || return 1
  printf '%s\n' "${BASH_REMATCH[1]}"
}
