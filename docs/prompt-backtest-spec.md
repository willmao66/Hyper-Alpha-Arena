# Prompt Backtest Feature Specification

## Overview

Allow users to test prompt modifications against historical AI decisions. Users can:
1. Select historical ModelChat records (buy/sell/hold decisions)
2. Apply text replacement rules to modify prompts
3. Re-run LLM with modified prompts
4. Compare original vs new decisions with P&L context

## Core Workflow

```
1. Select AI Trader → Filter ModelChat records → Check records to backtest
      ↓
2. Load selected records' prompt_snapshot into temporary workspace (cache)
      ↓
3. User operations:
   - Batch replace: find/replace text, show "X records replaced"
   - Manual edit: for unmatched records, edit individually (cache only, not source)
      ↓
4. Preview → Submit backtest task (async background execution)
      ↓
5. View results comparison (with P&L, expandable reasoning details)
```

## Database Design

### Table: prompt_backtest_tasks

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto increment |
| account_id | Integer FK | Related AI Trader |
| wallet_address | String(100) | Wallet address |
| environment | String(20) | testnet/mainnet |
| name | String(200) | Task name (optional) |
| status | String(20) | pending/running/completed/failed |
| total_count | Integer | Total records |
| completed_count | Integer | Completed count |
| failed_count | Integer | Failed count |
| replace_rules | Text | JSON: replacement rules used |
| started_at | Timestamp | Execution start time |
| finished_at | Timestamp | Execution end time |
| error_message | Text | Overall failure reason |
| created_at | Timestamp | Creation time |
| updated_at | Timestamp | Last update time |

### Table: prompt_backtest_items

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto increment |
| task_id | Integer FK | Related task |
| original_decision_log_id | Integer FK | Original AIDecisionLog |
| status | String(20) | pending/running/completed/failed |
| error_message | Text | Individual failure reason |
| --- Original Snapshot --- | | |
| original_operation | String(20) | buy/sell/hold |
| original_symbol | String(20) | Trading symbol |
| original_target_portion | Decimal | Position portion |
| original_reasoning | Text | Original AI reasoning |
| original_decision_json | Text | Original decision JSON |
| original_realized_pnl | Decimal | Original P&L |
| original_decision_time | Timestamp | Original decision time |
| original_prompt_template_name | String(200) | Template name used |
| --- Modified Prompt --- | | |
| modified_prompt | Text | User-modified prompt |
| --- New Decision --- | | |
| new_operation | String(20) | New decision |
| new_symbol | String(20) | New symbol |
| new_target_portion | Decimal | New position portion |
| new_reasoning | Text | New AI reasoning |
| new_decision_json | Text | New decision JSON |
| --- Derived Fields --- | | |
| decision_changed | Boolean | Whether decision changed |
| change_type | String(50) | e.g., buy_to_hold |
| created_at | Timestamp | Creation time |

## Backend API Design

### POST /api/prompt-backtest/tasks
Create a new backtest task.

Request:
```json
{
  "account_id": 1,
  "name": "Test RSI threshold change",
  "items": [
    {
      "decision_log_id": 123,
      "modified_prompt": "..."
    }
  ],
  "replace_rules": [
    {"find": "RSI > 70", "replace": "RSI > 80"}
  ]
}
```

Response:
```json
{
  "task_id": 1,
  "status": "pending",
  "total_count": 20
}
```

### GET /api/prompt-backtest/tasks/{task_id}
Get task status and progress.

Response:
```json
{
  "id": 1,
  "status": "running",
  "total_count": 20,
  "completed_count": 8,
  "failed_count": 1
}
```

### GET /api/prompt-backtest/tasks/{task_id}/results
Get comparison results list.

Response:
```json
{
  "items": [
    {
      "id": 1,
      "original_decision_time": "2025-01-09T10:30:00Z",
      "original_operation": "buy",
      "original_symbol": "BTC",
      "original_realized_pnl": -150.00,
      "new_operation": "hold",
      "decision_changed": true,
      "change_type": "buy_to_hold"
    }
  ],
  "summary": {
    "total": 20,
    "changed": 6,
    "avoided_loss_count": 2,
    "avoided_loss_amount": -280.00,
    "missed_profit_count": 1,
    "missed_profit_amount": 80.00
  }
}
```

### GET /api/prompt-backtest/items/{item_id}
Get single item details (with full reasoning).

Response:
```json
{
  "id": 1,
  "original_reasoning": "...",
  "original_decision_json": "...",
  "new_reasoning": "...",
  "new_decision_json": "...",
  "modified_prompt": "..."
}
```

## Frontend Design

### Entry Point
Add third tab in Attribution Analysis page:
```
TabsList: [Dimension Analysis] [Trade Details] [Prompt Backtest]
```

Reuse existing Account/Environment selectors.

### Components

1. **Record Selector**
   - Reuse ModelChat filtering logic
   - Add checkbox for multi-select
   - Show operation, symbol, P&L, time

2. **Temporary Workspace**
   - Load selected prompts into local state
   - Batch replace input: find/replace fields
   - Show "X records replaced successfully"
   - Click individual record to manually edit
   - All edits are cache only, not affecting source data

3. **Task Submission**
   - Submit button with cost estimate
   - Progress polling after submission
   - Allow closing page, task continues in background

4. **Results Comparison**
   - Table: Time | Original Decision | Original P&L | New Decision | Impact
   - Time column: Convert UTC to local timezone using dayjs
   - Click row to expand reasoning details
   - Summary stats: changed count, avoided loss, missed profit

### Timezone Handling
- Backend stores/returns UTC
- Frontend converts using: `dayjs.utc(time).local().format('YYYY-MM-DD HH:mm')`

## Technical Implementation

### Async Execution
- Use FastAPI BackgroundTasks or separate worker
- Process items one by one
- Update progress after each completion
- Continue on individual failures, record error

### LLM Call
- Get LLM config from Account table (api_key, api_base, model)
- Get system prompt from PromptTemplate
- Reuse existing ai_decision_service logic
- Parse response to extract operation, reasoning, decision JSON

### Error Handling
- Individual item failure: record error, continue next
- Overall task failure: update task status, record error message
- Retry mechanism: optional, can add later

## Implementation Order

1. Database tables and migration script
2. Backend APIs (create task, query status, query results)
3. Async execution logic
4. Frontend Tab entry and record selector
5. Frontend temporary workspace (batch replace + manual edit)
6. Frontend result comparison (with P&L, reasoning details)
7. i18n translations (en/zh)

## Future Enhancements

- Support regex replacement
- AI-assisted prompt modification
- Compare multiple modification schemes
- Retry failed items
- Export results to CSV
