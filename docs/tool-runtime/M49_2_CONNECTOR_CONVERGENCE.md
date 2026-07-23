# M49.2 Connector Convergence

No generic `connector.execute_anything`.

Action-specific fixtures:
- gmail.search_messages READ_ONLY fixture
- gcal.list_events READ_ONLY fixture
- gmail.send_message EXTERNAL_IRREVERSIBLE approval-gated stub (sent=false)

Live network mutation not authorized. Secret policy BROKERED_CLIENT_ONLY.
