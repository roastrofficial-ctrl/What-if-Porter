import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from porter.daemon import Porter
from porter.protocol import atomic_write,package
from porter.tickets import abandon,collect,inspect,lodge


class GenerationTwo(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.ipc=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def lodge_one(self,ttl=300):
        outbound=package("sender","recipient","demo.work",{"work":1},reply_to="sender",ttl=ttl)
        return outbound,lodge(self.ipc,outbound)

    def hold_return(self,outbound,value="done"):
        returned=package("recipient","sender","porter.return",{"value":value},in_reply_to=outbound["package"])
        Porter("sender",self.ipc,{}).deposit(returned);return returned

    def test_ticket_and_return_survive_host_and_porter_absence(self):
        outbound,ticket=self.lodge_one()
        # No Host object remains. A freshly-created Porter receives and holds reality.
        returned=self.hold_return(outbound)
        restarted_view=inspect(self.ipc,ticket["ticket"])
        self.assertEqual(restarted_view["state"],"RETURN_HELD")
        self.assertEqual(collect(self.ipc,ticket["ticket"])["package"]["package"],returned["package"])

    def test_collection_consumes_once_and_duplicate_reality_remains_visible(self):
        outbound,ticket=self.lodge_one();first=self.hold_return(outbound,"first");second=self.hold_return(outbound,"duplicate")
        view=inspect(self.ipc,ticket["ticket"]);self.assertEqual(view["duplicate_returns"],1)
        accepted=collect(self.ipc,ticket["ticket"]);self.assertEqual(accepted["state"],"COLLECTED");self.assertEqual(accepted["duplicates_retained"],1)
        repeated=collect(self.ipc,ticket["ticket"]);self.assertEqual(repeated["state"],"ALREADY_COLLECTED");self.assertEqual(repeated["return"],accepted["return"])
        self.assertTrue((self.ipc/"inbox"/((second if accepted["return"]==first["package"] else first)["package"]+".json")).exists())

    def test_expiry_is_observed_not_delivered(self):
        outbound,ticket=self.lodge_one(ttl=1);time.sleep(1.05)
        before=json.loads((self.ipc/"tickets"/(ticket["ticket"]+".json")).read_text())
        self.assertFalse(any(x["event"]=="EXPIRED_OBSERVED" for x in before["events"]))
        view=inspect(self.ipc,ticket["ticket"]);self.assertEqual(view["state"],"EXPIRED_OBSERVED")

    def test_abandonment_does_not_cancel_carriage_or_discard_late_return(self):
        outbound,ticket=self.lodge_one();self.assertEqual(abandon(self.ipc,ticket["ticket"])["state"],"ABANDONED")
        returned=self.hold_return(outbound,"late");view=inspect(self.ipc,ticket["ticket"]);self.assertEqual(view["state"],"ABANDONED_WITH_RETURN");self.assertIn(returned["package"],view["held_returns"])

    def test_two_collectors_do_not_both_consume(self):
        outbound,ticket=self.lodge_one();self.hold_return(outbound);results=[]
        threads=[threading.Thread(target=lambda:results.append(collect(self.ipc,ticket["ticket"]))) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(sum(x["state"]=="COLLECTED" for x in results),1)
        self.assertTrue(all(x["state"] in {"COLLECTED","ALREADY_COLLECTED","COLLECTION_CONTESTED"} for x in results))


if __name__=="__main__":unittest.main()
