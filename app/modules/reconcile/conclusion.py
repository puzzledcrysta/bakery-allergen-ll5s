"""班次/产线两级对账结论。

工作台接口与证据导出共用本模块的同一份结论，避免两套口径。
- 外部账只有班次总额时，逐产线证据仍须保留，放行边界由复核员逐线划定；
- 外部账含逐链参照时，沿用逐链差值并以可放行批对差。
"""
from decimal import Decimal
from app.settings import SHIFT_SCOPE


def _merge(items):
    merged = {}
    for item in items:
        slot = merged.setdefault(item['line'], {'line': item['line'], 'releasable': 0,
                                                'produced': 0, 'held': 0, 'keys': []})
        slot['releasable'] += int(item['releasable'])
        slot['produced'] += int(item['produced'])
        slot['held'] += int(item['held'])
        slot['keys'].extend(item.get('keys', ()))
    return sorted(merged.values(), key=lambda row: row['line'])


def rollup_from_accepted(accepted):
    """从可采信记录内嵌的产线汇总重建运行级产线证据。"""
    merged = {}
    for row in accepted:
        for piece in row.get('line_rollup', ()):
            slot = merged.setdefault(piece['line'], {'line': piece['line'], 'releasable': 0,
                                                     'produced': 0, 'held': 0, 'keys': []})
            slot['releasable'] += int(piece['releasable'])
            slot['produced'] += int(piece['produced'])
            slot['held'] += int(piece['held'])
            slot['keys'].append(row['key'])
    return sorted(merged.values(), key=lambda item: item['line'])


def build_shift_conclusion(book, rollup):
    """汇总产线可放行数并与外部账班次总额核对。"""
    lines = _merge(rollup or [])
    internal = sum((Decimal(item['releasable']) for item in lines), Decimal(0))
    lines_out = [{'line': item['line'],
                  'releasable': str(item['releasable']),
                  'produced': str(item['produced']),
                  'held': str(item['held']),
                  'keys': item['keys']}
                 for item in lines]
    shift = book.get('shift')
    if shift is None:
        return {'scope': SHIFT_SCOPE, 'shift': None, 'book_line': None,
                'internal_total': str(internal), 'external_total': None, 'delta': None,
                'code': 'NO_SHIFT_TOTAL', 'lines': lines_out}
    external = shift['amount']
    delta = internal - external
    code = 'SHIFT_MATCH' if delta == 0 else 'SHIFT_DELTA'
    return {'scope': SHIFT_SCOPE, 'shift': shift['shift'], 'book_line': shift['line'],
            'internal_total': str(internal), 'external_total': str(external),
            'delta': str(delta), 'code': code, 'lines': lines_out}
