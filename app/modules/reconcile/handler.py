from fastapi import APIRouter
from app.inputs import Paired
from app.pipeline import execute

router = APIRouter()

@router.post('/api/reconcile')
def reconcile(source: Paired):
    report = execute(source.raw(),source.ledger())
    # 班次/产线结论与工作台、导出同源：直接返回 pipeline 中生成的同一份 book 与 rollup。
    return {key:report[key] for key in ('book','counts','balanced','line_rollup')}
