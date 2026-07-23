# M49.3 Final Execution Path Inventory
Generated for HEAD on branch milestone/m49-3-gateway-completion.
## Canonical path
```
API / Agent / CLI / Scheduler / Workflow / Legacy Wrapper
  → ExecutionGateway.execute_registered_tool()
  → ToolExecutionService
  → ToolRegistry + durable idempotency + policy
  → Governed Adapter
  → Canonical Result + Events + Evidence
```
## Registered canonical tools
| tool_id | authority | side_effect | cancellation | availability | classification |
|---|---|---|---|---|---|
| `m49.allowlisted_command` | READ_ONLY | NO_SIDE_EFFECT | HARD_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.connector.browser.inspect_page` | READ_ONLY | NO_SIDE_EFFECT | TIMEOUT_ONLY | ENABLED | CANONICAL |
| `m49.connector.gcal.create_event` | EXTERNAL_MUTATION | EXTERNAL_REVERSIBLE | TIMEOUT_ONLY | ENABLED | CANONICAL |
| `m49.connector.gcal.list_events` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.connector.gcal.read_event` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.connector.github.create_issue` | EXTERNAL_MUTATION | EXTERNAL_REVERSIBLE | TIMEOUT_ONLY | ENABLED | CANONICAL |
| `m49.connector.github.read_pull_request` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.connector.github.read_repository` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.connector.gmail.create_draft` | EXTERNAL_MUTATION | EXTERNAL_REVERSIBLE | TIMEOUT_ONLY | ENABLED | CANONICAL |
| `m49.connector.gmail.read_message` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.connector.gmail.search_messages` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.connector.gmail.send_message` | EXTERNAL_MUTATION | EXTERNAL_IRREVERSIBLE | TIMEOUT_ONLY | ENABLED | CANONICAL |
| `m49.cooperative_cancel` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.echo_readonly` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.financial_advisory_stub` | FINANCIAL_ADVISORY | FINANCIAL_ADVISORY | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.financial_execution_stub` | FINANCIAL_EXECUTION | FINANCIAL_EXECUTION | NOT_CANCELLABLE | PROHIBITED | PROHIBITED |
| `m49.list_blueprints` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.list_open_tasks` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.list_projects` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.list_reminders` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.list_social_connections` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.local_artifact_write` | LOCAL_MUTATION | LOCAL_REVERSIBLE | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.local_note_write` | LOCAL_MUTATION | LOCAL_REVERSIBLE | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.my_files_list` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.performance_report` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.subprocess_diag` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.system_health` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |
| `m49.timeout_demo` | READ_ONLY | NO_SIDE_EFFECT | TIMEOUT_ONLY | ENABLED | CANONICAL |
| `m49.todays_events` | READ_ONLY | NO_SIDE_EFFECT | COOPERATIVE_CANCEL_SUPPORTED | ENABLED | CANONICAL |

## Legacy saathi.tools.execute_tool dispositions
| name | disposition | runtime_reachable | user_input_reachable | migration |
|---|---|---|---|---|
| `ab_ai_chat` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_batch` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_click` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_close` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_eval` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_fill` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_find_text` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_get_text` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_get_url` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_goto` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_open` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_press` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_screenshot` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_snapshot` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ab_status` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `add_event` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `add_reminder` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `applescript` | PROHIBITED | False | yes(if agent) | PROHIBITED |
| `ask_document` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `bilibili_search` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `canteen_query` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `cheap_ask` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `cheap_proxy_status` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `check_animated_video` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `check_email` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `check_messages` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `clean_prose` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `connect_facebook_instagram` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `content_strategy_30day` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `crypto_prices` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `deep_plan` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `deploy_ielts_site` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `dm_sales_converter` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `draft_social_content` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `engagement_booster` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `english_log_mistake` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `english_progress` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `exchange_rate` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `find_community_questions` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `get_mobile_link` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `github_repo` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `hashtag_seo_system` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `list_blueprints` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `list_projects` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `list_reminders` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `list_social_connections` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `look_at_screen` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `mac_close_app` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `mac_open_app` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `mac_run_shortcut` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `mac_type_text` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `make_animated_video` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `make_blog_post` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `make_content` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `make_daily_kit` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `make_flow_prompts` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `make_quote_image` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `make_quote_kit` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `make_quote_video` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `make_talking_yeti` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `make_video` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `manage_tasks` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `ml_add_subscriber` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ml_create_campaign` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ml_create_group` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `ml_get_automation` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `ml_get_subscriber` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `ml_list_automations` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `ml_list_campaigns` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `ml_list_groups` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `ml_list_subscribers` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `ml_stats` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `monthly_analytics_review` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `motivational_quote` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `my_files` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `nepali_progress` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `performance_report` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `plan_project_work` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `post_social_content` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `post_to_all_socials` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `profile_optimizer` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `project_edit_file` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `project_overview` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `project_run` | PROHIBITED | False | yes(if agent) | PROHIBITED |
| `publish_blog` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `publish_to_youtube` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `queue_video` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `reach_doctor` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `read_mac_file` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `read_project_file` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `read_webpage` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `record_feedback` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `register_project` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `remember_fact` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `render_hyperframes_video` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `research` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `rss_feed` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `run_shell` | PROHIBITED | False | yes(if agent) | PROHIBITED |
| `score_prose` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `search_mac_files` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `search_project` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `self_improve` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `self_status` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `send_email` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `send_telegram` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `send_video_to_phone` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `social_dashboard` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `stage_draft` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `system_health` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `teach_nepali` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `todays_content` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `todays_events` | MIGRATED_CANONICAL | True | yes(if agent) | MIGRATED_CANONICAL |
| `trigger_blueprint` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `trigger_n8n_workflow` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `viral_hook_generator` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `web_search` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `what_learned` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `write_file` | DEFERRED_AND_DISABLED | False | yes(if agent) | DEFERRED_AND_DISABLED |
| `youtube_info` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |
| `youtube_subtitles` | LEGACY_BOUNDED | True | yes(if agent) | LEGACY_BOUNDED |

## Entry points
| caller | entry | class | notes |
|---|---|---|---|
| AgentExecutor (saathi.agent) | `execute_tool` | LEGACY_BOUNDED + CANONICAL_WRAPPER | routes migrated via compat; blocks freeform/deferred |
| agent_runtime.gateway_exec | `execute_registered_tool` | CANONICAL | M49 tools |
| ExecutionGateway | `execute_registered_tool` | CANONICAL | mandatory for supported tools |
| CLI tools audit-* | `read-only` | DISCOVERY_ONLY | no execute |
| saathi.tools.system.run_shell | `run_shell` | PROHIBITED | blocked |
| saathi.tools.projects.project_run | `project_run` | PROHIBITED | blocked |
| Browser ab_* | `execute_tool` | DEFERRED_UNSUPPORTED | disabled |
| Deploy tools | `execute_tool` | DEFERRED_UNSUPPORTED | disabled |
| Financial execution | `m49.financial_execution_stub` | PROHIBITED | manifest PROHIBITED |
