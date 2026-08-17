#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,resource,socket,tempfile,threading,time,sys
from pathlib import Path
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from porter.daemon import Porter,handler
from porter.introduction import canonical,proof
from porter.native import NativeFrameRefused,open_frame,public_key,seal
from porter.protocol import atomic_write,package
from http.server import ThreadingHTTPServer
from reality_check import count_filesystem_operations,filesystem,measured,percentiles

SECRET="native-benchmark-operational";EXPIRY=int(time.time())+86400
def terms(sender):return {"secret":SECRET,"authority":"offline","kinds":["hdbe.call" if sender=="find-me" else "porter.return"],"max_package_bytes":8192,"max_outstanding_packages":10000,"max_outstanding_bytes":100000000,"expires_at":EXPIRY}
def keypair():
    key=X25519PrivateKey.generate();private=base64.b64encode(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode();return private,public_key(private)
def free_port():
    stream=socket.socket();stream.bind(("127.0.0.1",0));value=stream.getsockname()[1];stream.close();return value
def pct(values):return percentiles(values)

def native_valid(samples):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);a_key,a_pub=keypair();b_key,b_pub=keypair();ap,bp=free_port(),free_port();a=Porter("find-me",root/"a",{},relationships={"harmonicdb":terms("harmonicdb")},require_introductions=True,native_private_key=a_key,native_rendezvous={"harmonicdb":{"host":"127.0.0.1","port":bp,"public_key":b_pub}},native_listen=f"127.0.0.1:{ap}");b=Porter("harmonicdb",root/"b",{},relationships={"find-me":terms("find-me")},require_introductions=True,native_private_key=b_key,native_rendezvous={"find-me":{"host":"127.0.0.1","port":ap,"public_key":a_pub}},native_listen=f"127.0.0.1:{bp}")
        for porter in (a,b):threading.Thread(target=porter.native.serve_forever,daemon=True).start()
        time.sleep(.03);timings=[];before=filesystem(root)
        with count_filesystem_operations() as operations:
            for index in range(samples):
                value=package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=3600);started=time.perf_counter_ns();atomic_write(a.ipc/"outgoing",value)
                for _ in range(1000):
                    a.native.tick();b.native.tick()
                    if (a.ipc/"receipts"/f"{value['package']}.json").exists():break
                    time.sleep(.0005)
                else:raise RuntimeError("native benchmark did not converge")
                timings.append(time.perf_counter_ns()-started)
        for porter in (a,b):porter.native.stop()
        time.sleep(.1);after=filesystem(root);sample=package("find-me","harmonicdb","hdbe.call",{"index":0},ttl=3600);frame=seal({"package":sample,"admission":proof(SECRET,sample)},"find-me",a_key,"harmonicdb",b_pub,"PACKAGE",f"CU-PKG-{sample['package']}")
        return {"latency":pct(timings),"representative_wire_bytes":len(frame),"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}

def http_valid(samples):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);recipient=Porter("harmonicdb",root,{},relationships={"find-me":terms("find-me")},require_introductions=True);server=ThreadingHTTPServer(("127.0.0.1",0),handler(recipient));threading.Thread(target=server.serve_forever,daemon=True).start();port=server.server_address[1];timings=[];wire=[];before=filesystem(root)
        with count_filesystem_operations() as operations:
            for index in range(samples):
                value=package("find-me","harmonicdb","hdbe.call",{"index":index},ttl=3600);body=json.dumps({"package":value,"admission":proof(SECRET,value)},separators=(",",":")).encode();wire.append(len(body));request=Request(f"http://127.0.0.1:{port}/deposit",body,{"Content-Type":"application/json"});started=time.perf_counter_ns();json.load(urlopen(request));timings.append(time.perf_counter_ns()-started)
        after=filesystem(root);server.shutdown();return {"latency":pct(timings),"representative_body_bytes":wire[0],"growth":{"files":after["files"]-before["files"],"bytes":after["bytes"]-before["bytes"]},"operations":operations}

def crypto_cost(samples):
    a_key,_=keypair();b_key,b_pub=keypair();frames=[];sealing=[];opening=[]
    for index in range(samples):
        value={"replacement_secret":"protected-"+str(index),"padding":"x"*512};started=time.perf_counter_ns();frame=seal(value,"find-me",a_key,"harmonicdb",b_pub,"CEREMONY",f"CU-{index}");sealing.append(time.perf_counter_ns()-started);started=time.perf_counter_ns();open_frame(frame[9:],"harmonicdb",b_key,{"find-me":public_key(a_key)});opening.append(time.perf_counter_ns()-started);frames.append(frame)
    return {"seal":pct(sealing),"open":pct(opening),"wire_bytes":len(frames[0]),"plaintext_bytes":len(canonical({"replacement_secret":"protected-0","padding":"x"*512}))}

def invalid(count):
    a_key,_=keypair();b_key,b_pub=keypair();value={"noise":"x"*128};frame=seal(value,"find-me",a_key,"harmonicdb",b_pub,"PACKAGE","CU-invalid");envelope=json.loads(frame[9:]);raw=bytearray(base64.b64decode(envelope["ciphertext"]));raw[-1]^=1;envelope["ciphertext"]=base64.b64encode(raw).decode();body=canonical(envelope)
    def attack():
        for _ in range(count):
            try:open_frame(body,"harmonicdb",b_key,{"find-me":public_key(a_key)})
            except NativeFrameRefused:pass
    _,timing=measured(attack);return timing

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--attempts",type=int,default=10000);parser.add_argument("--samples",type=int,default=100);parser.add_argument("--output");parser.add_argument("--quiet",action="store_true");args=parser.parse_args();started=time.time();report={"benchmark":"PORTER 1.4 Native Carriage","samples":args.samples,"attempts":args.attempts,"native":native_valid(args.samples),"http":http_valid(args.samples),"cryptographic_protection":crypto_cost(args.samples),"invalid_protected_frames":invalid(args.attempts),"elapsed_seconds":time.time()-started};raw=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;report["process_max_rss_bytes"]=raw if sys.platform=="darwin" else raw*1024;rendered=json.dumps(report,indent=2,sort_keys=True)
    if args.output:Path(args.output).write_text(rendered+"\n")
    if not args.quiet:print(rendered)
if __name__=="__main__":main()
