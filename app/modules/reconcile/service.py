from decimal import Decimal
from .ledger import ledger, ledger_book
from .conclusion import build_shift_conclusion, rollup_from_accepted


def compare(accepted, payload, rollup=None):
    book = ledger_book(payload)
    expected = book['by_key']
    actual = {row['key']: (Decimal(row['amount']), row['line']) for row in accepted}
    rows, matches = [], 0
    for key in sorted(actual.keys() | expected.keys()):
        value, line = actual.get(key, (None, None))
        book_value, book_line = expected.get(key, (None, None))
        delta = (value or Decimal(0)) - (book_value or Decimal(0))
        reason = ('MISSING_BOOK' if book_value is None else 'MISSING_RESULT' if value is None else
                  'AMOUNT_DELTA' if delta else 'MATCH')
        matches += reason == 'MATCH'
        rows.append({'key': key, 'amount': str(value) if value is not None else None,
                     'reference': str(book_value) if book_value is not None else None, 'delta': str(delta),
                     'line': line, 'book_line': book_line, 'code': reason})
    actual_total = sum((pair[0] for pair in actual.values()), Decimal(0))
    book_total = sum((pair[0] for pair in expected.values()), Decimal(0))
    line_rollup = rollup if rollup is not None else rollup_from_accepted(accepted)
    # 班次与产线两级结论：工作台与导出共用这一份结果。
    shift = build_shift_conclusion(book, line_rollup)
    return {'rows': rows, 'matched': matches, 'mismatched': len(rows)-matches,
            'actual': str(actual_total), 'expected': str(book_total),
            'delta': str(actual_total-book_total), 'mode': book['mode'], 'shift': shift}
