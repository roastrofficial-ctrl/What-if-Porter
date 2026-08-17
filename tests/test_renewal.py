from __future__ import annotations

import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from porter.custody import collect_package
from porter.daemon import Porter
from porter.introduction import AdmissionRefused, StandingChangeInterrupted, proof, relationship_id
from porter.protocol import package


OLD="stolen-old-capability";NEW="replacement-capability"
def terms(**changes):
    value={"kinds":["hdbe.call"],"max_package_bytes":4096,"max_outstanding_packages":4,"max_outstanding_bytes":16384,"expires_at":int(time.time())+3600,"secret":OLD,"authority":"technical-passport:offline-claim"}
    value.update(changes);return value


class CapabilityCompromiseAndRenewal(unittest.TestCase):
    def setUp(self):self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name);self.config={"find-me":terms()};self.porter=Porter("harmonicdb",self.root,{},relationships=self.config,require_introductions=True)
    def tearDown(self):self.temporary.cleanup()
    def value(self,kind="hdbe.call",index=0):return package("find-me","harmonicdb",kind,{"index":index},ttl=3600)
    def deposit(self,porter,value,secret):return porter.deposit(value,admission=proof(secret,value))
    def rotate(self,porter=None,new_terms=None,reason="COMPROMISE_RESPONSE",fail_after=None):
        porter=porter or self.porter;return porter.admission.change("find-me",NEW,new_terms or terms(secret=NEW),reason,"technical-passport:offline-claim",fail_after)

    def test_stolen_capability_is_genuinely_authorised_before_threshold_then_refused(self):
        legitimate=self.value(index=1);stolen=self.value(index=2)
        self.deposit(self.porter,legitimate,OLD);self.deposit(self.porter,stolen,OLD)
        old_path=self.root/"introductions"/"facts"/f"{relationship_id('harmonicdb','find-me')}.json";old_bytes=old_path.read_bytes()
        change=self.rotate();after=self.value(index=3)
        with self.assertRaises(AdmissionRefused):self.deposit(self.porter,after,OLD)
        current=self.value(index=4);self.deposit(self.porter,current,NEW)
        self.assertEqual(old_path.read_bytes(),old_bytes);self.assertTrue((self.root/"introductions"/"changes"/f"{change['predecessor']}.json").exists())

    def test_historical_ac_replay_survives_compromise_and_termination(self):
        historical=self.value();receipt=self.deposit(self.porter,historical,OLD);self.rotate()
        self.assertEqual(self.porter.deposit(historical)["acceptance"],receipt["acceptance"])
        self.porter.admission.change("find-me",None,None,"EMERGENCY_TERMINATION")
        self.assertEqual(self.porter.deposit(historical)["acceptance"],receipt["acceptance"])
        with self.assertRaises(AdmissionRefused):self.deposit(self.porter,self.value(index=5),NEW)

    def test_candidate_is_not_current_until_atomic_change_fact(self):
        with self.assertRaises(StandingChangeInterrupted):self.rotate(fail_after="successor")
        self.deposit(self.porter,self.value(index=1),OLD)
        restarted=Porter("harmonicdb",self.root,{},relationships=self.config,require_introductions=True)
        self.deposit(restarted,self.value(index=2),OLD)
        with self.assertRaises(AdmissionRefused):self.deposit(restarted,self.value(index=3),NEW)

    def test_ordinary_renewal_prepares_without_an_authority_overlap(self):
        candidate=self.porter.admission.prepare("find-me",NEW,terms(secret=NEW),"technical-passport:offline-claim")
        self.deposit(self.porter,self.value(index=1),OLD)
        with self.assertRaises(AdmissionRefused):self.deposit(self.porter,self.value(index=2),NEW)
        self.porter.admission.change("find-me",NEW,terms(secret=NEW),"RENEWAL",successor_introduction=candidate["introduction"])
        with self.assertRaises(AdmissionRefused):self.deposit(self.porter,self.value(index=3),OLD)
        self.deposit(self.porter,self.value(index=4),NEW)

    def test_crash_after_change_recovers_only_successor(self):
        with self.assertRaises(StandingChangeInterrupted):self.rotate(fail_after="change")
        restarted=Porter("harmonicdb",self.root,{},relationships=self.config,require_introductions=True)
        with self.assertRaises(AdmissionRefused):self.deposit(restarted,self.value(index=1),OLD)
        self.deposit(restarted,self.value(index=2),NEW)

    def test_rotation_and_narrowing_do_not_reset_relationship_budget(self):
        constrained={"find-me":terms(max_outstanding_packages=2)};root=self.root/"budget";porter=Porter("harmonicdb",root,{},relationships=constrained,require_introductions=True)
        first=self.value(index=1);second=self.value(index=2);self.deposit(porter,first,OLD);self.deposit(porter,second,OLD)
        porter.admission.change("find-me",NEW,terms(secret=NEW,kinds=["hdbe.info"],max_outstanding_packages=2,max_outstanding_bytes=16384),"TERMS_REPLACED")
        with self.assertRaises(AdmissionRefused):self.deposit(porter,self.value("hdbe.info",3),NEW)
        collect_package(root,first["package"],"harmonicdb");self.deposit(porter,self.value("hdbe.info",4),NEW)
        with self.assertRaises(AdmissionRefused):self.deposit(porter,self.value("hdbe.call",5),NEW)

    def test_passport_absence_blocks_change_not_ordinary_local_admission(self):
        self.deposit(self.porter,self.value(index=1),OLD)
        unavailable=lambda _e:(_ for _ in ()).throw(OSError("offline"))
        with self.assertRaises(AdmissionRefused):self.porter.admission.change_from_claim("find-me",{"claim":"fresh"},unavailable,NEW,terms(secret=NEW),"RENEWAL")
        self.deposit(self.porter,self.value(index=2),OLD)

    def test_attacker_race_has_one_durable_threshold(self):
        for iteration in range(20):
            root=self.root/f"race-{iteration}";porter=Porter("harmonicdb",root,{},relationships=self.config,require_introductions=True);attack=self.value(index=iteration)
            def lodge_old():
                try:self.deposit(porter,attack,OLD);return "AC"
                except AdmissionRefused:return "REFUSE"
            with ThreadPoolExecutor(max_workers=2) as pool:
                attack_result,change_result=list(pool.map(lambda fn:fn(),[lodge_old,lambda:porter.admission.change("find-me",NEW,terms(secret=NEW),"COMPROMISE_RESPONSE")]))
            self.assertIn(attack_result,{"AC","REFUSE"});self.assertEqual(change_result["predecessor"],relationship_id("harmonicdb","find-me"))
            with self.assertRaises(AdmissionRefused):self.deposit(porter,self.value(index=100+iteration),OLD)
            self.deposit(porter,self.value(index=200+iteration),NEW)
            self.assertEqual((root/"acceptances"/f"{attack['package']}.json").exists(),attack_result=="AC")

    def test_ten_thousand_compromised_attempts_after_change_create_nothing(self):
        self.rotate();before={path.relative_to(self.root) for path in self.root.rglob("*") if path.is_file()}
        for index in range(10_000):
            value=self.value(index=index)
            with self.assertRaises(AdmissionRefused):self.deposit(self.porter,value,OLD)
        after={path.relative_to(self.root) for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after,before);self.assertEqual(list((self.root/"acceptances").glob("*.json")),[])


if __name__=="__main__":unittest.main()
