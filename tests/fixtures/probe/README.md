# Recorded probe payloads

`healthy-envelope.txt` is the **verbatim output of `munki_fleet/probe_client.sh`** run on
**Cyrils-Mac-mini** (`RWJ57V9PW4`, macOS 26.6.2, Munki 7.3.0.5808) on 2026-09-13, captured with:

```sh
sh munki_fleet/probe_client.sh > healthy-envelope.txt
```

It is a real client's answer, not a payload written to match the parser. The report section is the
**XML plist Munki wrote, verbatim** — not JSON, because `plutil -convert json` cannot represent the
report's date objects and exits 0 while printing nothing, which silently lost the whole report the
first time this probe was written. It carries everything the probe has to summarise: the report's
`MachineInfo` block (serial, `arch`, OS version and `munki_version`), the resolved `ManifestName`,
`ItemsToInstall`, `Warnings`, and a
400-line log tail containing a complete run boundary
(`### Starting managedsoftwareupdate run ###` … `### Ending managedsoftwareupdate run ###`),
a manifest-resolution fallback (`Manifest Cyrils-Mac-mini.local/Cyrils-Mac-mini/RWJ57V9PW4 not
found`), and architecture rejections (`WARNING: Rejected item IBMAsperaConnect ... Our architecture
is arm64.`).

Real serial numbers and internal addresses are present because they are what the machine writes.
They are fleet identifiers, not secrets — `docs/role-matrix.csv` already records serials. A probe
payload contains no credentials by design, and the collector never sends any.

`recorded-run-records.jsonl` is the **verbatim store** written by the first live run on the same
day: one run record plus three observations — one machine observed, two unreachable with the
transport's own `Permission denied (publickey,password,keyboard-interactive)` message. The
unreachable and stale cases in the tests are replayed from it rather than invented, which is what
criterion 7 asks for; a machine that is unreachable produces no envelope at all, so there is nothing
else to record as a fixture.

Only the states a healthy real machine cannot be in at once stay synthetic: a machine without Munki
tools, and an unreadable report.
