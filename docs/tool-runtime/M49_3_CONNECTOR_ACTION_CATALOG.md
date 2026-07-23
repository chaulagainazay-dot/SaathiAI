# M49.3 Connector Action Catalog

Actions: 11
Read: 7
Mutation: 4
Mode: DRY_RUN_ONLY
Generic executor: ABSENT

| tool_id | authority | side_effect | approval |
|---|---|---|---|
| `m49.connector.browser.inspect_page` | READ_ONLY | NO_SIDE_EFFECT | NO_APPROVAL_REQUIRED |
| `m49.connector.gcal.create_event` | EXTERNAL_MUTATION | EXTERNAL_REVERSIBLE | EXPLICIT_APPROVAL_REQUIRED |
| `m49.connector.gcal.list_events` | READ_ONLY | NO_SIDE_EFFECT | NO_APPROVAL_REQUIRED |
| `m49.connector.gcal.read_event` | READ_ONLY | NO_SIDE_EFFECT | NO_APPROVAL_REQUIRED |
| `m49.connector.github.create_issue` | EXTERNAL_MUTATION | EXTERNAL_REVERSIBLE | EXPLICIT_APPROVAL_REQUIRED |
| `m49.connector.github.read_pull_request` | READ_ONLY | NO_SIDE_EFFECT | NO_APPROVAL_REQUIRED |
| `m49.connector.github.read_repository` | READ_ONLY | NO_SIDE_EFFECT | NO_APPROVAL_REQUIRED |
| `m49.connector.gmail.create_draft` | EXTERNAL_MUTATION | EXTERNAL_REVERSIBLE | EXPLICIT_APPROVAL_REQUIRED |
| `m49.connector.gmail.read_message` | READ_ONLY | NO_SIDE_EFFECT | NO_APPROVAL_REQUIRED |
| `m49.connector.gmail.search_messages` | READ_ONLY | NO_SIDE_EFFECT | NO_APPROVAL_REQUIRED |
| `m49.connector.gmail.send_message` | EXTERNAL_MUTATION | EXTERNAL_IRREVERSIBLE | EXPLICIT_APPROVAL_REQUIRED |
