# M49.3 Cancellation Completion Matrix

| tool_id | cancellation | authority |
|---|---|---|
| `m49.allowlisted_command` | HARD_CANCEL_SUPPORTED | READ_ONLY |
| `m49.connector.browser.inspect_page` | TIMEOUT_ONLY | READ_ONLY |
| `m49.connector.gcal.create_event` | TIMEOUT_ONLY | EXTERNAL_MUTATION |
| `m49.connector.gcal.list_events` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.connector.gcal.read_event` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.connector.github.create_issue` | TIMEOUT_ONLY | EXTERNAL_MUTATION |
| `m49.connector.github.read_pull_request` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.connector.github.read_repository` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.connector.gmail.create_draft` | TIMEOUT_ONLY | EXTERNAL_MUTATION |
| `m49.connector.gmail.read_message` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.connector.gmail.search_messages` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.connector.gmail.send_message` | TIMEOUT_ONLY | EXTERNAL_MUTATION |
| `m49.cooperative_cancel` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.echo_readonly` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.financial_advisory_stub` | COOPERATIVE_CANCEL_SUPPORTED | FINANCIAL_ADVISORY |
| `m49.list_blueprints` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.list_open_tasks` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.list_projects` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.list_reminders` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.list_social_connections` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.local_artifact_write` | COOPERATIVE_CANCEL_SUPPORTED | LOCAL_MUTATION |
| `m49.local_note_write` | COOPERATIVE_CANCEL_SUPPORTED | LOCAL_MUTATION |
| `m49.my_files_list` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.performance_report` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.subprocess_diag` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.system_health` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |
| `m49.timeout_demo` | TIMEOUT_ONLY | READ_ONLY |
| `m49.todays_events` | COOPERATIVE_CANCEL_SUPPORTED | READ_ONLY |

UNKNOWN is not permitted for supported tools.
