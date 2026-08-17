from __future__ import annotations

import base64,json,socket,struct,tempfile,threading,time,unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from porter.ceremony import ceremony_proof
from porter.daemon import Porter
from porter.introduction import relationship_id
from porter.native import NativeFrameRefused,open_frame,public_key,seal
from porter.protocol import atomic_write,package

OLD="native-operational";NEW="native-replacement";CEREMONY="native-ceremony";EXPIRY=int(time.time())+86400
def keypair():
    key=X25519PrivateKey.generate();private=base64.b64encode(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode();return private,public_key(private)
def terms(identity):return {"secret":OLD,"authority":"offline","kinds":["hdbe.call" if identity=="find-me" else "porter.return"],"max_package_bytes":8192,"max_outstanding_packages":50,"max_outstanding_bytes":65536,"expires_at":EXPIRY,"ceremony_secret":CEREMONY,"ceremony_expires_at":EXPIRY,"ceremony_max_changes":8,"ceremony_max_pending":4,"ceremony_terms":{"kinds":["hdbe.call" if identity=="find-me" else "porter.return"],"max_package_bytes":8192,"max_outstanding_packages":50,"max_outstanding_bytes":65536,"expires_at":EXPIRY}}
def port():
    sock=socket.socket();sock.bind(("127.0.0.1",0));value=sock.getsockname()[1];sock.close();return value


class NativeCarriageExperiment(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name);self.a_root=base/"a";self.b_root=base/"b";self.a_key,self.a_public=keypair();self.b_key,self.b_public=keypair();self.a_port,self.b_port=port(),port()
        self.a=Porter("find-me",self.a_root,{},relationships={"harmonicdb":terms("harmonicdb")},require_introductions=True,native_private_key=self.a_key,native_rendezvous={"harmonicdb":{"host":"127.0.0.1","port":self.b_port,"public_key":self.b_public}},native_listen=f"127.0.0.1:{self.a_port}")
        self.b=Porter("harmonicdb",self.b_root,{},relationships={"find-me":terms("find-me")},require_introductions=True,native_private_key=self.b_key,native_rendezvous={"find-me":{"host":"127.0.0.1","port":self.a_port,"public_key":self.a_public}},native_listen=f"127.0.0.1:{self.b_port}")
        for porter in (self.a,self.b):threading.Thread(target=porter.native.serve_forever,daemon=True).start()
        time.sleep(.03)
    def tearDown(self):
        for porter in (self.a,self.b):porter.native.stop()
        time.sleep(.02)
        self.tmp.cleanup()
    def pump(self,predicate,limit=200):
        for _ in range(limit):
            self.a.native.tick();self.b.native.tick()
            if predicate():return
            time.sleep(.01)
        self.fail("native carriage did not converge")

    def test_protected_frame_binds_recipient_class_and_ciphertext(self):
        secret={"replacement_secret":"this-must-not-be-visible"};frame=seal(secret,"find-me",self.a_key,"harmonicdb",self.b_public,"CEREMONY","CU-one");body=frame[9:]
        self.assertNotIn(b"this-must-not-be-visible",frame);envelope,value=open_frame(body,"harmonicdb",self.b_key,{"find-me":self.a_public});self.assertEqual(secret,value)
        with self.assertRaises(NativeFrameRefused):open_frame(body,"another-porter",self.b_key,{"find-me":self.a_public})
        altered=json.loads(body);raw=bytearray(base64.b64decode(altered["ciphertext"]));raw[-1]^=1;altered["ciphertext"]=base64.b64encode(raw).decode()
        with self.assertRaises(NativeFrameRefused):open_frame(json.dumps(altered).encode(),"harmonicdb",self.b_key,{"find-me":self.a_public})

    def test_package_and_acceptance_evidence_are_independent_native_units(self):
        value=package("find-me","harmonicdb","hdbe.call",{"native":True},ttl=3600);atomic_write(self.a_root/"outgoing",value)
        self.pump(lambda:(self.a_root/"receipts"/f"{value['package']}.json").exists())
        self.assertTrue((self.b_root/"acceptances"/f"{value['package']}.json").exists());self.assertTrue((self.b_root/"inbox"/f"{value['package']}.json").exists())
        self.assertTrue(any(path.name.startswith("CU-EV-") for path in (self.b_root/"native"/"outgoing").glob("*.json")) or (self.a_root/"receipts"/f"{value['package']}.json").exists())

    def test_remote_ac_can_outrun_origin_knowledge_and_retry_repairs_it(self):
        value=package("find-me","harmonicdb","hdbe.call",{"lost_evidence":True},ttl=3600);atomic_write(self.a_root/"outgoing",value);original=self.b.native.send;self.b.native.send=lambda *_:(_ for _ in ()).throw(OSError("return path lost"))
        self.pump(lambda:(self.b_root/"acceptances"/f"{value['package']}.json").exists());self.assertFalse((self.a_root/"receipts"/f"{value['package']}.json").exists())
        self.b.native.send=original;self.pump(lambda:(self.a_root/"receipts"/f"{value['package']}.json").exists())
        self.assertEqual(1,len(list((self.b_root/"acceptances").glob(f"{value['package']}.json"))))

    def test_recipient_absence_retains_unit_then_same_identity_moves_rendezvous(self):
        absent=port();self.a.native.rendezvous["harmonicdb"]["port"]=absent;first=package("find-me","harmonicdb","hdbe.call",{"absence":True},ttl=3600);atomic_write(self.a_root/"outgoing",first)
        for _ in range(5):self.a.native.tick();time.sleep(.01)
        self.assertTrue((self.a_root/"native"/"outgoing"/f"CU-PKG-{first['package']}.json").exists());self.assertFalse((self.b_root/"acceptances"/f"{first['package']}.json").exists())
        self.a.native.rendezvous["harmonicdb"]["port"]=self.b_port;self.pump(lambda:(self.a_root/"receipts"/f"{first['package']}.json").exists())
        old_intro=(self.b_root/"introductions"/"facts"/f"{relationship_id('harmonicdb','find-me')}.json").read_bytes();new_port=port();self.b.native.stop()
        moved=Porter("harmonicdb",self.b_root,{},relationships={"find-me":terms("find-me")},require_introductions=True,native_private_key=self.b_key,native_rendezvous={"find-me":{"host":"127.0.0.1","port":self.a_port,"public_key":self.a_public}},native_listen=f"127.0.0.1:{new_port}");threading.Thread(target=moved.native.serve_forever,daemon=True).start();time.sleep(.25);self.b=moved;self.a.native.rendezvous["harmonicdb"]["port"]=new_port
        second=package("find-me","harmonicdb","hdbe.call",{"moved":True},ttl=3600);atomic_write(self.a_root/"outgoing",second);self.pump(lambda:(self.a_root/"receipts"/f"{second['package']}.json").exists())
        self.assertEqual(old_intro,(self.b_root/"introductions"/"facts"/f"{relationship_id('harmonicdb','find-me')}.json").read_bytes())

    def test_standing_ceremony_and_result_travel_as_native_units(self):
        predecessor=relationship_id("harmonicdb","find-me");value=self.a.ceremonies.draft("harmonicdb",predecessor,NEW,{"kinds":["hdbe.call"],"max_package_bytes":8192,"max_outstanding_packages":50,"max_outstanding_bytes":65536,"expires_at":EXPIRY},"COMPROMISE_KNOWN");self.a.ceremonies.lodge(value)
        self.pump(lambda:(self.a_root/"ceremonies"/"receipts"/f"{value['ceremony']}.json").exists())
        self.assertEqual(value["successor"],self.b.admission.active["find-me"]["introduction"]);self.assertEqual(NEW,self.a.admission.outbound["harmonicdb"]["secret"])

    def test_hostile_framing_and_slow_connections_create_no_durable_state(self):
        before={p.relative_to(self.b_root) for p in self.b_root.rglob("*") if p.is_file()}
        cases=[b"P",struct.pack("!4sBI",b"NOPE",1,2)+b"{}",struct.pack("!4sBI",b"PRTR",9,2)+b"{}",struct.pack("!4sBI",b"PRTR",1,999999)]
        valid=seal({"x":1},"find-me",self.a_key,"harmonicdb",self.b_public,"PACKAGE","CU-hostile");cases.extend([valid[:-3],valid[:5]+struct.pack("!I",len(valid)-9-1)+valid[9:]])
        for raw in cases:
            try:
                with socket.create_connection(("127.0.0.1",self.b_port),timeout=1) as stream:stream.sendall(raw)
            except OSError:pass
        slow=[]
        for _ in range(80):
            try:slow.append(socket.create_connection(("127.0.0.1",self.b_port),timeout=.2))
            except OSError:pass
        time.sleep(.05)
        for stream in slow:stream.close()
        time.sleep(.1);after={p.relative_to(self.b_root) for p in self.b_root.rglob("*") if p.is_file()};self.assertEqual(before,after)
