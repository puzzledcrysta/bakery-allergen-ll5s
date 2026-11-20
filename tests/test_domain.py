from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_residue(cases):
    # TRAP-13
    actual, evidence, lines = evaluate(cases['residue'])
    assert actual == Decimal('1')
    assert evidence and all(len(row)==3 for row in evidence)
    rollup = {row['line']: row for row in lines}
    # 产线 A 第二批缺清场，前序过敏原残留导致扣留；B 线只有清场记录、无生产批。
    assert rollup['A'] == {'line': 'A', 'releasable': 1, 'produced': 2, 'held': 1}
    assert 'B' not in rollup
    assert sum(row['releasable'] for row in lines) == actual


def test_verified(cases):
    actual, evidence, lines = evaluate(cases['verified'])
    assert actual == Decimal('2')
    assert sum(row['releasable'] for row in lines) == 2


def test_invalid_clean(cases):
    actual, evidence, lines = evaluate(cases['invalid_clean'])
    assert actual == Decimal('1')
    assert sum(row['held'] for row in lines) == 1


def test_declared_residue(cases):
    actual, evidence, lines = evaluate(cases['declared_residue'])
    assert actual == Decimal('2')
    assert all(row['held'] == 0 for row in lines)


def test_collision(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['collision'])
    assert error.value.code in {'BUSINESS','NUMBER','RANGE','TIMESTAMP'}


def test_unknown(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['unknown'])
    assert error.value.code in {'BUSINESS','NUMBER','RANGE','TIMESTAMP'}


def test_no_definition(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['no_definition'])
    assert error.value.code in {'BUSINESS','NUMBER','RANGE','TIMESTAMP'}
