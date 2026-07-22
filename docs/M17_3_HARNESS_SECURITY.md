# M17.3 Harness Security
argv-only (no shell=True); sanitized minimal env (no inherited secrets); minimal
PATH; file-root confinement + symlink/traversal rejection; output size cap;
secret-pattern rejection in output; XXE + ZIP-slip verifiers; trust gate (only
approved/trusted execute); source pinning; agents cannot self-promote trust;
source change resets trust; quarantine blocks execution; imported entries stay
untrusted; independent verification (fake success never accepted). Red-team 68/68.
