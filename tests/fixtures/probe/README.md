# Recorded probe payloads

`healthy-envelope.txt` is the **verbatim output of `munki_fleet/probe_client.sh`** run on
**Cyrils-Mac-mini** (`RWJ57V9PW4`, macOS 26.6.2, Munki 7.3.0.5808) on 2026-09-13, captured with:

```sh
sh munki_fleet/probe_client.sh > healthy-envelope.txt
```

It is a real client's answer, not a payload written to match the parser. It carries everything the
probe has to summarise: the report as JSON (its `MachineInfo` block includes the serial, `arch`, OS
version and `munki_version`), the resolved `ManifestName`, `ItemsToInstall`, `Warnings`, and a
400-line log tail containing a complete run boundary
(`### Starting managedsoftwareupdate run ###` … `### Ending managedsoftwareupdate run ###`),
a manifest-resolution fallback (`Manifest Cyrils-Mac-mini.local/Cyrils-Mac-mini/RWJ57V9PW4 not
found`), and architecture rejections (`WARNING: Rejected item IBMAsperaConnect ... Our architecture
is arm64.`).

Real serial numbers and internal addresses are present because they are what the machine writes.
They are fleet identifiers, not secrets — `docs/role-matrix.csv` already records serials. A probe
payload contains no credentials by design, and the collector never sends any.

The other cases the tests need are synthetic, because they are states a healthy machine cannot be
in at the same time: an unreachable machine (no envelope at all), a machine without Munki tools, and
an unreadable report.
