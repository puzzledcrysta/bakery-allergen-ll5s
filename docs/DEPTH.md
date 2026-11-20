# 换线清场审计深度登记

- 规模：中型
- 核心规则：按时间检查过敏原残留，只有匹配产线且验证通过的清场才能解除前序过敏原。
- 使用者与工作流：中央厨房质量主管按生产链复算来源批次，对照外部记录后提交复核。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 来源采信 | 接收分段记录、定位坏行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 字段解释 | 归一主键、版本、时间和原字段 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 隔离裁决 | 归并重复、隔离争议版本 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 换线裁决 | 复算业务明细与边界证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 独立对账 | 核对外部记录并分别计量 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 批次复算 | 保存运行、查询历史、复算原输入 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 交付复核 | 复核差异、阻止陈旧提交、导出证据 | `GET /api/export` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 班次边界 | 按班次总额与逐产线证据划定放行边界 | `POST /api/boundary` | `app/modules/review/boundary.py` | `tests/test_boundary.py` |

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-02 | BOM | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不齐 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 空值哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 主键前导零 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时间归一 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 等版本冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-18 | 三种空态 | 测试构造输入 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核 | 测试构造输入 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-13 | 乱序换线恢复状态，其他线清场不可抵销 | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_residue` |
| TRAP-31 | 多产线共供一班，外部账只有班次总额 | external_shift.csv | `app/modules/reconcile/conclusion.py` | `tests/test_boundary.py::test_line_rollup_splits_release_by_line` |
| TRAP-32 | 总额相符但逐链分布错位 | 测试构造输入 | `app/modules/reconcile/service.py` | `tests/test_boundary.py::test_same_shift_total_with_misdistribution_is_flagged` |
| TRAP-33 | 放行边界超产线可放行数或班次总额 | 测试构造输入 | `app/modules/review/boundary.py` | `tests/test_boundary.py::test_boundary_cannot_exceed_line_releasable` |

## 对账规则

输入记录数 = 计入 + 隔离 + 去重和替换 + 空白记录 + 重复表头。
业务账按生产链全外连接。差异分别标记漏记、外部单边和数值不符，以可放行批对差。
外部账三列形态（生产链,范围,外部记录值）在逐链参照之外登记班次总额；范围为“班次”的行
只参与班次层核对，范围为“产线”的行参与逐链核对。班次总额相符不抹除逐链差值，
放行边界由复核员逐产线登记，超产线可放行数（`BOUNDARY_LIMIT`）或超外部班次总额
（`BOUNDARY_TOTAL`）一律拒绝写入。

## 放行边界与复算

- 产线级可放行数由换线裁决同步产出（`domain/rule.py` 的 `lines`），随每条可采信记录留痕。
- 工作台 `/api/boundary/{run_id}` 与导出包的 `release_boundary` 来自同一函数
  `review/boundary.py::boundary_view`，结论只有一份。
- 边界按版本追加，旧版本只读，过期版本返回 409（`BOUNDARY_STALE`）。
- 运行指纹由规则版本与两份输入哈希决定：重跑同一输入命中同一 `run_id`，
  既有边界原样保留，不新增待确认、不丢记录；校验失败在写入前抛出，
  旧版可放行结果、原始输入与边界全部保留。

## 范围

本地文件与单机复核。单次来源文本限 128 KiB。复合字段单项最多 240 段。
