from app.errors import DataError
from app.settings import KEY, UNIT, SHIFT_SCOPE, LINE_SCOPE
from app.modules.domain.values import number
from app.modules.intake.reader import decode, records

KEYED_HEADER = [KEY, f'外部记录值({UNIT})']
SCOPED_HEADER = [KEY, '范围', f'外部记录值({UNIT})']


def ledger(payload):
    """逐链外部账：业务键 -> (计量, 物理行号)。"""
    text, _ = decode(payload)
    rows = iter(records(text))
    _, header = next(rows, (0, []))
    if header != KEYED_HEADER:
        raise DataError('HEADER', '外部账表头或计量单位不符')
    by_key = {}
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != 2 or not row[0].strip():
            raise DataError('WIDTH', f'外部账第 {line} 行缺少业务键或计量')
        key = row[0].strip()
        if key in by_key:
            raise DataError('BOOK_CONFLICT', f'外部账第 {line} 行重复业务键 {key}')
        by_key[key] = (number(row[1]), line)
    return by_key


def ledger_book(payload):
    """解析外部账，同时保留逐链记录与班次总额。

    支持两种形态，表头二选一：
    - 两列：生产链, 外部记录值(可放行批)           —— 只含逐链参照；
    - 三列：生产链, 范围, 外部记录值(可放行批)      —— 逐链行范围为“产线”，
      范围为“班次”的行只登记班次总额，业务键列写班次标识。
    """
    text, _ = decode(payload)
    rows = iter(records(text))
    _, header = next(rows, (0, []))
    if header == KEYED_HEADER:
        return {'by_key': ledger(payload), 'shift': None, 'mode': 'keyed'}
    if header != SCOPED_HEADER:
        raise DataError('HEADER', '外部账表头或计量单位不符')
    by_key, shift = {}, None
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != 3 or not row[0].strip() or not row[1].strip():
            raise DataError('WIDTH', f'外部账第 {line} 行缺少业务键、范围或计量')
        key, scope = row[0].strip(), row[1].strip()
        amount = number(row[2])
        if scope == SHIFT_SCOPE:
            if shift is not None:
                raise DataError('SHIFT_CONFLICT', f'外部账第 {line} 行重复登记班次总额')
            shift = {'shift': key, 'amount': amount, 'line': line}
            continue
        if scope != LINE_SCOPE:
            raise DataError('SCOPE_UNKNOWN', f'外部账第 {line} 行范围 {scope} 无法识别')
        if key in by_key:
            raise DataError('BOOK_CONFLICT', f'外部账第 {line} 行重复业务键 {key}')
        by_key[key] = (amount, line)
    return {'by_key': by_key, 'shift': shift, 'mode': 'scoped'}
