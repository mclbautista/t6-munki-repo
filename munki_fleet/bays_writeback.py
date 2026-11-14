"""Project known Munki identity facts to Bays through `t6.fleet`.

This module only builds the facts (from this repo's inventory and rings data) and prints the
plan. Matching, the dry run, the write and the Bays field mapping are `t6.fleet`'s.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from t6.domain import Ring
from t6.fleet import Fleet, MachineFacts
from t6.fleet.bays import OBSERVED
from t6.notion.writes import Ambiguous, Rejected


def _instant(text, utc_if_naive):
    """A report or log time as an aware datetime. The report writes UTC without an offset; the
    log writes local time with one. Anything else is unknown, not guessed."""
    if not text:
        return None
    try:
        when = datetime.fromisoformat(str(text).strip())
    except ValueError:
        return None
    if when.tzinfo is None:
        if not utc_if_naive:
            return None
        when = when.replace(tzinfo=timezone.utc)
    return when


def observed_facts(entry):
    """The observed facts from one `probe.latest_per_machine` entry, and why any are missing.

    Only what the observation actually carries is returned (a partial observation writes only
    its own fields); `Last Check-in` is Munki's own last run time, not when the probe ran.
    """
    if entry is None:
        return {}, 'no observation'
    observation = entry['observation']
    if observation.get('outcome') == 'unobserved':
        return {}, f"unobserved ({observation.get('reason') or 'unknown reason'})"
    machine = observation.get('machine') or {}
    check = (observation.get('state') or {}).get('last_check') or {}
    last = (_instant(check.get('report_ended'), True) or _instant(check.get('log_run_ended'), False)
            or _instant(check.get('log_run_started'), False))
    facts = {'munki_client_version': machine.get('munki_version') or None,
             'os_version': machine.get('os_vers') or None, 'last_check_in': last,
             'observed_at': _instant(observation.get('observed_at'), False)}
    return facts, ('stale observation' if entry.get('stale') else None)


def machine_facts(inventory_path, rings_path, observations=None):
    inventory = json.loads(Path(inventory_path).read_text(encoding='utf-8'))
    rings = json.loads(Path(rings_path).read_text(encoding='utf-8'))
    pilot_entries = rings['pilots']
    pilots = {entry['munki_name'] for entry in pilot_entries if entry.get('munki_name')}
    complete_pilots = bool(pilot_entries) and all(entry.get('munki_name') for entry in pilot_entries)
    absent = [{'unix_hostname': item.get('probe_hostname'), 'computer_name': item.get('name'),
               'serial': item.get('serial'), '_known_absent': True}
              for item in inventory.get('known_absent', []) if isinstance(item, dict)]
    facts = []
    reasons = {}
    for machine in inventory['machines'] + absent:
        names = tuple(v for v in (machine.get('unix_hostname'), machine.get('computer_name')) if v)
        if not names:
            continue
        manifest = machine.get('munki_name')
        if machine.get('_known_absent') and machine.get('unix_hostname') in pilots:
            ring = Ring.PILOT
        elif manifest and complete_pilots:
            ring = Ring.PILOT if manifest in pilots else Ring.PRODUCTION
        else:
            ring = None
        serial = machine.get('serial')
        seen = next((entry for entry in (observations or {}).values()
                     if serial and serial in ((entry['observation'].get('machine') or {}).get('serial'),
                                              (entry['observation'].get('target') or {}).get('serial'))),
                    None)
        observed, why = observed_facts(seen) if observations is not None else ({}, None)
        facts.append(MachineFacts(names=names, serial_number=serial, munki_manifest=manifest,
                                  ring=ring, **observed))
        reasons[names[0]] = why
    return facts, reasons


def writeback(client, data_source, inventory_path, rings_path, *, apply=False, observations=None, now=None):
    facts, reasons = machine_facts(inventory_path, rings_path, observations)
    failed = False
    for result in Fleet(client, data_source).sync(facts, apply=apply, now=now):
        if result.status in ('unmatched', 'ambiguous'):
            print(f'{result.name}: {result.status}; skipped')
            continue
        print(f'{result.name}: Bays row {result.page_id}')
        for change in result.changes:
            print(f'  {change.fact}: {_show(change.old)} -> {_show(change.new)}')
        for fact in result.skipped:
            why = reasons.get(result.name) if fact in OBSERVED else None
            print(f'  {fact}: unknown (skipped{": " + why if why else ""})')
        if result.status == 'changed':
            print(f'{result.name}: Bays row changed since query; skipped')
        elif apply and result.changes:
            if isinstance(result.written, (Rejected, Ambiguous)):
                failed = True
                print(f'  NOT written: {result.written}')
            else:
                print('  written')
    return 1 if failed else 0


def _show(value):
    return repr(getattr(value, 'value', value))
