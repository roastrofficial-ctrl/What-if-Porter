# PORTER Host Runtime — Implementation-Independent Conformance

These vectors test `PORTER-HOST-RUNTIME/1` and `PORTER-HOST-ADAPTER/1` without
requiring Python, SQLite, filesystem IPC, Docker or a particular process model.

| Vector | Arrangement and action | Required observation |
|---|---|---|
| C1 | chosen attention; no candidates | no CL and no adapter offer |
| C2 | candidate held; Runtime absent | AC remains; no CL, adapter or application effect |
| C3 | chosen attention with valid candidate | canonical validation, then CL, then the exact Collection offered |
| C4 | crash after CL before adapter | same Host custody remains recoverable; no application claim |
| C5 | crash after adapter entry before control return | CL remains; application meaning is ambiguous; later re-offer is permitted |
| C6 | adapter exits or throws | no generic FAILED/RETRY/DONE; CL remains |
| C7 | malformed, mismatched or oversized control | operational rejection only; no application or PORTER fact invented |
| C8 | adapter hangs | no new semantic state; serial implementation may block until operator action |
| C9 | adapter returns control without Return | valid operational return; absence of Return is not failure |
| C10 | application records intention, exits, later lodges Return | Return is ordinary later Lodgement; Runtime need not correlate it |
| C11 | application lodges unrelated Package | ordinary Lodgement without `in_reply_to`; Runtime does not reject or relabel it |
| C12 | application lodges several Packages | each has independent Lodgement; no response-count rule |
| C13 | ten selected, crash during fifth opportunity | first four control returns remain operational observations, five CL facts remain true, five Packages remain Porter custody; no rollback |
| C14 | Runtime restart after returned control | no application completion fact; conforming control state may suppress needless re-offer |
| C15 | loss of Runtime operational state | AC/CL/application truth unchanged; duplicate offer is permitted |
| C16 | Porter restart and candidate projection loss | canonical AC/CL reconstruct candidates; later chosen attention works |
| C17 | both Runtime and application absent while Porter accepts | arrival causes only Porter state; later local start enables attention |
| C18 | irrelevant Kind under local interest policy | no Collection by that attention policy; no payload interpretation |
| C19 | adapter proposes cadence in output | Host cadence remains deployment-owned and unchanged |
| C20 | batches 1, 10 and 100 | batching changes opportunity count only; every CL is independent |
| C21 | candidate order changes | correctness and meaning unchanged; no ordering promise |
| C22 | telemetry deleted or truncated | AC, CL and application state byte-for-byte unchanged |
| C23 | Runtime has no external interface/listener | all Runtime/adapter operations remain possible through local IPC |
| C24 | application mutates offered in-memory value | canonical AC/CL bytes remain unchanged by the interface implementation |
| C25 | one-shot, intermittent, continuous and dormant lifecycle policies | all valid; only chosen visits inspect or collect |

For C5 and C15, an adapter must use application-owned recovery rules if duplicate
opportunity could repeat an effect. The Runtime must not prescribe those rules.

## Reference evidence

The Python suite implements C1–C7, C9–C11, C13–C19 and C22 directly in
`tests/test_host_runtime.py`; existing candidate, custody, generation and restart
tests cover C12, C16, C20, C21, C24 and C25. Slow-adapter pressure observes C8.

The third Host exercises C3, C9, C10, C11 and C23 with the same Runtime and
adapter boundary. The final rebuilt Docker environment passed all 115 tests,
including the 15 focused Runtime tests.
