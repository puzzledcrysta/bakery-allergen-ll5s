from app.errors import DataError
from app.evidence import finding
from app.settings import UNIT
from .rule import evaluate


def calculate(records):
    accepted, rejected = [],[]
    lines = {}
    for record in records:
        try:
            amount, proof, line_rollup = evaluate(record['fields'])
        except DataError as error:
            rejected.append(finding(record,error.code,str(error)))
            continue
        for item in line_rollup:
            slot = lines.setdefault(item['line'], {'line': item['line'], 'releasable': 0,
                                                   'produced': 0, 'held': 0, 'keys': []})
            slot['releasable'] += item['releasable']
            slot['produced'] += item['produced']
            slot['held'] += item['held']
            slot['keys'].append(record['key'])
        accepted.append({'key':record['key'],'line':record['line'],'revision':record['revision'],
                         'amount':format(amount,'f'),'unit':UNIT,'raw':record['raw'],
                         'line_rollup':line_rollup,
                         'proof':[{'metric':label,'value':str(value),'unit':unit} for label,value,unit in proof]})
    rollup = sorted(lines.values(), key=lambda item: item['line'])
    return accepted, rejected, rollup
