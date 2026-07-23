# M49.2 Migration Waves

## Wave A (implemented)
- m49.system_health (saathi.tools system_health)
- m49.my_files_list (my_files list)
- m49.list_open_tasks (manage_tasks list)

## Wave B (implemented)
- m49.local_artifact_write
- m49.subprocess_diag (allowlisted argv only)

## Wave C (implemented fixtures)
- m49.connector.gmail.search_messages
- m49.connector.gcal.list_events
- m49.connector.gmail.send_message (approval stub, never sends)

## Deferred
email live send, calendar mutation, browser mutation, deploy, credentials, financial execution, full saathi.tools privileged set
