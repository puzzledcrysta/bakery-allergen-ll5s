from collections import defaultdict
from decimal import Decimal
from app.errors import DataError
from .values import whole, parts


def allergens(value):
    if value == '无':
        return set()
    codes = value.split('+')
    if not value or set(codes)-{'蛋','奶','麸质','坚果','大豆'}:
        raise DataError('BUSINESS',f'未登记过敏原 {value}')
    return set(codes)


def evaluate(row):
    declarations = {}
    for entry in parts(row['配方申报']):
        batch,sep,reg = entry.partition('=')
        if not sep or not batch or batch in declarations:
            raise DataError('BUSINESS',f'配方申报重复或畸形 {entry}')
        declarations[batch] = allergens(reg)
    records, slots, used = [],set(),set()
    for entry in parts(row['换线记录']):
        fields = entry.split(',')
        if len(fields) != 5 or fields[3] not in {'RUN','CLEAN'} or not fields[1] or not fields[2]:
            raise DataError('BUSINESS',f'换线证据字段无效 {entry}')
        stamp,line,batch,action,note = fields
        stamp = whole(stamp,0,10080)
        if (line,stamp) in slots or (action=='RUN' and batch in used):
            raise DataError('BUSINESS',f'重复生产证据 {batch}')
        slots.add((line,stamp))
        if action=='RUN':
            used.add(batch)
        elif note not in {'PASS','FAIL'}:
            raise DataError('BUSINESS',f'清场验证无结论 {batch}')
        records.append((stamp,line,batch,action,note))
    if used != declarations.keys():
        raise DataError('BUSINESS','生产与配方批号不一致')
    residue, proof, passed = defaultdict(set), [], 0
    line_passed, line_total = defaultdict(int), defaultdict(int)
    for _, line, batch, action, note in sorted(records):
        if action == 'CLEAN':
            if note == 'PASS':
                residue[line].clear()
            continue
        residue[line].update(allergens(note))
        line_total[line] += 1
        missing = residue[line]-declarations[batch]
        if not missing:
            passed += 1
            line_passed[line] += 1
        state = '扣留 ' + '+'.join(sorted(missing)) if missing else '可放行'
        proof.append((f'{line} / {batch}', state, ''))
    # 产线级对账依据：每条产线各自的可放行批数与生产批数，供班次边界裁决。
    lines = [{'line': name,
              'releasable': line_passed[name],
              'produced': line_total[name],
              'held': line_total[name]-line_passed[name]}
             for name in sorted(line_total)]
    return Decimal(passed), proof, lines
