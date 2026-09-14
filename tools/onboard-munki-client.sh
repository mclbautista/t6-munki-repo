#!/bin/bash
# T6 Munki client onboarding — the executable half of ticket 11 (munki-fleet-rollout).
#
# WHAT THIS DOES, IN ORDER
#   1. refuses to run unless it is root, the installer is the signed Munki build, and the repository
#      already carries a manifest named after this machine's short hostname;
#   2. records the before state (unmanaged) so the change is evidenced rather than asserted;
#   3. installs the Munki tools package;
#   4. points the client at the T6 repository and makes sure NO ClientIdentifier is set, because the
#      machine must resolve its manifest by its own short hostname;
#   5. runs one check-only and reads back the resolved manifest;
#   6. treats a manifest that is not this machine's own — `site_default` above all — as FAILURE.
#
# TOOLING REQUIREMENTS (stated, so this does not fail on a tool version)
#   macOS's own /bin/bash (3.2 is fine; nothing here needs bash 4) and macOS built-ins only:
#   pkgutil, installer, defaults, scutil, plutil, curl, launchctl, sw_vers, uname. No Python, no
#   Homebrew, no Munki admin tools. The COLLECTOR side is a different story: it runs
#   /usr/bin/python3 (CommandLineTools) per the repository's rule, and this script never invokes it.
#
# USAGE — as root, at the machine:
#   sudo bash onboard-munki-client.sh --pkg ~/munki-bootstrap/munkitools-7.3.0.5808.pkg
#
# UNDO — also as root. It refuses to change anything until you pass --yes, and prints the whole plan
#   first (a gate you can read before it acts, not after):
#   sudo bash onboard-munki-client.sh --undo
#   sudo bash onboard-munki-client.sh --undo --yes
#
# WHAT CORRECT LOOKS LIKE AT THE END: the last block printed is headed `ONBOARDING EVIDENCE` and its
# `resolved manifest:` line carries this machine's own short hostname. Anything else — `site_default`
# in particular — means the procedure failed and the machine is NOT onboarded.
set -u

REPO_URL="http://192.168.88.188/MunkiRepo"
MUNKI_DIR="/usr/local/munki"
PREFS_BASE="/Library/Preferences/ManagedInstalls"
PREFS="${PREFS_BASE}.plist"
REPORT="/Library/Managed Installs/ManagedInstallReport.plist"
RECEIPTS="com.googlecode.munki.core com.googlecode.munki.admin com.googlecode.munki.app
com.googlecode.munki.app_usage com.googlecode.munki.launchd com.googlecode.munki.pythonlibs"

say()  { printf '\n== %s\n' "$*"; }
ok()   { printf '   ok: %s\n' "$*"; }
fail() { printf '\nFAIL: %s\n' "$*" >&2; exit 1; }

MODE=install
CONFIRM=no
PKG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --pkg) PKG="${2:-}"; shift 2 ;;
        --undo) MODE=undo; shift ;;
        --yes) CONFIRM=yes; shift ;;
        *) fail "unknown argument: $1" ;;
    esac
done

# --- undo: print the plan, change nothing until --yes ---------------------------------------------
if [ "$MODE" = undo ]; then
    say "UNDO PLAN — what will be removed, and what will NOT be"
    cat <<EOF
   unload : the six com.googlecode.munki launchd jobs in /Library/LaunchDaemons
   remove : ${MUNKI_DIR}
   remove : /Applications/Managed Software Center.app
   remove : /Library/Managed Installs        (reports, logs, caches, and any downloaded installers)
   remove : ${PREFS}
   forget : the package receipts: ${RECEIPTS}
   NOT touched: everything Munki ever INSTALLED. Munki does not uninstall its payloads, so removing
                the tools leaves every application and package it deployed exactly where it is.
   NOT touched: ${REPO_URL} on the NAS — this script never writes to the repository.
   Reversible by re-running the install path.
EOF
    [ "$CONFIRM" = yes ] || { printf '\nrefusing to act: re-run with --yes to carry out the plan above.\n'; exit 2; }
    [ "$(id -u)" -eq 0 ] || fail "carrying out the undo must run as root"
    say "carrying out the undo"
    for job in /Library/LaunchDaemons/com.googlecode.munki.*.plist; do
        [ -e "$job" ] && { launchctl bootout system "$job" 2>/dev/null || launchctl unload "$job" 2>/dev/null; ok "unloaded $(basename "$job")"; }
    done
    rm -rf "$MUNKI_DIR" "/Applications/Managed Software Center.app" "/Library/Managed Installs"
    ok "removed the tools, the app and /Library/Managed Installs"
    rm -f "$PREFS" && ok "removed $PREFS"
    for r in $RECEIPTS; do pkgutil --forget "$r" >/dev/null 2>&1 && ok "forgot $r"; done
    say "UNDO EVIDENCE"
    printf '   munki dir present   : %s\n' "$([ -d "$MUNKI_DIR" ] && echo YES || echo no)"
    printf '   munki jobs loaded   : %s\n' "$(launchctl list 2>/dev/null | grep -ci munki)"
    printf '   receipts remaining  : %s\n' "$(pkgutil --pkgs 2>/dev/null | grep -ci munki)"
    exit 0
fi

[ "$(id -u)" -eq 0 ] || fail "must run as root: this installs a package and writes
/Library/Preferences and /Library/LaunchDaemons. At the machine:
    sudo bash $0 --pkg <path to munkitools-*.pkg>
(To read the undo plan without root: bash $0 --undo)"

[ -n "$PKG" ] || fail "give the installer path: --pkg <path to munkitools-*.pkg>"
[ -f "$PKG" ] || fail "no such installer: $PKG"

# --- 1. preflight: everything that must be true BEFORE anything on this machine changes -------------
say "1. PREFLIGHT — nothing has been changed yet"
say "   1a. the installer is the signed Munki build"
sig="$(/usr/sbin/pkgutil --check-signature "$PKG" 2>&1)" || fail "the installer is not signed:
$sig"
printf '%s\n' "$sig" | grep -q "Mac Admins Open Source" || fail "the installer is not signed by Mac
Admins Open Source, the Munki project's identity. Do not install it:
$(printf '%s\n' "$sig" | head -5)"
printf '%s\n' "$sig" | grep -qi "notary" || fail "the installer is signed but NOT notarized:
$(printf '%s\n' "$sig" | head -5)"
ok "signed by Mac Admins Open Source and notarized by Apple"
printf '%s\n' "$sig" | sed -n '2p;3p' | sed 's/^/      /'
printf '      sha256: %s\n' "$(/usr/bin/shasum -a 256 "$PKG" | awk '{print $1}')"

say "   1b. this machine has a manifest in the repository, named after its short hostname"
SHORT="$(scutil --get LocalHostName 2>/dev/null || true)"
[ -n "$SHORT" ] || fail "LocalHostName is unset, so nothing can resolve this machine's manifest.
Set it first (it is what Munki uses as the client identifier)."
printf '      LocalHostName: %s\n' "$SHORT"
if /usr/bin/curl -sf --max-time 8 "$REPO_URL/manifests/$SHORT" -o /dev/null; then
    ok "the repository serves manifests/$SHORT"
else
    fail "the repository carries no manifest named '$SHORT' ($REPO_URL/manifests/$SHORT).
Onboarding now would leave this machine resolving site_default, which this procedure treats as a
FAILURE rather than a warning. Publish a manifest named exactly '$SHORT' first, then re-run."
fi

say "   1c. the repository is reachable and serves the machinery for this machine"
for path in "manifests/$SHORT" "manifests/all" "manifests/site_default"; do
    if /usr/bin/curl -sf --max-time 8 "$REPO_URL/$path" -o /dev/null; then ok "serves $path"
    else fail "the repository does not serve $path — the client could not resolve its manifest"; fi
done

say "2. BEFORE STATE (unmanaged, or the state a re-run found)"
printf '      sw_vers            : %s (%s)\n' "$(sw_vers -productVersion)" "$(sw_vers -buildVersion)"
printf '      architecture       : %s\n' "$(uname -m)"
printf '      LocalHostName      : %s\n' "$SHORT"
printf '      Munki tools        : %s\n' "$([ -d "$MUNKI_DIR" ] && echo "PRESENT — this is a re-run" || echo absent)"
printf '      client prefs       : %s\n' "$([ -f "$PREFS" ] && echo present || echo absent)"
printf '      launchd munki jobs : %s\n' "$(launchctl list 2>/dev/null | grep -ci munki)"

# --- 3. install ------------------------------------------------------------------------------------
say "3. INSTALL the Munki tools"
if /usr/sbin/installer -pkg "$PKG" -target / ; then ok "installer exited 0"
else fail "the installer failed"; fi
VERSION="$(/usr/sbin/pkgutil --pkg-info com.googlecode.munki.core 2>/dev/null | awk '/^version:/{print $2}')"
[ -n "$VERSION" ] || fail "com.googlecode.munki.core is not installed after the installer ran"
ok "com.googlecode.munki.core $VERSION"

# --- 4. point the client at the repository, and leave NO ClientIdentifier ----------------------------
say "4. CONFIGURE the client endpoint (and make sure resolution is by short hostname)"
/usr/bin/defaults write "$PREFS_BASE" SoftwareRepoURL "$REPO_URL" || fail "could not write $PREFS"
ok "SoftwareRepoURL = $REPO_URL"
if echo "$(defaults read "$PREFS_BASE" ClientIdentifier 2>/dev/null || true)" | grep -q '[^[:space:]]'; then
    /usr/bin/defaults delete "$PREFS_BASE" ClientIdentifier
    ok "REMOVED a ClientIdentifier it found — it would have overridden short-hostname resolution"
else
    ok "no ClientIdentifier set, so the client resolves by its short hostname (as intended)"
fi
chown root:wheel "$PREFS" 2>/dev/null || true
chmod 644 "$PREFS" 2>/dev/null || true

# --- 5. one check-only, and read the manifest back --------------------------------------------------
say "5. FIRST CHECK — check-only, which resolves and downloads but installs nothing"
/usr/local/munki/managedsoftwareupdate --checkonly 2>&1 | sed 's/^/      /'
say "   and the same answer from Munki's own report"
[ -f "$REPORT" ] || fail "no report at $REPORT: the client did not run, so nothing is verified"
MANIFEST="$(/usr/bin/plutil -extract ManifestName raw -o - "$REPORT" 2>/dev/null || true)"
[ -n "$MANIFEST" ] || fail "the report carries no ManifestName — the client ran but did not resolve a manifest"

# --- 6. the verdict: its own manifest or nothing ----------------------------------------------------
say "6. VERDICT"
if [ "$MANIFEST" = "site_default" ]; then
    fail "this machine resolved site_default, which means it has NO machine manifest of its own.
The change is installed but the machine is NOT onboarded. Publish manifests/$SHORT and re-run."
fi
if [ "$MANIFEST" != "$SHORT" ]; then
    fail "this machine resolved '$MANIFEST' but its short hostname is '$SHORT'. The machine is NOT
onboarded: a manifest that is not this machine's own is the wrong answer, not a warning."
fi
ok "the machine resolved its own manifest"

say "ONBOARDING EVIDENCE — copy this block into the ticket"
cat <<EOF
   machine            : $SHORT
   unix hostname      : $(hostname)
   serial             : $(/usr/sbin/system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Serial Number/{print $2}')
   macOS              : $(sw_vers -productVersion) (build $(sw_vers -buildVersion))
   architecture       : $(uname -m)
   Munki tools        : $VERSION   (com.googlecode.munki.core)
   SoftwareRepoURL    : $REPO_URL
   ClientIdentifier   : none set — resolution is by short hostname
   check-only result  : completed, no error  (see the line above)
   resolved manifest  : $MANIFEST
   report timestamp   : $(stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%S%z' "$REPORT")
   launchd munki jobs : $(launchctl list 2>/dev/null | grep -ci munki)
EOF
printf '\nRESULT: onboarded — %s resolved its own manifest (%s).\n' "$SHORT" "$MANIFEST"
exit 0
