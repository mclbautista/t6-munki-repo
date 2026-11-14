import json
import os

import pytest

from t6.fleet import Fleet
from t6.notion.testing import FakeNotion, title, rich_text, select

from munki_fleet.cli import Deps, main


def bay(fake, page_id):
    """One Bays row as a t6 Machine, read through t6.fleet."""
    with fake.client() as client:
        return next(m for m in Fleet(client, 'bays').machines() if m.page_id == page_id)


def setup_case(tmp_path, machines=None, pilots=None):
    inventory = tmp_path / 'machines.json'
    rings = tmp_path / 'rings.json'
    inventory.write_text(json.dumps({'machines': machines if machines is not None else [
        {'unix_hostname': 'Bay-1', 'computer_name': 'Bay 1', 'serial': 'S1',
         'munki_name': 'Bay-1'}]}))
    rings.write_text(json.dumps({'pilots': pilots if pilots is not None else [{'munki_name': 'Bay-1'}]}))
    fake = FakeNotion()
    fake.add_snapshot_data_source('bays', 'bays')
    return fake, inventory, rings


def add_bay(fake, name='Bay 1', host='Bay-1', serial='old', manifest='old-manifest', ring='production'):
    return fake.add_page('bays', {'Name': title(name), 'Hostname': rich_text(host),
                                 'Serial Number': rich_text(serial),
                                 'Munki Manifest': rich_text(manifest), 'Ring': select(ring)})


def run(fake, inventory, rings, *extra):
    return main(['bays-writeback', '--inventory', str(inventory), '--rings', str(rings),
                 '--data-source', 'bays', *extra], deps=Deps(notion_client_factory=fake.client))


@pytest.mark.xfail(strict=True, reason='t6.fleet has no schema pre-check; gap to raise in t6-core')
def test_missing_write_field_schema_refuses_before_any_updates(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path)
    add_bay(fake)
    fake.remove_property('bays', 'Serial Number')
    assert run(fake, inventory, rings, '--apply') != 0
    assert 'Serial Number' in capsys.readouterr().err
    assert not [r for r in fake.requests if r.method == 'PATCH']


def test_changed_live_identity_after_query_is_not_written(tmp_path):
    import httpx
    fake, inventory, rings = setup_case(tmp_path)
    page = add_bay(fake)
    original = fake._handle

    def changed_after_query(request):
        response = original(request)
        if request.url.path.endswith('/query'):
            fake._pages[page['id']]['properties']['Hostname'] = rich_text('different')
            fake._pages[page['id']]['properties']['Name'] = title('different')
        return response

    fake.transport = httpx.MockTransport(changed_after_query)
    run(fake, inventory, rings, '--apply')
    assert not [r for r in fake.requests if r.method == 'PATCH']


@pytest.mark.xfail(strict=True, reason='t6.fleet does not check a page belongs to the data source; gap to raise in t6-core')
def test_wrong_data_source_page_is_not_updated(tmp_path):
    import httpx
    fake, inventory, rings = setup_case(tmp_path)
    page = add_bay(fake)
    original = fake._handle

    def foreign_page(request):
        response = original(request)
        if request.url.path.endswith('/query'):
            body = response.json()
            body['results'][0]['parent']['data_source_id'] = 'b-ays'
            return httpx.Response(200, json=body)
        if request.method == 'GET' and request.url.path.endswith('/' + page['id']):
            body = response.json()
            body['parent']['data_source_id'] = 'b-ays'
            return httpx.Response(200, json=body)
        return response

    fake.transport = httpx.MockTransport(foreign_page)
    run(fake, inventory, rings, '--apply')
    assert fake.page(page['id']) == page
    assert not [r for r in fake.requests if r.method == 'PATCH']


@pytest.mark.xfail(strict=True, reason='t6.fleet has no schema pre-check; gap to raise in t6-core')
def test_wrong_type_field_schema_refuses_before_updates(tmp_path):
    fake, inventory, rings = setup_case(tmp_path)
    add_bay(fake)
    fake.change_property_type('bays', 'Munki Manifest', 'number')
    assert run(fake, inventory, rings, '--apply') != 0
    assert not [r for r in fake.requests if r.method == 'PATCH']


def test_unmatched_machine_is_reported_without_create(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path)
    assert run(fake, inventory, rings, '--apply') == 0
    assert 'unmatched' in capsys.readouterr().out
    assert not [r for r in fake.requests if r.method == 'PATCH' or r.url.path == '/v1/pages']


def test_unknown_source_fields_leave_existing_values_untouched(tmp_path):
    fake, inventory, rings = setup_case(tmp_path, machines=[{'unix_hostname': 'Bay-1'}])
    page = add_bay(fake)
    assert run(fake, inventory, rings, '--apply') == 0
    assert fake.page(page['id']) == page
    assert not [r for r in fake.requests if r.method == 'PATCH']


def test_repeated_apply_is_a_noop(tmp_path):
    fake, inventory, rings = setup_case(tmp_path)
    add_bay(fake)
    assert run(fake, inventory, rings, '--apply') == 0
    fake.requests.clear()
    assert run(fake, inventory, rings, '--apply') == 0
    assert not [r for r in fake.requests if r.method == 'PATCH']


def test_dry_run_reports_old_and_new_without_writes(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path)
    page = add_bay(fake)
    assert run(fake, inventory, rings) == 0
    output = capsys.readouterr().out
    assert page['id'] in output
    assert all(value in output for value in ['serial_number', 'old', 'S1', 'munki_manifest',
                                              'old-manifest', 'Bay-1', 'ring', 'production', 'pilot'])
    assert not [r for r in fake.requests if r.method == 'PATCH']
    assert fake.page(page['id']) == page


def test_apply_writes_facts_and_readback(tmp_path):
    fake, inventory, rings = setup_case(tmp_path)
    page = add_bay(fake)
    assert run(fake, inventory, rings, '--apply') == 0
    row = bay(fake, page['id'])
    assert (row.serial_number, row.munki_manifest, row.ring) == ('S1', 'Bay-1', 'pilot')
    assert len([r for r in fake.requests if r.method == 'PATCH']) == 1


def test_different_identity_names_matching_different_rows_are_ambiguous(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path)
    add_bay(fake, name='First', host='Bay-1')
    add_bay(fake, name='Bay 1', host='other')
    assert run(fake, inventory, rings, '--apply') == 0
    assert 'ambiguous' in capsys.readouterr().out
    assert not [r for r in fake.requests if r.method == 'PATCH']


def test_two_machines_targeting_same_row_are_both_skipped(tmp_path, capsys):
    machines = [{'unix_hostname': 'Bay-1', 'serial': 'S1', 'munki_name': 'Bay-1'},
                {'unix_hostname': 'Bay 1', 'serial': 'S2', 'munki_name': 'Bay 1'}]
    fake, inventory, rings = setup_case(tmp_path, machines)
    add_bay(fake, host='Bay-1')
    assert run(fake, inventory, rings, '--apply') == 0
    assert 'ambiguous' in capsys.readouterr().out
    assert not [r for r in fake.requests if r.method == 'PATCH']


def test_known_absent_probed_machine_can_write_its_serial_without_inventing_manifest(tmp_path):
    fake, inventory, rings = setup_case(tmp_path, machines=[])
    inventory.write_text(json.dumps({'machines': [], 'known_absent': [
        {'name': 'Bay-1', 'probe_hostname': 'Bay-1', 'serial': 'S1'}]}))
    page = add_bay(fake, ring='production')
    assert run(fake, inventory, rings, '--apply') == 0
    row = bay(fake, page['id'])
    assert row.serial_number == 'S1'
    assert row.munki_manifest == 'old-manifest'
    assert row.ring == 'pilot'


def test_incomplete_pilot_declaration_does_not_write_production(tmp_path):
    fake, inventory, rings = setup_case(tmp_path, pilots=[{'name': 'unknown pilot'}])
    page = add_bay(fake, ring='pilot')
    assert run(fake, inventory, rings, '--apply') == 0
    assert bay(fake, page['id']).ring == 'pilot'


def test_exact_match_with_other_normalized_match_is_ambiguous(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path)
    add_bay(fake, name='first', host='Bay-1')
    add_bay(fake, name='second', host='bay-1')
    assert run(fake, inventory, rings, '--apply') == 0
    assert 'ambiguous' in capsys.readouterr().out
    assert not [r for r in fake.requests if r.method == 'PATCH']


# --- observed facts (ticket #7) ---------------------------------------------------------------

STORE = os.path.join(os.path.dirname(__file__), 'fixtures', 'probe', 'recorded-run-records.jsonl')
FRESH = '2026-09-13T19:40:00+08:00'      # a minute after the recorded run
LATER = '2026-09-13T23:40:00+08:00'      # hours later, so the recorded observation is stale

MINI = {'unix_hostname': 'Cyrils-Mac-mini', 'serial': 'RWJ57V9PW4', 'munki_name': 'Cyrils-Mac-mini'}
TOC = {'unix_hostname': '202-TOC-M4-Max', 'serial': 'RW3HL9FL4M', 'munki_name': '202-TOC-M4-Max'}


def observed_run(fake, inventory, rings, now, *extra):
    return main(['bays-writeback', '--inventory', str(inventory), '--rings', str(rings),
                 '--data-source', 'bays', '--store', STORE, '--now', now, *extra],
                deps=Deps(notion_client_factory=fake.client))


def test_a_healthy_observation_writes_its_three_facts(tmp_path):
    from datetime import datetime, timezone
    fake, inventory, rings = setup_case(tmp_path, machines=[MINI], pilots=[{'munki_name': MINI['munki_name']}])
    page = add_bay(fake, name='Mini', host='Cyrils-Mac-mini')
    assert observed_run(fake, inventory, rings, FRESH, '--apply') == 0
    row = bay(fake, page['id'])
    assert row.munki_client_version == '7.3.0.5808'
    assert row.os_version == '26.6.2'
    # the report's UTC 11:27:03 is Munki's own run time, not the probe's 19:39:19+08:00
    assert row.last_check_in == datetime(2026, 9, 13, 11, 27, tzinfo=timezone.utc)


def test_an_unreachable_machine_keeps_its_values_and_the_dry_run_says_why(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path, machines=[TOC], pilots=[{'munki_name': TOC['munki_name']}])
    page = add_bay(fake, name='TOC', host='202-TOC-M4-Max')
    assert observed_run(fake, inventory, rings, FRESH) == 0
    assert 'unobserved (unreachable)' in capsys.readouterr().out
    assert observed_run(fake, inventory, rings, FRESH, '--apply') == 0
    row = bay(fake, page['id'])
    assert (row.munki_client_version, row.os_version, row.last_check_in) == (None, None, None)


def test_a_machine_with_no_observation_is_skipped_with_a_reason(tmp_path, capsys):
    other = {'unix_hostname': 'Bay-1', 'serial': 'S1', 'munki_name': 'Bay-1'}
    fake, inventory, rings = setup_case(tmp_path, machines=[other])
    add_bay(fake)
    assert observed_run(fake, inventory, rings, FRESH) == 0
    assert 'no observation' in capsys.readouterr().out


def test_a_stale_observation_writes_no_observed_fact(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path, machines=[MINI], pilots=[{'munki_name': MINI['munki_name']}])
    page = add_bay(fake, name='Mini', host='Cyrils-Mac-mini')
    assert observed_run(fake, inventory, rings, LATER, '--apply') == 0
    assert 'stale observation' in capsys.readouterr().out
    assert bay(fake, page['id']).munki_client_version is None


def test_a_partial_observation_writes_only_the_fields_it_carries(tmp_path):
    from munki_fleet.bays_writeback import observed_facts
    entry = {'stale': False, 'observation': {
        'outcome': 'partial', 'observed_at': FRESH,
        'machine': {'munki_version': '7.3.0.5808', 'os_vers': None}, 'state': {}}}
    facts, why = observed_facts(entry)
    assert why is None
    assert facts['munki_client_version'] == '7.3.0.5808'
    assert facts['os_version'] is None and facts['last_check_in'] is None


def test_the_log_time_with_a_local_offset_lands_as_the_same_instant():
    from datetime import datetime, timedelta, timezone
    from munki_fleet.bays_writeback import observed_facts
    entry = {'stale': False, 'observation': {
        'outcome': 'observed', 'observed_at': FRESH, 'machine': {},
        'state': {'last_check': {'log_run_started': '2026-09-13 19:26:23.317+08:00'}}}}
    facts, _ = observed_facts(entry)
    assert facts['last_check_in'] == datetime(2026, 9, 13, 11, 26, 23, 317000, tzinfo=timezone.utc)
    assert facts['last_check_in'].utcoffset() == timedelta(hours=8)
