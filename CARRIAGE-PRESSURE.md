# PORTER 1.3 — Carriage Pressure Record

HTTP/JSON remains labelled **HOST INTEGRATION TRANSPORT**. Ceremony did not
replace it, but made its assumptions unusually visible.

## Pressure exposed

- A stable Porter identity still resolves through a configured DNS name, port
  and `/ceremony` endpoint. HTTP makes identity look like location even though
  PORTER does not want that equivalence.
- The recipient must run a listener and the origin initiates a connection.
  Hosts remain listener-free; Porters do not.
- Request/response coupling tempts callers to confuse an HTTP response with
  durable ceremony knowledge. PORTER must separately retain the result, and a
  lost response requires exact retry.
- Timeout and connection errors collapse recipient absence, DNS failure,
  carriage delay and response loss into transport ambiguity. CM and recipient
  facts, not exceptions, determine protocol knowledge.
- HTTP status codes expose a grammar distinction between malformed, oversized
  and policy-refused ceremony even though all authority failures share one
  public ceremony reason.
- Replacement possession material currently travels inside laboratory JSON.
  HMAC authenticates it but provides no confidentiality. Real carriage needs a
  protected peer channel or encrypted ceremony object; HTTP alone does not
  supply that property in this experiment.
- Separate `/deposit` and `/ceremony` endpoints correctly expose different
  admission boundaries, but also make protocol category depend on URL routing.

## Semantics that helped

- `Content-Length` permits an oversized ceremony to be refused before body
  acquisition.
- Stateless request repetition fits stable CM identity and exact result repair.
- A bounded response carries recipient evidence without implying Host
  collection.
- Existing route and failure scaffolding let the ceremony model be tested
  independently of a new carriage substrate.

HTTP therefore receives no acquittal, but it did not prevent the protocol result.
The experiment increased the reasons Porters need their own substrate while
adding none for Hosts to regain listeners.
