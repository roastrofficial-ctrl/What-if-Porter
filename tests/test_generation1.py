import json
import tempfile
import time
import unittest
from pathlib import Path

from porter.daemon import Porter
from porter.protocol import atomic_write, package, validate


class GenerationOne(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);self.a=root/"a";self.b=root/"b"
        self.recipient=Porter("recipient",self.b,{"sender":"unused"})
        self.sender=Porter("sender",self.a,{"recipient":"opaque-route"},transport=lambda value,_:self.recipient.deposit(value))
        import threading;threading.Thread(target=self.sender.carry,daemon=True).start()

    def tearDown(self):self.sender.running=False;self.temp.cleanup()

    def wait(self,path):
        deadline=time.time()+3
        while time.time()<deadline:
            if path.exists():return
            time.sleep(.02)
        self.fail(f"timed out waiting for {path}")

    def test_arrival_is_held_until_explicit_collection(self):
        marker=self.b/"host-executed";value=package("sender","recipient","demo.note",{"opaque":"hello"},reply_to="sender")
        atomic_write(self.a/"outgoing",value);held=self.b/"inbox"/(value["package"]+".json");self.wait(held)
        self.assertFalse(marker.exists(),"Package arrival must not invoke the Host")
        collected=self.b/"collected"/held.name;held.rename(collected);marker.write_text(json.loads(collected.read_text())["payload"]["opaque"])
        self.assertEqual(marker.read_text(),"hello")

    def test_carriage_is_payload_opaque_and_records_receipt(self):
        value=package("sender","recipient","unknown.application.kind",{"secret_shape":{"x":[1,2,3]}})
        atomic_write(self.a/"outgoing",value);held=self.b/"inbox"/(value["package"]+".json");self.wait(held)
        self.assertEqual(json.loads(held.read_text())["payload"],value["payload"])
        receipt=self.a/"receipts"/(value["package"]+".json");self.wait(receipt);self.assertEqual(json.loads(receipt.read_text())["state"],"HELD_FOR_COLLECTION")

    def test_invalid_or_expired_packages_are_refused(self):
        value=package("sender","recipient","demo.note",{});value["expires"]=value["created"]-1
        with self.assertRaises(ValueError):self.recipient.deposit(value)
        with self.assertRaises(ValueError):validate({"protocol":"PORTER/1"})


if __name__=="__main__":unittest.main()
