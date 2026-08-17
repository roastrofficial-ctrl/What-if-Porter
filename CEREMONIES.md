# PORTER Standing Ceremony/1

Standing ceremony is durable security evidence addressed to a Porter, not
correspondence addressed through that Porter to a Host. It exists because the
operational authority under an Introduction cannot safely be the sole authority
for changing that Introduction.

## Ceremonial grant

The recipient Porter first establishes an immutable `CG-…` ceremonial grant for
one remote Porter identity. The grant bounds:

- the relationship whose standing may be reconsidered;
- maximum Kinds, Package size, custody count and custody bytes of successors;
- maximum successor expiry;
- whether termination is permitted;
- outstanding out-of-order ceremonies;
- total standing changes; and
- ceremonial-authority expiry.

Possession material is stored separately with mode `0600`. A grant is neither a
Technical Passport claim nor an Introduction: it gives no authority to create
ordinary AC. Technical Passport may justify its establishment offline, but
PORTER owns the local grant and ordinary Package admission never consults it.

The grant is deliberately finite. Theft of operational possession cannot forge
ceremony. Theft of ceremonial possession can replace or terminate standing only
within the grant's relationship, term and use bounds. It cannot widen terms,
reset custody, target another Porter, or establish a recursive ceremony grant.
Compromise beyond that root requires local recipient intervention or expiry.

## Ceremony journey

```text
origin Porter                         recipient Porter
     │ CM lodged                           │
     │ durable retry intent                │
     ├──────── ceremony + proof ──────────>│ verify CG
     │                                     │ retain exact evidence
     │                                     │ prepare candidate IN
     │                                     │ publish recipient-local SC
     │<──────── ceremony result ───────────┤
     │ retain result                       │
     │ update outbound knowledge           │
```

`CM-…` has stable identity and canonical bytes. Origin lodgement makes the
origin Porter responsible for retrying its security evidence. At the recipient,
valid evidence is retained by that same identity. Exact duplicates reproduce
the result; different bytes under one identity are hostile.

Ceremony does not use ordinary LG, AC or CL. LG and AC describe Host-directed
correspondence responsibility; CL describes Host collection. Here the
computational recipient is the Porter itself, evaluation is Porter security
work, and no Host has anything to collect. Forcing ceremony through AC/CL would
invent Host custody and violate silence. The only authority-changing threshold
is still SC.

## Ordering and knowledge

Every ceremony names the exact predecessor IN and a preselected successor IN.
If the predecessor is unknown, valid bounded evidence is held pending. When an
earlier ceremony makes that predecessor current, the recipient drains the
pending successor. If the predecessor is historical and already has another
transition, the ceremony is stale and cannot move standing backward. The unique
predecessor transition slot prevents forks without distributed consensus.

An absent recipient leaves the origin's CM durable and its result unknown.
Retry repairs knowledge. A response lost after SC is safe: exact replay finds
the SC caused by that CM and reproduces the same result. Until the origin retains
that result it knows only that it lodged and attempted ceremony, not that remote
standing changed.

The origin's outbound credential knowledge is explicitly separate from its own
recipient-local inbound standing. An APPLIED result updates the former. It does
not fabricate a reciprocal SC.
