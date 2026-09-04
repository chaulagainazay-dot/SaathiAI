# INTERRUPTION_CONTRACT

API: `voiceSession.interrupt(reason)`

Reasons: USER_MIC_REQUEST, USER_CANCEL, ROUTE_CHANGE, NEW_ASSISTANT_RESPONSE, SESSION_CLOSE, ERROR, CLAIM_PREEMPT, LOGOUT

Behavior V-NEXT-1:

- Stops output always
- Releases input only on ROUTE_CHANGE / SESSION_CLOSE / LOGOUT / ERROR
- USER_MIC_REQUEST stops output then allows new input (manual interrupt)
- **Not** acoustic barge-in / VAD

Future VAD should call the same interrupt API.
