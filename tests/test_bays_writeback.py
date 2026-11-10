import json

from t6.notion.testing import FakeNotion, title, rich_text, select

from munki_fleet.cli import Deps, main


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
    assert all(value in output for value in ['Serial Number', 'old', 'S1', 'Munki Manifest',
                                              'old-manifest', 'Bay-1', 'Ring', 'production', 'pilot'])
    assert not [r for r in fake.requests if r.method == 'PATCH']
    assert fake.page(page['id']) == page


def test_apply_writes_facts_and_readback(tmp_path):
    from t6.notion.generated import BaysRow
    fake, inventory, rings = setup_case(tmp_path)
    page = add_bay(fake)
    assert run(fake, inventory, rings, '--apply') == 0
    with fake.client() as client:
        row = BaysRow.from_page(client.retrieve_page(page['id']))
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
    from t6.notion.generated import BaysRow
    fake, inventory, rings = setup_case(tmp_path, machines=[])
    inventory.write_text(json.dumps({'machines': [], 'known_absent': [
        {'name': 'Bay-1', 'probe_hostname': 'Bay-1', 'serial': 'S1'}]}))
    page = add_bay(fake, ring='production')
    assert run(fake, inventory, rings, '--apply') == 0
    row = BaysRow.from_page(fake.page(page['id']))
    assert row.serial_number == 'S1'
    assert row.munki_manifest == 'old-manifest'
    assert row.ring == 'pilot'


def test_incomplete_pilot_declaration_does_not_write_production(tmp_path):
    from t6.notion.generated import BaysRow
    fake, inventory, rings = setup_case(tmp_path, pilots=[{'name': 'unknown pilot'}])
    page = add_bay(fake, ring='pilot')
    assert run(fake, inventory, rings, '--apply') == 0
    assert BaysRow.from_page(fake.page(page['id'])).ring == 'pilot'


def test_exact_match_with_other_normalized_match_is_ambiguous(tmp_path, capsys):
    fake, inventory, rings = setup_case(tmp_path)
    add_bay(fake, name='first', host='Bay-1')
    add_bay(fake, name='second', host='bay-1')
    assert run(fake, inventory, rings, '--apply') == 0
    assert 'ambiguous' in capsys.readouterr().out
    assert not [r for r in fake.requests if r.method == 'PATCH']
