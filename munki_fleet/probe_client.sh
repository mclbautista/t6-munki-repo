#!/bin/sh
# Read-only Munki client state probe. No root, no writes, no network beyond the local files.
#
# Emits a line-oriented envelope so the collector never has to guess what it did not receive:
# a missing file and an empty file are different answers, and both are distinguishable from a
# machine that could not be reached at all (which produces no envelope).
#
#   munki-fleet-probe/1
#   munki_tools=yes|no
#   report_present=yes|no
#   report_mtime=<epoch>|-
#   log_present=yes|no
#   log_mtime=<epoch>|-
#   <<<REPORT>>>
#   <the report as JSON, or empty>
#   <<<LOG>>>
#   <the tail of the Munki log, raw>
set -u
REPORT="/Library/Managed Installs/ManagedInstallReport.plist"
LOG="/Library/Managed Installs/Logs/ManagedSoftwareUpdate.log"
TAIL_LINES=400

mtime_of() {
  [ -f "$1" ] && stat -f %m "$1" 2>/dev/null || printf '-'
}

printf 'munki-fleet-probe/1\n'
if [ -d /usr/local/munki ]; then printf 'munki_tools=yes\n'; else printf 'munki_tools=no\n'; fi

if [ -f "$REPORT" ]; then
  printf 'report_present=yes\n'
  printf 'report_mtime=%s\n' "$(mtime_of "$REPORT")"
else
  printf 'report_present=no\n'
  printf 'report_mtime=-\n'
fi

if [ -f "$LOG" ]; then
  printf 'log_present=yes\n'
  printf 'log_mtime=%s\n' "$(mtime_of "$LOG")"
else
  printf 'log_present=no\n'
  printf 'log_mtime=-\n'
fi

printf '<<<REPORT>>>\n'
# The report is emitted verbatim, as the XML plist Munki writes. `plutil -convert json` refuses a
# plist containing date objects - and exits 0 while printing nothing - which silently lost the whole
# report the first time this probe was written. Verbatim output cannot fail that way, and the
# collector parses the same plist format Munki wrote.
if [ -f "$REPORT" ]; then
  cat "$REPORT" 2>/dev/null || printf ''
fi
printf '\n'

printf '<<<LOG>>>\n'
if [ -f "$LOG" ]; then
  tail -n "$TAIL_LINES" "$LOG" 2>/dev/null || printf ''
fi
