"""Project known Munki identity facts to existing Bays pages."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from t6.notion.generated import BaysRow
from .identity import normalise_name


def writeback(client, data_source, inventory_path, rings_path, *, apply=False):
    inventory = json.loads(Path(inventory_path).read_text(encoding='utf-8'))
    rings = json.loads(Path(rings_path).read_text(encoding='utf-8'))
    pilot_entries = rings['pilots']
    pilots = {entry['munki_name'] for entry in pilot_entries if entry.get('munki_name')}
    complete_pilots = bool(pilot_entries) and all(entry.get('munki_name') for entry in pilot_entries)
    schema = client.retrieve_data_source(data_source).get('properties', {})
    for name, kind in {'Name': 'title', 'Hostname': 'rich_text', 'Serial Number': 'rich_text',
                       'Munki Manifest': 'rich_text', 'Ring': 'select'}.items():
        if schema.get(name, {}).get('type') != kind:
            raise ValueError(f'data source {data_source}: {name} must be {kind}')
    pages = client.query_data_source(data_source)
    def canonical(value):
        try:
            return uuid.UUID(value)
        except (ValueError, TypeError, AttributeError):
            return value
    for page in pages:
        parent = page.get('parent') or {}
        if (parent.get('type') != 'data_source_id' or
                canonical(parent.get('data_source_id')) != canonical(data_source)):
            raise ValueError(f'page {page.get("id")} is not in data source {data_source}')
    rows = [(page, BaysRow.from_page(page)) for page in pages]
    planned = []
    absent = [{'unix_hostname': item.get('probe_hostname'), 'computer_name': item.get('name'),
               'serial': item.get('serial')} for item in inventory.get('known_absent', [])
              if isinstance(item, dict)]
    for machine in inventory['machines'] + absent:
        candidates = (machine.get('unix_hostname'), machine.get('computer_name'))
        keys = {normalise_name(value) for value in candidates if value}
        matches = [(page, row) for page, row in rows if any(
            normalise_name(value) in keys for value in (row.hostname, row.name) if value)]
        planned.append((machine, matches))
    claimed = {}
    for _, matches in planned:
        for page, _ in matches:
            claimed[page['id']] = claimed.get(page['id'], 0) + 1
    for machine, matches in planned:
        name = machine.get('unix_hostname') or machine.get('computer_name') or '<unknown>'
        if len(matches) != 1 or claimed[matches[0][0]['id']] > 1:
            print(f"{name}: {'ambiguous' if matches else 'unmatched'}; skipped")
            continue
        page, row = matches[0]
        print(f"{name}: Bays {row.name!r} ({page['id']}) {page.get('url', '')}")
        manifest = machine.get('munki_name')
        desired = {'serial_number': machine.get('serial'), 'munki_manifest': manifest,
                   'ring': ('pilot' if manifest in pilots else 'production')
                   if manifest and complete_pilots else None}
        changes = {}
        for field, new in desired.items():
            old = getattr(row, field)
            label = BaysRow.notion_name(field)
            print(f"  {label}: {old!r} -> {new!r}" if new else
                  f"  {label}: {old!r} -> unknown (skipped)")
            if new and new != old:
                changes[field] = new
        if apply and changes:
            current = client.retrieve_page(page['id'])
            if (current.get('parent') != page.get('parent') or
                    current.get('archived') or current.get('in_trash') or
                    any(current.get('properties', {}).get(key) != page.get('properties', {}).get(key)
                        for key in ('Name', 'Hostname', 'Serial Number', 'Munki Manifest', 'Ring'))):
                print(f"{name}: Bays row changed since query; skipped")
                continue
            client.update_page(page['id'], {'properties': BaysRow.to_properties(**changes)})
    return 0
