# Baadar Publication Safety Gate

The gate is a pure pre-publication decision boundary. It accepts injected
callbacks for the existing SaathiOS approval and audit systems; it does not
own an approval registry or an audit store.

Publication fails closed for:

- unknown source, missing licence, or unclear commercial rights;
- required attribution without attribution text;
- unresolved music, font, voice, character, or similarity review;
- user-provided material without permission confirmation;
- required human review without approval;
- missing destination or content hash;
- a duplicate content hash;
- denial/missing approval;
- any request for real publication (only simulation is supported).

Every decision is written through the supplied existing audit callback. Tests
cover original generated, licensed, public-domain, missing licence, unclear
commercial use, missing attribution, duplicate hash, character likeness,
music rights, blocked publication, and approved publication simulation.
Legal review is still required for ambiguous licences, fair-use claims,
territorial restrictions, publicity rights, and material similarity.
