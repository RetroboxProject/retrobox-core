# Retrobox logging helpers: colored [INFO] / [ OK ] / [ERR ] / [WARN] tags.
#
# Usage (source this file, don't execute it):
#   source "${TOOLS_DIR}/lib/log.sh"
#   log_info "message"
#   log_ok   "message"
#   log_warn "message"
#   log_err  "message"      # goes to stderr
#
# Scheme: the tag (including brackets) is colored per level, the rest of the
# line is white, and the whole line is bold. Colors are skipped automatically
# when stdout isn't a terminal, or when NO_COLOR is set (see no-color.org).

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    _LOG_BOLD=$'\033[1m'
    _LOG_RESET=$'\033[0m'
    _LOG_WHITE=$'\033[97m'
    _LOG_CYAN=$'\033[36m'
    _LOG_RED=$'\033[31m'
    _LOG_GREEN=$'\033[32m'
    _LOG_YELLOW=$'\033[33m'
else
    _LOG_BOLD=""
    _LOG_RESET=""
    _LOG_WHITE=""
    _LOG_CYAN=""
    _LOG_RED=""
    _LOG_GREEN=""
    _LOG_YELLOW=""
fi

# $1 = tag color, $2 = 4-char tag, $3.. = message
_log() {
    local color="$1" tag="$2"
    shift 2
    printf '%s%s[%s]%s %s%s\n' \
        "${_LOG_BOLD}" "${color}" "${tag}" "${_LOG_WHITE}" "$*" "${_LOG_RESET}"
}

log_info() { _log "${_LOG_CYAN}"   "INFO" "$@"; }
log_ok()   { _log "${_LOG_GREEN}"  " OK " "$@"; }
log_warn() { _log "${_LOG_YELLOW}" "WARN" "$@"; }
log_err()  { _log "${_LOG_RED}"    "ERR " "$@" >&2; }