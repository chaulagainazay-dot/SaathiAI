# Replace Decision

Order replacement is explicitly unsupported in T-NEXT-4.1. `replace_order`
fails closed with `REPLACE_UNSUPPORTED`; callers must reconcile and use the
normal cancel/propose flow.
