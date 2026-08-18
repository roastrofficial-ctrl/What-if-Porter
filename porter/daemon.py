from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from .protocol import atomic_write, validate
from .tickets import event, ticket_for_package
from .lodgement import atomic_json, recover
from .carriage import (
    accept,
    acceptance_evidence,
    note_attempt,
    recover_acceptances,
    retain_evidence,
)
from .custody import recover_collections
from .introduction import Admission, AdmissionRefused
from .ceremony import (
    CeremonyService,
    CeremonyRefused,
    MAX_WIRE_BYTES as MAX_CEREMONY_WIRE_BYTES,
)


class SimulatedCarriageCrash(RuntimeError):
    """Generation IV experiment: transport returned, evidence was not retained."""


class RemoteRefusal(RuntimeError):
    def __init__(self, evidence):
        super().__init__(evidence.get("reason", "CORRESPONDENCE_NOT_ADMITTED"))
        self.evidence = evidence


def wire_size_allowed(length, maximum):
    return isinstance(length, int) and 0 <= length <= maximum


class Porter:
    def __init__(
        self,
        identity,
        ipc,
        routes,
        transport=None,
        relationships=None,
        require_introductions=False,
        max_wire_bytes=262144,
        native_private_key=None,
        native_rendezvous=None,
        native_listen=None,
        continuity_authorities=None,
    ):
        self.identity = identity
        self.ipc = Path(ipc)
        self.routes = routes
        self.running = True
        self.transport = transport or self._network_deposit
        self.crash_after_response_once = False
        self.max_wire_bytes = max_wire_bytes
        self.ipc.mkdir(parents=True, exist_ok=True)
        self.ipc.chmod(0o777)
        for name in (
            "outgoing",
            "inbox",
            "collected",
            "receipts",
            "refused",
            "acceptances",
            "carriage",
        ):
            folder = self.ipc / name
            folder.mkdir(parents=True, exist_ok=True)
            folder.chmod(0o777)
        for lock in (
            (self.ipc / "tickets").glob("CT-*.lock")
            if (self.ipc / "tickets").exists()
            else []
        ):
            lock.chmod(0o666)
        for claimed in (self.ipc / "outgoing").glob("PKG-*.carrying"):
            target = claimed.with_suffix(".json")
            if not target.exists():
                claimed.rename(target)
        recover(self.ipc)
        recover_acceptances(self.ipc)
        recover_collections(self.ipc)
        self.admission = Admission(
            self.ipc, self.identity, relationships or {}, require_introductions
        )
        self.ceremonies = CeremonyService(
            self.ipc, self.identity, self.admission, relationships or {}
        )
        self.native = None
        if native_private_key and native_listen:
            from .native import NativeCarriage

            self.native = NativeCarriage(
                self,
                native_private_key,
                native_rendezvous or {},
                native_listen,
                continuity_authorities=continuity_authorities or {},
            )

    def deposit(self, value, fail_after=None, admission=None):
        validate(value)
        if value["to"] != self.identity:
            raise ValueError("recipient Porter refuses this destination")
        if value["expires"] <= int(time.time()):
            raise ValueError("Package expired before deposit")
        with self.admission.authorize(value, admission):
            acceptance, repeated = accept(self.ipc, self.identity, value)
        if fail_after == "acceptance":
            raise RuntimeError("interrupted after durable remote acceptance")
        # AC is already the immutable account of first acceptance. Repeating
        # that fact in an unbounded diagnostic journal consumed a quarter of
        # dormant-custody storage without adding knowledge. A repeated arrival
        # remains useful operational narration because it explains a retry.
        if repeated:
            self.record(
                "PACKAGE_ACCEPTED_AGAIN",
                value["package"],
                {
                    "from": value["from"],
                    "kind": value["kind"],
                    "acceptance": acceptance["acceptance"],
                },
            )
        if value.get("in_reply_to"):
            ticket = ticket_for_package(self.ipc, value["in_reply_to"])
            if ticket:
                event(self.ipc, ticket, "RETURN_HELD", {"return": value["package"]})
        if fail_after == "evidence":
            raise RuntimeError("acceptance evidence prevented from returning")
        return acceptance_evidence(acceptance)

    def _network_deposit(self, value, route):
        body = {"package": value, "admission": self.admission.outbound_proof(value)}
        request = Request(
            route.rstrip("/") + "/deposit",
            json.dumps(body, separators=(",", ":")).encode(),
            {"Content-Type": "application/json"},
            method="POST",
        )
        try:
            return json.load(urlopen(request, timeout=10))
        except HTTPError as exc:
            try:
                evidence = json.load(exc)
            except Exception:
                raise
            if evidence.get("kind") == "REFUSE":
                raise RemoteRefusal(evidence)
            raise

    def _network_ceremony(self, value, evidence, route):
        body = json.dumps(
            {"ceremony": value, "evidence": evidence}, separators=(",", ":")
        ).encode()
        request = Request(
            route.rstrip("/") + "/ceremony",
            body,
            {"Content-Type": "application/json"},
            method="POST",
        )
        try:
            return json.load(urlopen(request, timeout=10))
        except HTTPError as exc:
            try:
                evidence = json.load(exc)
            except Exception:
                raise
            if evidence.get("kind") == "CEREMONY_REFUSE":
                raise RemoteRefusal(evidence)
            raise

    def carry(self):
        while self.running:
            recover(self.ipc)
            if self.native:
                self.native.tick()
                time.sleep(0.05)
                continue
            for claimed in sorted((self.ipc / "outgoing").glob("PKG-*.carrying")):
                claimed.rename(claimed.with_suffix(".json"))
            for path in sorted((self.ipc / "outgoing").glob("PKG-*.json")):
                try:
                    self.carry_one(path)
                except SimulatedCarriageCrash:
                    raise
                except Exception as exc:
                    self.record(
                        "REMOTE_ACCEPTANCE_UNKNOWN", path.stem, {"reason": str(exc)}
                    )
            for path in sorted(
                (self.ipc / "ceremonies" / "outgoing").glob("CM-*.json")
            ):
                try:
                    self.carry_ceremony_one(path)
                except Exception as exc:
                    self.record(
                        "CEREMONY_RESULT_UNKNOWN", path.stem, {"reason": str(exc)}
                    )
            time.sleep(0.05)

    def _retain_native_acceptance(self, receipt):
        knowledge = retain_evidence(self.ipc, receipt)
        package_id = receipt["package"]
        (self.ipc / "outgoing" / f"{package_id}.awaiting").unlink(missing_ok=True)
        self.record(
            "REMOTE_ACCEPTANCE_KNOWN",
            package_id,
            {
                "recipient": receipt["recipient"],
                "acceptance": receipt["acceptance"],
                "carriage": "PORTER-CARRIAGE/1",
            },
        )
        ticket = ticket_for_package(self.ipc, package_id)
        if ticket:
            event(
                self.ipc,
                ticket,
                "REMOTE_ACCEPTANCE_KNOWN",
                {"recipient": receipt["recipient"], "acceptance": receipt["acceptance"]},
            )
        return knowledge

    def _retain_native_refusal(self, evidence):
        package_id = evidence["package"]
        atomic_json(self.ipc / "refused" / f"{package_id}.json", evidence)
        (self.ipc / "outgoing" / f"{package_id}.awaiting").unlink(missing_ok=True)

    def _retain_native_ceremony(self, result):
        retained = self.ceremonies.retain_result(result)
        identity = result["ceremony"]
        (self.ipc / "ceremonies" / "outgoing" / f"{identity}.awaiting").unlink(
            missing_ok=True
        )
        return retained

    def carry_ceremony_one(self, path, fail_after=None):
        path = Path(path)
        claimed = path.with_suffix(".carrying")
        try:
            path.rename(claimed)
        except FileNotFoundError:
            return
        item = json.loads(claimed.read_text())
        value = item["ceremony"]
        if fail_after == "attempt":
            raise RuntimeError("interrupted after ceremony carriage attempt")
        try:
            result = self._network_ceremony(
                value, item["evidence"], self.routes[value["to"]]
            )
            if fail_after == "response":
                raise RuntimeError("interrupted before ceremony result retention")
            if result.get("state") == "PENDING_PREDECESSOR":
                claimed.rename(path)
                return result
            retained = self.ceremonies.retain_result(result)
            claimed.unlink(missing_ok=True)
            return retained
        except RemoteRefusal as refusal:
            claimed.unlink(missing_ok=True)
            return refusal.evidence
        except Exception:
            if claimed.exists():
                claimed.rename(path)
            raise

    def carry_one(self, path, fail_after=None):
        path = Path(path)
        claimed = path.with_suffix(".carrying")
        try:
            path.rename(claimed)
        except FileNotFoundError:
            return
        value = validate(json.loads(claimed.read_text()))
        note_attempt(self.ipc, value["package"])
        if fail_after == "attempt":
            raise RuntimeError("interrupted after carriage attempt began")
        try:
            receipt = self.transport(value, self.routes[value["to"]])
            marker = self.ipc / "generation4.acceptance-evidence-lost"
            if self.crash_after_response_once and not marker.exists():
                marker.write_text(value["package"] + "\n")
                raise SimulatedCarriageCrash(
                    "recipient accepted; sender crashed before retaining evidence"
                )
            if fail_after == "response":
                raise RuntimeError("interrupted before acceptance evidence retention")
            knowledge = retain_evidence(self.ipc, receipt)
            self.record(
                "REMOTE_ACCEPTANCE_KNOWN",
                value["package"],
                {
                    "recipient": receipt["recipient"],
                    "acceptance": receipt["acceptance"],
                },
            )
            ticket = ticket_for_package(self.ipc, value["package"])
            if ticket:
                event(
                    self.ipc,
                    ticket,
                    "REMOTE_ACCEPTANCE_KNOWN",
                    {
                        "recipient": receipt["recipient"],
                        "acceptance": receipt["acceptance"],
                    },
                )
            if fail_after == "retention":
                raise RuntimeError("interrupted after acceptance evidence retention")
            claimed.unlink(missing_ok=True)
            return knowledge
        except RemoteRefusal as refusal:
            atomic_json(
                self.ipc / "refused" / f"{value['package']}.json", refusal.evidence
            )
            claimed.unlink(missing_ok=True)
            return refusal.evidence
        except Exception:
            if (
                not (self.ipc / "receipts" / f"{value['package']}.json").exists()
                and claimed.exists()
            ):
                claimed.rename(path)
            elif (self.ipc / "receipts" / f"{value['package']}.json").exists():
                claimed.unlink(missing_ok=True)
            raise

    def record(self, event_type, package_id, details=None):
        value = {
            "event": event_type,
            "at_ms": int(time.time() * 1000),
            "porter": self.identity,
            "package": package_id,
            **({"details": details} if details else {}),
        }
        with (self.ipc / "porter-events.jsonl").open("a") as stream:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps(value, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            fcntl.flock(stream, fcntl.LOCK_UN)


def handler(porter):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value):
            raw = json.dumps(value, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            (
                self.reply(
                    200, {"ok": True, "service": "Porter", "identity": porter.identity}
                )
                if self.path == "/health"
                else self.reply(404, {"error": "unknown Porter operation"})
            )

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if self.path == "/ceremony":
                if not wire_size_allowed(length, MAX_CEREMONY_WIRE_BYTES):
                    return self.reply(
                        413,
                        {
                            "vocabulary": "PORTER-CEREMONY/1",
                            "kind": "CEREMONY_REFUSE",
                            "reason": "CEREMONY_NOT_ADMITTED",
                        },
                    )
                try:
                    body = json.loads(self.rfile.read(length))
                    self.reply(
                        202,
                        porter.ceremonies.receive(
                            body.get("ceremony"), body.get("evidence")
                        ),
                    )
                except CeremonyRefused as exc:
                    self.reply(
                        403,
                        {
                            "vocabulary": "PORTER-CEREMONY/1",
                            "kind": "CEREMONY_REFUSE",
                            "reason": exc.public_reason,
                        },
                    )
                except Exception as exc:
                    self.reply(
                        400,
                        {
                            "vocabulary": "PORTER-CEREMONY/1",
                            "kind": "CEREMONY_REFUSE",
                            "reason": str(exc),
                        },
                    )
                return
            if self.path != "/deposit":
                return self.reply(404, {"error": "unknown Porter operation"})
            if not wire_size_allowed(length, porter.max_wire_bytes):
                self.close_connection = True
                return self.reply(
                    413,
                    {
                        "protocol": "PORTER/1",
                        "kind": "REFUSE",
                        "state": "POLICY_REFUSED_BEFORE_ACCEPTANCE",
                        "reason": "CORRESPONDENCE_NOT_ADMITTED",
                    },
                )
            try:
                body = json.loads(self.rfile.read(length))
                wrapped = isinstance(body, dict) and "package" in body
                self.reply(
                    202,
                    porter.deposit(
                        body["package"] if wrapped else body,
                        admission=body.get("admission") if wrapped else None,
                    ),
                )
            except AdmissionRefused as exc:
                self.reply(
                    403,
                    {
                        "protocol": "PORTER/1",
                        "kind": "REFUSE",
                        "state": "POLICY_REFUSED_BEFORE_ACCEPTANCE",
                        "reason": exc.public_reason,
                    },
                )
            except Exception as exc:
                self.reply(
                    400,
                    {
                        "protocol": "PORTER/1",
                        "kind": "REFUSE",
                        "state": "INVALID_ENVELOPE",
                        "reason": str(exc),
                    },
                )

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", required=True)
    parser.add_argument("--ipc", default="/ipc")
    parser.add_argument("--listen", default="0.0.0.0:7070")
    parser.add_argument("--routes", default="{}")
    parser.add_argument(
        "--experiment-crash-before-acceptance-evidence", action="store_true"
    )
    parser.add_argument("--relationships", default="{}")
    parser.add_argument("--require-introductions", action="store_true")
    parser.add_argument("--max-wire-bytes", type=int, default=262144)
    parser.add_argument("--native-listen")
    parser.add_argument("--native-private-key")
    parser.add_argument("--native-rendezvous", default="{}")
    parser.add_argument("--continuity-authorities", default="{}")
    args = parser.parse_args()
    porter = Porter(
        args.identity,
        args.ipc,
        json.loads(args.routes),
        relationships=json.loads(args.relationships),
        require_introductions=args.require_introductions,
        max_wire_bytes=args.max_wire_bytes,
        native_private_key=args.native_private_key,
        native_rendezvous=json.loads(args.native_rendezvous),
        native_listen=args.native_listen,
        continuity_authorities=json.loads(args.continuity_authorities),
    )
    porter.crash_after_response_once = args.experiment_crash_before_acceptance_evidence
    threading.Thread(target=porter.carry, daemon=True).start()
    if porter.native:
        porter.native.serve_forever()
    else:
        host, port = args.listen.rsplit(":", 1)
        ThreadingHTTPServer((host, int(port)), handler(porter)).serve_forever()


if __name__ == "__main__":
    main()
