"""放行边界：复核员依据班次总额与逐产线证据划定。

边界按版本追加，旧版本只读；重跑同一输入得到同一 run_id，既有边界原样保留，
既不会新增待确认项，也不会丢失记录。任何校验失败都在写入前抛出，旧版结论不受影响。
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from app.errors import DataError
from app.store import connection
from app.modules.runs.repository import lookup
from app.modules.reconcile.conclusion import build_shift_conclusion


def _state(run):
    book = run['book']
    shift = book['shift']
    lines = {item['line']: item for item in shift['lines']}
    return book, shift, lines


def get_boundaries(run_id):
    with connection() as db:
        lookup(db, run_id)
        rows = db.execute(
            'SELECT version, line, release, note, changed FROM boundaries '
            'WHERE run_id=? ORDER BY version DESC, line ASC', (run_id,)).fetchall()
        current = rows[0]['version'] if rows else 0
        latest = [dict(row) for row in rows if row['version'] == current]
        return {'version': current, 'lines': latest}


def boundary_view(run_id):
    """合并复算产线证据与已登记边界，返回工作台与导出共用的放行结论。"""
    with connection() as db:
        run = json.loads(lookup(db, run_id)['result'])
        saved = get_boundaries(run_id)
    book, shift, lines = _state(run)
    chosen = {item['line']: item for item in saved['lines']}
    view_lines = []
    total_release = 0
    for name, evidence in sorted(lines.items()):
        releasable = int(Decimal(evidence['releasable']))
        record = chosen.get(name)
        release = int(record['release']) if record else 0
        total_release += release
        if record is None:
            state = '待确认'
        elif release == 0:
            state = '暂缓'
        elif release < releasable:
            state = '部分放行'
        else:
            state = '放行'
        view_lines.append({'line': name, 'releasable': evidence['releasable'],
                           'produced': evidence['produced'], 'held': evidence['held'],
                           'release': release, 'state': state,
                           'note': record['note'] if record else '',
                           'changed': record['changed'] if record else None,
                           'keys': evidence['keys']})
    external = shift['external_total']
    cap = int(Decimal(external)) if external is not None else None
    return {'version': saved['version'], 'shift': shift['shift'],
            'shift_code': shift['code'], 'internal_total': shift['internal_total'],
            'external_total': external, 'shift_delta': shift['delta'],
            'lines': view_lines, 'release_total': str(total_release),
            'pending': sum(1 for item in view_lines if item['state'] == '待确认'),
            'within_shift_cap': None if cap is None else total_release <= cap}


def submit(run_id, version, items, note):
    note = note.strip()
    if not items:
        raise DataError('BOUNDARY_LIMIT', '至少登记一条产线放行边界')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = json.loads(lookup(db, run_id)['result'])
        current = db.execute('SELECT COALESCE(MAX(version),0) FROM boundaries WHERE run_id=?',
                             (run_id,)).fetchone()[0]
        if current != version:
            raise DataError('BOUNDARY_STALE', '放行边界版本已过期，请刷新', 409)
        _, shift, lines = _state(run)
        requested, total = {}, 0
        for item in items:
            name = str(item.get('line', '')).strip()
            if name not in lines:
                raise DataError('BOUNDARY_LINE', f'产线 {name} 不属于本班次证据')
            value = item.get('release')
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise DataError('BOUNDARY_LIMIT', f'产线 {name} 放行数须为非负整数')
            if name in requested:
                raise DataError('BOUNDARY_LINE', f'产线 {name} 重复登记')
            cap = int(Decimal(lines[name]['releasable']))
            if value > cap:
                raise DataError('BOUNDARY_LIMIT',
                                f'产线 {name} 放行 {value} 批超过可放行 {cap} 批')
            requested[name] = value
            total += value
        external = shift['external_total']
        if external is not None and total > int(Decimal(external)):
            raise DataError('BOUNDARY_TOTAL',
                            f'放行总数 {total} 批超过外部班次总额 {external} 批')
        if (shift['code'] != 'SHIFT_MATCH' or
                any(value < int(Decimal(lines[name]['releasable']))
                    for name, value in requested.items())) and not note:
            raise DataError('REVIEW_NOTE', '有差额或部分放行时须填写复核意见')
        changed = datetime.now(timezone.utc).isoformat()
        next_version = current + 1
        db.executemany(
            'INSERT INTO boundaries VALUES (?,?,?,?,?,?)',
            [(run_id, next_version, name, value, note, changed)
             for name, value in sorted(requested.items())])
    return boundary_view(run_id)
