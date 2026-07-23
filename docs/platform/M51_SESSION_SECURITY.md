# M51 Session Security

Fields: hashed token, user, org, workspace, auth_method, absolute expiry, idle expiry,
session_version, revocation reason, ua_hash optional.

Controls: rotate (old token dead), logout, logout others, revoke on password/membership change.

Raw tokens never logged.
