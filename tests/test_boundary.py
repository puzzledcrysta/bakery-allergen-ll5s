"""班次/产线两级对账与放行边界测试。

构造两条产线共同供货的班次：外部账只有班次总额，内部按产线给出可放行数。
"""
from decimal import Decimal
import pytest
from app.errors import DataError
from app.settings import KEY, UNIT
from app.modules.reconcile.ledger import ledger_book
from app.modules.reconcile.service import compare
from app.pipeline import execute

HEADER = f'{KEY},范围,外部记录值({UNIT})'


def source_text():
    rows = [
        # 每条来源记录是一条独立生产链；用两条链分别承载 A、B 两线证据。
        # 产线 A：两批均无残留 -> 2 批可放行
        ('A1', '1,A,A1,RUN,无;2,A,A2,RUN,无', 'A1=无;A2=无'),
        # 产线 B：首批蛋残留，清场验证未通过，第二批未申报蛋 -> B2 扣留，仅 1 批可放行
        ('B1', '3,B,B1,RUN,蛋;4,B,BC,CLEAN,FAIL;5,B,B2,RUN,无', 'B1=蛋;B2=奶'),
    ]
    lines = [f'{KEY},修订号,提交时间,换线记录,配方申报,原始备注']
    for index, (key, record, recipe) in enumerate(rows, 1):
        lines.append(f'{key},1,2026-11-18T{9+index:02d}:00:00+08:00,"{record}",{recipe},')
    return '\n'.join(lines).encode()


def shift_book(total, keyed_rows=()):
    lines = [HEADER]
    lines.extend(f'{key},产线,{amount}' for key, amount in keyed_rows)
    lines.append(f'2026-11-18,班次,{total}')
    return '\n'.join(lines).encode()


@pytest.fixture
def two_line():
    return source_text()


def test_line_rollup_splits_release_by_line(two_line):
    result = execute(two_line, shift_book(3))
    rollup = {row['line']: row for row in result['line_rollup']}
    assert rollup['A']['releasable'] == 2 and rollup['A']['held'] == 0
    assert rollup['B']['releasable'] == 1 and rollup['B']['held'] == 1
    shift = result['book']['shift']
    assert shift['code'] == 'SHIFT_MATCH' and shift['internal_total'] == '3'
    assert shift['external_total'] == '3' and shift['delta'] == '0'
    # 两条产线一高一低，总额相符也必须保留逐线证据，不能整班一笔带过。
    assert {row['line']: row['releasable'] for row in shift['lines']} == {'A': '2', 'B': '1'}


def test_same_shift_total_with_misdistribution_is_flagged(two_line):
    # 总额相同（3），但外部账逐链参照落在错误的生产链上：班次层相符，逐链层仍须暴露差值。
    result = execute(two_line, shift_book(3, keyed_rows=(('A1', '3'),)))
    shift = result['book']['shift']
    assert shift['code'] == 'SHIFT_MATCH'
    codes = {row['key']: row['code'] for row in result['book']['rows']}
    assert codes['A1'] == 'AMOUNT_DELTA' and codes['B1'] == 'MISSING_BOOK'


def test_shift_total_delta_is_measured(two_line):
    result = execute(two_line, shift_book(2))
    shift = result['book']['shift']
    assert shift['code'] == 'SHIFT_DELTA'
    assert Decimal(shift['delta']) == Decimal('1')


def test_keyed_ledger_remains_supported():
    book = f'{KEY},外部记录值({UNIT})\n009,1\n'.encode()
    parsed = ledger_book(book)
    assert parsed['mode'] == 'keyed' and parsed['shift'] is None
    report = compare([{'key': '009', 'line': 2, 'amount': '1'}], book)
    assert report['shift']['code'] == 'NO_SHIFT_TOTAL' and report['rows'][0]['code'] == 'MATCH'


def test_unknown_scope_rejected(two_line):
    bad = f'{HEADER}\nA1,车间,2\n2026-11-18,班次,3\n'.encode()
    with pytest.raises(DataError) as error:
        execute(two_line, bad)
    assert error.value.code == 'SCOPE_UNKNOWN'


def test_duplicate_shift_total_rejected(two_line):
    bad = f'{HEADER}\n2026-11-18,班次,3\n2026-11-18,班次,3\n'.encode()
    with pytest.raises(DataError) as error:
        execute(two_line, bad)
    assert error.value.code == 'SHIFT_CONFLICT'


# --- 放行边界 ---------------------------------------------------------------

def submit_boundary(client, run_id, items, version=0, note='已逐线核对证据'):
    return client.post(f'/api/boundary/{run_id}',
                       json={'version': version, 'items': items, 'note': note})


def test_boundary_requires_line_evidence(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    view = client.get(f'/api/boundary/{run_id}').json()
    assert view['version'] == 0 and view['pending'] == 2
    assert {row['line']: row['state'] for row in view['lines']} == {'A': '待确认', 'B': '待确认'}
    ok = submit_boundary(client, run_id, [{'line': 'A', 'release': 2},
                                          {'line': 'B', 'release': 1}])
    assert ok.status_code == 200 and ok.json()['version'] == 1
    assert ok.json()['release_total'] == '3' and ok.json()['pending'] == 0


def test_boundary_cannot_exceed_line_releasable(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    blocked = submit_boundary(client, run_id, [{'line': 'B', 'release': 2}])
    assert (blocked.status_code, blocked.json()['code']) == (422, 'BOUNDARY_LIMIT')
    # 被拒后旧版（尚无登记）原样保留，没有产生半截写入。
    assert client.get(f'/api/boundary/{run_id}').json()['version'] == 0


def test_boundary_cannot_exceed_shift_total(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(2).decode()}) \
                    .json()['manifest']['run_id']
    blocked = submit_boundary(client, run_id, [{'line': 'A', 'release': 2},
                                               {'line': 'B', 'release': 1}],
                              note='差额待外部补证')
    assert (blocked.status_code, blocked.json()['code']) == (422, 'BOUNDARY_TOTAL')


def test_partial_release_keeps_pending_within_line(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    # 只放行 A 线可放行数的一部分，B 线仍待确认，供排产先取 A 线。
    response = submit_boundary(client, run_id, [{'line': 'A', 'release': 1}],
                               note='先放行 A 线一批赶排产，B 线待补清场')
    body = response.json()
    line = {row['line']: row for row in body['lines']}
    assert line['A']['state'] == '部分放行' and line['B']['state'] == '待确认'
    assert body['release_total'] == '1' and body['pending'] == 1


def test_boundary_unknown_line_rejected(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    blocked = submit_boundary(client, run_id, [{'line': 'Z', 'release': 1}])
    assert (blocked.status_code, blocked.json()['code']) == (422, 'BOUNDARY_LINE')


def test_boundary_stale_version_rejected(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    assert submit_boundary(client, run_id, [{'line': 'A', 'release': 2}]).status_code == 200
    stale = submit_boundary(client, run_id, [{'line': 'A', 'release': 1}], version=0)
    assert (stale.status_code, stale.json()['code']) == (409, 'BOUNDARY_STALE')


def test_replay_keeps_boundary_and_adds_no_pending(client, two_line):
    payload = {'data': two_line.decode(), 'book': shift_book(3).decode()}
    run_id = client.post('/api/runs', json=payload).json()['manifest']['run_id']
    submit_boundary(client, run_id, [{'line': 'A', 'release': 2}, {'line': 'B', 'release': 1}])
    # 复算同一输入：同一 run_id，边界版本与记录原样保留，不新增待确认。
    replayed = client.post(f'/api/runs/{run_id}/replay').json()
    assert replayed['manifest']['run_id'] == run_id
    view = client.get(f'/api/boundary/{run_id}').json()
    assert view['version'] == 1 and view['pending'] == 0
    assert view['release_total'] == '3'
    assert len(client.get('/api/runs').json()) == 1


def test_failed_replay_keeps_old_result_and_evidence(client, two_line):
    payload = {'data': two_line.decode(), 'book': shift_book(3).decode()}
    run_id = client.post('/api/runs', json=payload).json()['manifest']['run_id']
    submit_boundary(client, run_id, [{'line': 'A', 'release': 2}])
    # 用损坏外部账复算会在写入前失败；旧版可放行结果、原始依据与边界均保留。
    bad = client.post('/api/runs', json={'data': two_line.decode(), 'book': '坏账\nx'})
    assert bad.status_code == 422
    detail = client.get(f'/api/runs/{run_id}').json()
    assert sum(int(row['amount']) for row in detail['accepted']) == 3
    restored = client.get(f'/api/runs/{run_id}/source').json()
    from base64 import b64decode
    assert b64decode(restored['book_base64']) == shift_book(3)
    assert client.get(f'/api/boundary/{run_id}').json()['release_total'] == '2'


def test_workbench_and_export_share_one_conclusion(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    submit_boundary(client, run_id, [{'line': 'A', 'release': 2}, {'line': 'B', 'release': 1}])
    exported = client.get(f'/api/export/{run_id}').json()
    live = client.get(f'/api/boundary/{run_id}').json()
    assert exported['release_boundary'] == live
    assert exported['reconciliation']['shift']['lines'] == exported['reconciliation']['shift']['lines']
    # 导出同时带产线证据与班次总额结论。
    assert exported['line_rollup'] and exported['reconciliation']['shift']['external_total'] == '3'


def test_export_remains_reproducible_with_boundary(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    submit_boundary(client, run_id, [{'line': 'A', 'release': 2}])
    first = client.get(f'/api/export/{run_id}').content
    second = client.get(f'/api/export/{run_id}').content
    assert first == second


def test_keyed_ledger_boundary_has_no_shift_cap(client, two_line):
    # 两列外部账没有班次总额：边界仍按产线可放行数约束，只是没有总额上限。
    keyed = f'{KEY},外部记录值({UNIT})\nA1,2\nB1,1\n'.encode()
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': keyed.decode()}) \
                    .json()['manifest']['run_id']
    view = client.get(f'/api/boundary/{run_id}').json()
    assert view['external_total'] is None and view['within_shift_cap'] is None
    ok = submit_boundary(client, run_id, [{'line': 'A', 'release': 2},
                                          {'line': 'B', 'release': 1}])
    assert ok.status_code == 200 and ok.json()['release_total'] == '3'


def test_zero_release_marks_line_held(client, two_line):
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    body = submit_boundary(client, run_id, [{'line': 'A', 'release': 0},
                                            {'line': 'B', 'release': 1}],
                           note='A 线本批暂缓').json()
    state = {row['line']: row['state'] for row in body['lines']}
    assert state == {'A': '暂缓', 'B': '放行'} and body['pending'] == 0


def test_replay_service_keeps_boundary_records(client, two_line):
    from app.modules.runs.service import run, replay
    from app.modules.review.boundary import boundary_view
    book = shift_book(3)
    stored = run(two_line, book)
    run_id = stored['manifest']['run_id']
    submit_boundary(client, run_id, [{'line': 'A', 'release': 2}])
    # 服务层复算同一输入：结果等价且边界版本、明细不丢失。
    again = replay(run_id)
    assert again['manifest']['run_id'] == run_id
    view = boundary_view(run_id)
    assert view['version'] == 1 and view['lines'][0]['release'] == 2


def test_rejected_submit_persists_nothing(client, two_line):
    from app.store import connection
    run_id = client.post('/api/runs', json={'data': two_line.decode(),
                                            'book': shift_book(3).decode()}) \
                    .json()['manifest']['run_id']
    submit_boundary(client, run_id, [{'line': 'A', 'release': 9}])
    with connection() as db:
        count = db.execute('SELECT COUNT(*) FROM boundaries WHERE run_id=?', (run_id,)).fetchone()[0]
    assert count == 0
