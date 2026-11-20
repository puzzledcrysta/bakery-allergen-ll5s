import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '换线清场审计'
SLUG = 'bakery-allergen'
KEY = '生产链'
FIELDS = ('换线记录', '配方申报')
ROLE = '中央厨房质量主管'
UNIT = '可放行批'
SIGNATURE = '风险档案签'
RULE_VERSION = 'bakery-allergen-1.0'
TABS = {'intake': '来源采信', 'contract': '字段解释', 'quality': '隔离裁决', 'domain': '换线裁决', 'reconcile': '独立对账', 'runs': '批次复算', 'review': '交付复核'}
