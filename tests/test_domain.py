from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_residue(cases):
    # TRAP-13
    actual, evidence = evaluate(cases['residue'])
    assert actual == Decimal('1')
    assert evidence and all(len(row)==3 for row in evidence)


def test_verified(cases):
    actual, evidence = evaluate(cases['verified'])
    assert actual == Decimal('2')


def test_invalid_clean(cases):
    actual, evidence = evaluate(cases['invalid_clean'])
    assert actual == Decimal('1')


def test_declared_residue(cases):
    actual, evidence = evaluate(cases['declared_residue'])
    assert actual == Decimal('2')


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

