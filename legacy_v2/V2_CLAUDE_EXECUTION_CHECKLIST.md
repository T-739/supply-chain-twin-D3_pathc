# Claude Code 执行清单（基于最终版 SPEC）

## 1. 任务目标（Objective）

按最终版 `SPEC.md` 实现 supply chain twin MVP 的 **Twin State 层** 与 **deterministic cost engine**，只覆盖关键路径第 1 步：

1. Twin State Schema
2. deterministic cost logic
3. case translation contract
4. unit tests

本轮 **不要** 实现：
- Governance Agent
- Streamlit UI
- LangGraph graph
- RAG
- Weather API
- optimization engine
- stochastic simulation

---

## 2. 本轮必须产出的文件（Deliverables）

按以下顺序实现：

1. `data/configs/baseline_network.json`
2. `src/twin_state.py`
3. `tests/test_twin_state_costs.py`
4. `src/case_translation.py`

可选但推荐：
5. `tests/test_case_translation.py`

---

## 3. 实现顺序（Execution Order）

### Step 1 — 落地 baseline 配置
先创建 `data/configs/baseline_network.json`，**数值必须与 SPEC 完全一致**。

完成标准：
- 文件可被读取
- JSON 合法
- 字段名与 SPEC 完全一致
- entity 数量严格为 2/2/2/2

---

### Step 2 — 实现数据模型（Pydantic v2）
在 `src/twin_state.py` 中定义以下模型：

- `Supplier`
- `Warehouse`
- `Carrier`
- `CustomerZone`
- `CostPolicy`
- `ActionType`
- `Action`
- `SupervisorDecisionType`
- `TwinState`

要求：
- 使用 Pydantic v2
- 所有字段带类型注解
- 不使用 dataclass 替代
- `TwinState` 必须是真对象，不是 prompt blob

---

### Step 3 — 实现 `initialize_from_config(path)`
实现方式建议：`@classmethod`

要求：
- 读取 JSON
- 将 list 转为 `dict[str, Model]`
- 读取 `active_order` 并写入 `TwinState`
- 校验 2 suppliers / 2 warehouses / 2 carriers / 2 customer zones
- 非法输入 fail fast

建议输出：
- 返回一个完整 `TwinState` 实例

---

### Step 4 — 实现 `inject_shock(shock_config)`
支持 patch 机制：
- `set`
- `add`
- `multiply`

支持 entity：
- `supplier`
- `warehouse`
- `carrier`
- `customer_zone`
- `twin`

要求：
- patch 顺序严格按输入顺序执行
- patch 结果写入 `current_disruptions`
- 不允许随机行为
- 重复运行同一 baseline + 同一 shock 必须得到同一 state

---

### Step 5 — 实现 `apply_action(action)`
只允许四种 operational action：
- `EXPEDITE`
- `TRANSFER`
- `COMPENSATE`
- `NO_ACTION`

#### 5.1 `EXPEDITE`
校验：
- `target_carrier_id` 必填
- carrier 存在
- carrier `available == True`
- carrier `capacity_limit >= units`

状态更新：
- `planned_carrier_id = target_carrier_id`
- `planned_eta_hours += eta_adjustment_hours`

#### 5.2 `TRANSFER`
校验：
- `from_warehouse_id` 必填
- `to_warehouse_id` 必填
- source inventory 足够
- destination 不超 `max_capacity`
- `from != to`

状态更新：
- source `current_inventory -= units`
- destination `current_inventory += units`
- `planned_eta_hours += eta_adjustment_hours`

#### 5.3 `COMPENSATE`
校验：
- `compensation_per_unit` 允许缺省，用默认值
- `penalty_relief_per_hour` 允许缺省，用默认值
- `0 <= penalty_relief_per_hour < zone.sla_penalty_per_hour`

状态更新：
- 不修改 inventory
- 不修改 carrier
- 通常不修改 ETA

#### 5.4 `NO_ACTION`
状态更新：
- 不修改 inventory
- 不修改 carrier
- 不修改 ETA（通常为 0）

统一要求：
- `action.units == state.order_units`，否则报错
- 记录 `last_applied_action`
- 不自动 fallback 到别的动作

---

### Step 6 — 实现 `compute_total_cost()`
必须在 action 已 apply 后才允许调用。

统一中间量：
- `q = state.order_units`
- `zone = state.customer_zones[state.customer_zone_id]`
- `eta_after = max(0, state.planned_eta_hours)`
- `late_hours = max(0, eta_after - zone.sla_deadline_hours)`

#### 6.1 EXPEDITE
- `direct = q * selected_carrier.cost_per_unit * cost_policy.expedite_multiplier`

#### 6.2 TRANSFER
- `direct = transfer_fixed_fee + q * transfer_unit_cost + q * destination_warehouse.operating_cost_per_unit`

#### 6.3 COMPENSATE
- `direct = q * compensation_per_unit`
- `effective_penalty_rate = zone.sla_penalty_per_hour - penalty_relief_per_hour`
- `penalty = late_hours * q * effective_penalty_rate`

#### 6.4 NO_ACTION
- `direct = 0`
- `penalty = late_hours * q * zone.sla_penalty_per_hour`

#### 6.5 EXPEDITE / TRANSFER 通用 penalty
- `penalty = late_hours * q * zone.sla_penalty_per_hour`

#### 6.6 总成本
- `total_cost = direct_action_cost + sla_lateness_penalty`

#### 6.7 breakdown
`last_cost_breakdown` 必须至少包含：
- `direct_action_cost`
- `sla_lateness_penalty`
- `total_cost`
- `eta_after_action`
- `late_hours`

---

### Step 7 — 实现 `to_prompt_context()`
返回类型：**JSON string**

要求：
- 用固定 dict layout
- 顶层 key 顺序必须与 SPEC 一致
- entity list 按 `id` 排序
- 使用 `json.dumps(..., ensure_ascii=False, indent=2)`
- 不包含：
  - `oracle_cost`
  - `optimal_action`
  - `optimal_action_set`
  - hidden payoff
  - uploaded csv 的预计算 cost

建议签名：
```python
    def to_prompt_context(self, allowed_operational_actions: list[dict] | None = None) -> str:
```

---

### Step 8 — 实现 `case_translation.py`
作用：将 legacy narrative case bank 翻译为 canonical translated case。

每个 translated case 必须包含：
- `case_id`
- `baseline_path`
- `state_patches`
- `candidate_operational_actions`
- `oracle_cost`
- `optimal_action_set`
- `optimal_action`
- optional `supervisor_metadata`

#### 8.1 关键翻译规则
- `Approve` -> 一个 canonical operational action
- `Alternative` -> 一个 canonical override action
- `Verify` -> 不进 `ActionType`，只保留在 `supervisor_metadata`
- twin runtime 只处理 resolved operational action

#### 8.2 tie-breaking
先算全部 feasible action cost，再：
1. 取最低 `total_cost`
2. 若并列，取最低 `sla_lateness_penalty`
3. 若并列，取最低 `direct_action_cost`
4. 若仍并列，优先级：
   - `EXPEDITE`
   - `TRANSFER`
   - `COMPENSATE`
   - `NO_ACTION`

输出要求：
- `oracle_cost`
- `optimal_action_set`
- 单一 `optimal_action`

---

## 4. 必须通过的测试（Tests Checklist）

## A. Baseline / initialization
- [ ] `baseline_network.json` 可成功加载
- [ ] 初始化后 entity 数量严格为 2/2/2/2
- [ ] `active_order` 字段正确映射到 `TwinState`
- [ ] 非法 config 会抛异常

## B. Shock injection
- [ ] `set` patch 正常生效
- [ ] `add` patch 正常生效
- [ ] `multiply` patch 正常生效
- [ ] 重复执行同一 shock 结果一致
- [ ] patch log 被写入 `current_disruptions`

## C. Action validation
- [ ] 不可用 carrier 上 `EXPEDITE` 会报错
- [ ] inventory 不足时 `TRANSFER` 会报错
- [ ] destination 超 capacity 时 `TRANSFER` 会报错
- [ ] `penalty_relief_per_hour >= sla_penalty_per_hour` 时 `COMPENSATE` 会报错
- [ ] `action.units != order_units` 会报错
- [ ] 未 apply_action 先 `compute_total_cost()` 会报错

## D. Action mutation
- [ ] `EXPEDITE` 正确更新 `planned_carrier_id`
- [ ] `EXPEDITE` 正确更新 `planned_eta_hours`
- [ ] `TRANSFER` 正确更新两个 warehouse 库存
- [ ] `TRANSFER` 正确更新 ETA
- [ ] `COMPENSATE` 不改 inventory / carrier
- [ ] `NO_ACTION` 不改 operational state

## E. Cost exactness
- [ ] Mini Example 1 精确等于 `60.0`
- [ ] Mini Example 2 精确等于 `250.0`
- [ ] Mini Example 3 精确等于 `250.0`
- [ ] `NO_ACTION` 对照值精确等于 `300.0`
- [ ] T1 expected costs 完全匹配
- [ ] T2 expected costs 完全匹配
- [ ] T3 expected operational costs 完全匹配

## F. Tie-breaking
- [ ] 两个 action 同 `total_cost` 时，能生成 `optimal_action_set`
- [ ] 并列时按 `sla_lateness_penalty` 再比较
- [ ] 再并列时按 `direct_action_cost` 比较
- [ ] 再并列时按固定优先级比较

## G. Prompt serialization
- [ ] `to_prompt_context()` 返回字符串
- [ ] 字符串可被 `json.loads()` 成功解析
- [ ] 顶层 key 顺序与 SPEC 一致
- [ ] entity 列表按 id 排序
- [ ] 不泄露 oracle fields
- [ ] `allowed_operational_actions` 缺省时输出空列表

## H. Case translation
- [ ] legacy `Verify` 不进入 `ActionType`
- [ ] translated case 能生成 `oracle_cost`
- [ ] translated case 能生成 `optimal_action_set`
- [ ] translated case 能生成单一 `optimal_action`
- [ ] T1/T2/T3 三个示例 JSON 结构完全符合 SPEC

---

## 5. 推荐测试文件结构

```text
tests/
  test_twin_state_costs.py
  test_case_translation.py
```

### `test_twin_state_costs.py` 最少应包含
- `test_initialize_from_config_success()`
- `test_initialize_from_config_invalid_counts()`
- `test_inject_shock_set_add_multiply()`
- `test_apply_action_expedite_success()`
- `test_apply_action_transfer_success()`
- `test_apply_action_compensate_success()`
- `test_apply_action_no_action_success()`
- `test_apply_action_invalid_carrier_unavailable()`
- `test_apply_action_transfer_insufficient_inventory()`
- `test_apply_action_transfer_capacity_exceeded()`
- `test_compute_total_cost_requires_action_first()`
- `test_mini_example_1_expedite()`
- `test_mini_example_2_transfer()`
- `test_mini_example_3_compensate()`
- `test_to_prompt_context_exact_top_level_keys()`
- `test_to_prompt_context_no_oracle_fields()`

### `test_case_translation.py` 最少应包含
- `test_translate_t1_matches_expected_costs()`
- `test_translate_t2_matches_expected_costs()`
- `test_translate_t3_matches_expected_costs()`
- `test_verify_stays_in_supervisor_metadata_only()`
- `test_tie_breaking_returns_optimal_action_set_and_single_optimal_action()`

---

## 6. Claude 实现时的禁止事项（Do Not Do）

- 不要把 `VERIFY` 加入 `ActionType`
- 不要把 uploaded CSV 里的 `c_total_*` 当 runtime 真值
- 不要引入 optimization
- 不要引入 stochastic noise
- 不要扩展到 multi-SKU
- 不要把 TwinState 退化成 dict blob / prompt blob
- 不要让 LLM 生成 numeric ground truth
- 不要改 baseline 数值
- 不要擅自修改 tie-breaking 规则
- 不要改变 `to_prompt_context()` 的输出结构

---

## 7. 完成定义（Definition of Done）

只有当下面全部满足，才算这一轮完成：

- [ ] `baseline_network.json` 已落地且数值锁死
- [ ] `src/twin_state.py` 已实现并可运行
- [ ] `src/case_translation.py` 已实现并可输出 canonical case
- [ ] 所有 mini examples 数值完全一致
- [ ] T1/T2/T3 translation 示例数值完全一致
- [ ] `to_prompt_context()` 输出结构固定
- [ ] tie-breaking 行为固定且可测试
- [ ] 所有单元测试通过

---

## 8. 一句话执行指令（可直接发给 Claude）

请严格按照 `SPEC.md` 和本清单实现 `baseline_network.json`、`src/twin_state.py`、`src/case_translation.py`、以及对应单元测试；不要扩 scope，不要改数值，不要把 `VERIFY` 放进 `ActionType`，所有 ground truth 必须由 deterministic cost function 计算得到。
