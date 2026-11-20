import json
from app.modules.runs.service import get
from .decisions import timeline
from .boundary import boundary_view


def bundle(run_id):
    history = timeline(run_id)
    run = get(run_id)
    # 工作台与导出共用同一份班次/产线对账结论与放行边界，避免两套口径。
    boundary = boundary_view(run_id)
    # The export carries source line evidence and the applicable decision version.
    return json.dumps({'manifest':run['manifest'],'counts':run['counts'],'results':run['accepted'],
                       'quarantine':run['quarantine'],'suppressed':run['suppressed'],
                       'reconciliation':run['book'],'line_rollup':run['line_rollup'],
                       'release_boundary':boundary,'review':history},
                      ensure_ascii=False,indent=2)
