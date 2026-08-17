from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from porter.custody import collect_package
from porter.daemon import Porter, wire_size_allowed
from porter.introduction import AdmissionRefused, establish_from_claim, proof
from porter.protocol import package


def terms(**changes):
    value = {"kinds": ["hdbe.call"], "max_package_bytes": 4096, "max_outstanding_packages": 2,
             "max_outstanding_bytes": 8192, "expires_at": int(time.time()) + 3600, "secret": "correct-horse-battery-staple"}
    value.update(changes); return value


class IntroductionsUnderAttack(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.config={"find-me":terms()};self.porter=Porter("harmonicdb",self.root,{},relationships=self.config,require_introductions=True)
    def tearDown(self):self.temporary.cleanup()
    def value(self,sender="find-me",kind="hdbe.call",payload=None):return package(sender,"harmonicdb",kind,payload or {"operation":"observe"},ttl=3600)
    def admitted(self,value):return self.porter.deposit(value,admission=proof(self.config["find-me"]["secret"],value))
    def facts(self):return list((self.root/"acceptances").glob("PKG-*.json"))

    def test_unknown_spoofed_wrong_kind_and_bad_proof_never_cross_ac(self):
        attacks=[self.value("stranger"),self.value(kind="admin.erase"),self.value()]
        evidence=[None,proof(self.config["find-me"]["secret"],attacks[1]),{"vocabulary":"PORTER-INTRODUCTION/1","proof":"forged"}]
        reasons=[]
        for value,item in zip(attacks,evidence):
            with self.assertRaises(AdmissionRefused) as refusal:self.porter.deposit(value,admission=item)
            reasons.append(refusal.exception.public_reason)
        self.assertEqual(reasons,["CORRESPONDENCE_NOT_ADMITTED"]*3)
        self.assertEqual(self.facts(),[]);self.assertEqual(list((self.root/"inbox").glob("*.json")),[])

    def test_same_identity_repeats_one_ac_but_changed_bytes_are_rejected(self):
        value=self.value();first=self.admitted(value);second=self.admitted(value)
        self.assertEqual(first["acceptance"],second["acceptance"]);self.assertEqual(len(self.facts()),1)
        changed={**value,"payload":{"operation":"erase"}}
        with self.assertRaises(ValueError):self.porter.deposit(changed,admission=proof(self.config["find-me"]["secret"],changed))
        self.assertEqual(len(self.facts()),1)

    def test_exact_historical_ac_replays_after_introduction_expiry(self):
        now=int(time.time());root=self.root/"replay";config={"find-me":terms(expires_at=now+1)};porter=Porter("harmonicdb",root,{},relationships=config,require_introductions=True)
        value=package("find-me","harmonicdb","hdbe.call",{},ttl=3600);first=porter.deposit(value,admission=proof(config["find-me"]["secret"],value))
        restarted=Porter("harmonicdb",root,{},relationships=config,require_introductions=True)
        restarted.admission.now=lambda:now+2;replay=restarted.deposit(value)
        self.assertEqual(replay["acceptance"],first["acceptance"]);self.assertEqual(len(list((root/"acceptances").glob("*.json"))),1)

    def test_kind_size_expiry_and_custody_budget_precede_ac(self):
        first=self.value(payload={"body":"a"*100});second=self.value(payload={"body":"b"*100});third=self.value(payload={"body":"c"*100})
        self.admitted(first);self.admitted(second)
        with self.assertRaises(AdmissionRefused):self.admitted(third)
        self.assertEqual(len(self.facts()),2)
        collect_package(self.root,first["package"],"harmonicdb")
        self.admitted(third);self.assertEqual(len(self.facts()),3)
        oversized=self.value(payload={"body":"x"*5000})
        with self.assertRaises(AdmissionRefused):self.admitted(oversized)
        expired_config={"find-me":terms(expires_at=int(time.time())-1)}
        expired=Porter("other",self.root/"expired",{},relationships=expired_config,require_introductions=True)
        value=package("find-me","other","hdbe.call",{},ttl=60)
        with self.assertRaises(AdmissionRefused):expired.deposit(value,admission=proof(expired_config["find-me"]["secret"],value))

    def test_ten_thousand_strangers_create_no_per_attempt_recipient_state(self):
        before={p.relative_to(self.root) for p in self.root.rglob("*") if p.is_file()}
        for index in range(10_000):
            value=self.value(f"stranger-{index}")
            with self.assertRaises(AdmissionRefused):self.porter.deposit(value)
        after={p.relative_to(self.root) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after,before);self.assertEqual(self.facts(),[])

    def test_standing_and_budget_recover_without_live_claim_provider(self):
        value=self.value();self.admitted(value)
        restarted=Porter("harmonicdb",self.root,{},relationships=self.config,require_introductions=True)
        second=self.value();restarted.deposit(second,admission=proof(self.config["find-me"]["secret"],second))
        third=self.value()
        with self.assertRaises(AdmissionRefused):restarted.deposit(third,admission=proof(self.config["find-me"]["secret"],third))
        self.assertEqual(len(self.facts()),2)

    def test_claim_provider_supplies_identity_but_local_policy_supplies_terms(self):
        claim={"passport":"signed-evidence"};calls=[]
        def passport_adapter(evidence):calls.append(evidence);return {"subject":"known-service","issuer":"technical-passport:BPA/1"}
        fact=establish_from_claim(self.root/"claim", "harmonicdb", claim, passport_adapter, "capability", terms())
        self.assertEqual(fact["sender"],"known-service");self.assertEqual(fact["terms"]["kinds"],["hdbe.call"]);self.assertEqual(calls,[claim])
        again=establish_from_claim(self.root/"claim", "harmonicdb", claim, passport_adapter, "capability", terms())
        self.assertEqual(again["introduction"],fact["introduction"])
        with self.assertRaises(AdmissionRefused):establish_from_claim(self.root/"bad", "harmonicdb", {"blob":"x"*17000}, passport_adapter, "x", terms())
        with self.assertRaises(AdmissionRefused):establish_from_claim(self.root/"down", "harmonicdb", claim, lambda _e: (_ for _ in ()).throw(OSError()), "x", terms())

    def test_competing_admissions_cannot_cross_one_relationship_allowance(self):
        root=self.root/"concurrent";cfg={"find-me":terms(max_outstanding_packages=10)};porter=Porter("harmonicdb",root,{},relationships=cfg,require_introductions=True)
        def attempt(index):
            value=package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=60)
            try:porter.deposit(value,admission=proof(cfg["find-me"]["secret"],value));return True
            except AdmissionRefused:return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(40)))
        self.assertEqual(sum(results),10);self.assertEqual(len(list((root/"acceptances").glob("*.json"))),10)

    def test_wire_size_is_refused_before_body_or_ac(self):
        self.assertFalse(wire_size_allowed(100_000,1024));self.assertFalse(wire_size_allowed(-1,1024));self.assertTrue(wire_size_allowed(1024,1024))


if __name__=="__main__":unittest.main()
