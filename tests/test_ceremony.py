from __future__ import annotations

import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from porter.ceremony import CeremonyInterrupted,CeremonyRefused,ceremony_proof
from porter.daemon import Porter
from porter.introduction import AdmissionRefused,proof,relationship_id
from porter.protocol import package

OLD="operational-stolen";NEW="operational-replacement";THIRD="operational-third";CEREMONY="separate-ceremonial-root";EXPIRY=int(time.time())+3600


def terms(secret=OLD,**changes):
    value={"secret":secret,"authority":"passport:offline","kinds":["hdbe.call"],"max_package_bytes":4096,"max_outstanding_packages":20,"max_outstanding_bytes":65536,"expires_at":EXPIRY}
    value.update(changes);return value


def config(secret=OLD,max_changes=8):
    value=terms(secret);value.update({"ceremony_secret":CEREMONY,"ceremony_expires_at":EXPIRY,"ceremony_max_changes":max_changes,"ceremony_max_pending":4,"ceremony_terms":{key:value[key] for key in ("kinds","max_package_bytes","max_outstanding_packages","max_outstanding_bytes","expires_at")}});return value


class StandingCeremonyCorrespondence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name);self.a_root=base/"a";self.b_root=base/"b"
        self.a=Porter("find-me",self.a_root,{"harmonicdb":"memory://b"},relationships={"harmonicdb":config() },require_introductions=True)
        self.b=Porter("harmonicdb",self.b_root,{"find-me":"memory://a"},relationships={"find-me":config()},require_introductions=True)
        self.predecessor=relationship_id("harmonicdb","find-me")
    def tearDown(self):self.tmp.cleanup()
    def pkg(self,index):return package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=3600)
    def deposit(self,index,secret=OLD):
        value=self.pkg(index);return value,self.b.deposit(value,admission=proof(secret,value))
    def draft(self,predecessor=None,secret=NEW,term=None,**kw):return self.a.ceremonies.draft("harmonicdb",predecessor or self.predecessor,secret,term or terms(secret),kw.pop("reason","COMPROMISE_KNOWN"),**kw)
    def present(self,value,evidence_secret=CEREMONY,**kw):return self.b.ceremonies.receive(value,ceremony_proof(evidence_secret,value),**kw)

    def test_knowledge_gap_acceptances_remain_historical_after_remote_ceremony(self):
        before,_=self.deposit(1);fact=self.a.ceremonies.lodge(self.draft())
        during,during_receipt=self.deposit(2)
        result=self.present(fact["ceremony_value"]);self.assertEqual("APPLIED",result["state"])
        with self.assertRaises(AdmissionRefused):self.deposit(3)
        self.deposit(4,NEW)
        self.assertEqual(during_receipt["acceptance"],self.b.deposit(during)["acceptance"])
        self.assertTrue((self.b_root/"acceptances"/f"{before['package']}.json").exists())

    def test_stolen_operational_authority_cannot_forge_or_widen_ceremony(self):
        value=self.draft()
        with self.assertRaises(CeremonyRefused):self.present(value,OLD)
        widened=self.draft(term=terms(NEW,kinds=["hdbe.call","porter.return"]))
        with self.assertRaises(CeremonyRefused):self.present(widened)
        self.deposit(1,OLD)

    def test_duplicate_collision_and_historical_replay_do_not_move_standing(self):
        value=self.draft(ceremony_id="CM-stable");first=self.present(value);again=self.present(value)
        self.assertEqual(first,again)
        mutated={**value,"reason":"ATTACKER_MUTATION"}
        with self.assertRaises(CeremonyRefused):self.present(mutated)
        second=self.a.ceremonies.draft("harmonicdb",value["successor"],THIRD,terms(THIRD),"RENEWAL")
        self.present(second);self.assertEqual(second["successor"],self.b.admission.active["find-me"]["introduction"])
        self.assertEqual(first,self.present(value));self.assertEqual(second["successor"],self.b.admission.active["find-me"]["introduction"])

    def test_out_of_order_valid_ceremony_waits_for_predecessor_then_drains(self):
        first=self.draft();second=self.a.ceremonies.draft("harmonicdb",first["successor"],THIRD,terms(THIRD),"RENEWAL")
        self.assertEqual("PENDING_PREDECESSOR",self.present(second)["state"])
        self.present(first)
        self.assertEqual(second["successor"],self.b.admission.active["find-me"]["introduction"])
        self.assertEqual("APPLIED",self.present(second)["state"])

    def test_crash_matrix_reconstructs_from_canonical_threshold(self):
        for point in ("received","verified","candidate"):
            with self.subTest(point=point):
                root=self.b_root/point;porter=Porter("harmonicdb",root,{},relationships={"find-me":config()},require_introductions=True);value=self.draft(ceremony_id=f"CM-{point}")
                with self.assertRaises(CeremonyInterrupted):porter.ceremonies.receive(value,ceremony_proof(CEREMONY,value),fail_after=point)
                restarted=Porter("harmonicdb",root,{},relationships={"find-me":config()},require_introductions=True)
                old=self.pkg(100);restarted.deposit(old,admission=proof(OLD,old))
                restarted.ceremonies.receive(value,ceremony_proof(CEREMONY,value));new=self.pkg(101);restarted.deposit(new,admission=proof(NEW,new))
        for point in ("change","result"):
            with self.subTest(point=point):
                root=self.b_root/point;porter=Porter("harmonicdb",root,{},relationships={"find-me":config()},require_introductions=True);value=self.draft(ceremony_id=f"CM-{point}")
                with self.assertRaises(CeremonyInterrupted):porter.ceremonies.receive(value,ceremony_proof(CEREMONY,value),fail_after=point)
                restarted=Porter("harmonicdb",root,{},relationships={"find-me":config()},require_introductions=True)
                old=self.pkg(200)
                with self.assertRaises(AdmissionRefused):restarted.deposit(old,admission=proof(OLD,old))
                self.assertEqual("APPLIED",restarted.ceremonies.receive(value,ceremony_proof(CEREMONY,value))["state"])

    def test_origin_lodgement_and_lost_result_are_repairable(self):
        value=self.draft()
        with self.assertRaises(CeremonyInterrupted):self.a.ceremonies.lodge(value,fail_after="lodged")
        restarted=Porter("find-me",self.a_root,{"harmonicdb":"memory://b"},relationships={"harmonicdb":config()},require_introductions=True)
        outgoing=json.loads(next((self.a_root/"ceremonies"/"outgoing").glob("CM-*.json")).read_text())
        result=self.b.ceremonies.receive(outgoing["ceremony"],outgoing["evidence"])
        self.assertFalse((self.a_root/"ceremonies"/"receipts"/f"{value['ceremony']}.json").exists())
        repeated=self.b.ceremonies.receive(outgoing["ceremony"],outgoing["evidence"]);self.assertEqual(result,repeated)
        restarted.ceremonies.retain_result(repeated);self.assertTrue((self.a_root/"ceremonies"/"receipts"/f"{value['ceremony']}.json").exists())
        fresh=self.pkg(777);self.assertEqual(proof(NEW,fresh),restarted.admission.outbound_proof(fresh))

    def test_recipient_absence_preserves_origin_lodgement_until_later_carriage(self):
        value=self.draft();self.a.ceremonies.lodge(value);path=self.a_root/"ceremonies"/"outgoing"/f"{value['ceremony']}.json"
        self.a._network_ceremony=lambda *_:(_ for _ in ()).throw(OSError("recipient absent"))
        with self.assertRaises(OSError):self.a.carry_ceremony_one(path)
        self.assertTrue(path.exists());self.assertFalse((self.a_root/"ceremonies"/"receipts"/f"{value['ceremony']}.json").exists())
        self.deposit(50,OLD)
        self.a._network_ceremony=lambda ceremony,evidence,_route:self.b.ceremonies.receive(ceremony,evidence)
        result=self.a.carry_ceremony_one(path);self.assertEqual("APPLIED",result["state"])
        with self.assertRaises(AdmissionRefused):self.deposit(51,OLD)

    def test_stolen_ceremonial_authority_has_finite_local_grant(self):
        root=self.b_root/"bounded";porter=Porter("harmonicdb",root,{},relationships={"find-me":config(max_changes=2)},require_introductions=True)
        one=self.draft(ceremony_id="CM-theft-1");porter.ceremonies.receive(one,ceremony_proof(CEREMONY,one))
        two=self.a.ceremonies.draft("harmonicdb",one["successor"],THIRD,terms(THIRD),"ATTACKER_REPLACEMENT",ceremony_id="CM-theft-2");porter.ceremonies.receive(two,ceremony_proof(CEREMONY,two))
        three=self.a.ceremonies.draft("harmonicdb",two["successor"],"fourth",terms("fourth"),"ATTACKER_REPLACEMENT",ceremony_id="CM-theft-3")
        with self.assertRaises(CeremonyRefused):porter.ceremonies.receive(three,ceremony_proof(CEREMONY,three))
        self.assertEqual(two["successor"],porter.admission.active["find-me"]["introduction"])

    def test_attacker_and_ceremony_race_linearise_at_recipient_sc(self):
        for index in range(20):
            root=self.b_root/f"race-{index}";porter=Porter("harmonicdb",root,{},relationships={"find-me":config()},require_introductions=True);value=self.draft(ceremony_id=f"CM-race-{index}");attack=self.pkg(index)
            def attack_once():
                try:porter.deposit(attack,admission=proof(OLD,attack));return "AC"
                except AdmissionRefused:return "REFUSE"
            with ThreadPoolExecutor(max_workers=2) as pool:
                attacked=pool.submit(attack_once);changed=pool.submit(porter.ceremonies.receive,value,ceremony_proof(CEREMONY,value));result=attacked.result();changed.result()
            self.assertEqual(result=="AC",(root/"acceptances"/f"{attack['package']}.json").exists())
            after=self.pkg(1000+index)
            with self.assertRaises(AdmissionRefused):porter.deposit(after,admission=proof(OLD,after))

    def test_wrong_relationship_recipient_predecessor_and_oversize_are_refused_without_facts(self):
        cases=[]
        ordinary=self.draft()
        cases.append(({**ordinary,"to":"another-porter"},CEREMONY))
        cases.append(({**ordinary,"sender":"another-host"},CEREMONY))
        cases.append(({**ordinary,"replacement_secret":"x"*40000},CEREMONY))
        before={p.relative_to(self.b_root) for p in self.b_root.rglob("*") if p.is_file()}
        for value,secret in cases:
            with self.assertRaises(CeremonyRefused):self.present(value,secret)
        after={p.relative_to(self.b_root) for p in self.b_root.rglob("*") if p.is_file()}
        self.assertEqual(before,after)

    def test_ten_thousand_invalid_ceremonies_create_no_recipient_state(self):
        before={p.relative_to(self.b_root) for p in self.b_root.rglob("*") if p.is_file()}
        for index in range(10000):
            value=self.draft(ceremony_id=f"CM-hostile-{index}")
            with self.assertRaises(CeremonyRefused):self.present(value,"not-the-ceremony-key")
        after={p.relative_to(self.b_root) for p in self.b_root.rglob("*") if p.is_file()}
        self.assertEqual(before,after)
