# M17 Data Model (reuses connectors.db via M15)
UIElement{element_id,type,bbox,confidence,text,accessibility_id,semantic,
clickable,editable,enabled,visible,focused}. Screen{surface,app,url,window_state,
elements,loading,error_present,provider,captured_at}. Operations are ToolDefs in
the M15 registry (risk explicit; require_verification flag). Replay{workflow_id,
owner,steps[ReplayStep]} — sanitized (password/otp/token/secret -> [REDACTED]).
No new store; execution/approval/evidence via M15.
