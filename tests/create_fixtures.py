import struct
import os

def create_rdt_packet():
    # RDT Response: >IIIiiiiii
    # rdt_seq=1, ft_seq=100, status=0, counts=(1000, 2000, 3000, 400, 500, 600)
    fmt = ">IIIiiiiii"
    data = struct.pack(fmt, 1, 100, 0, 1000, 2000, 3000, 400, 500, 600)
    with open("tests/fixtures/rdt_packet.bin", "wb") as f:
        f.write(data)

def create_tcp_calinfo():
    # TCP CalInfo: >HBBII6H
    # Header=0x1234, fu=2(N), tu=3(Nm), cpf=1000000, cpt=1000000, scale=(1,1,1,1,1,1)
    # Note: scaling factors are often mostly 1 or specific values, but for parsing test we just need valid structure.
    fmt = ">HBBII6H"
    data = struct.pack(fmt, 0x1234, 2, 3, 1000000, 1000000, 1, 1, 1, 1, 1, 1)
    with open("tests/fixtures/tcp_calinfo.bin", "wb") as f:
        f.write(data)

def create_xml_calinfo():
    xml = """<?xml version="1.0"?>
<netft>
    <cfgcpf>1000000</cfgcpf>
    <cfgcpt>1000000</cfgcpt>
    <cfgfu>2</cfgfu>
    <cfgtu>3</cfgtu>
    <setserial>FT12345</setserial>
    <setfwver>1.0.0</setfwver>
</netft>
"""
    with open("tests/fixtures/netftapi2.xml", "w") as f:
        f.write(xml)

if __name__ == "__main__":
    os.makedirs("tests/fixtures", exist_ok=True)
    create_rdt_packet()
    create_tcp_calinfo()
    create_xml_calinfo()
