# -*- coding: utf-8 -*-
"""组装并解析 Oopz 前端硬编码的 RSA 私钥

用法：
    python assemble_key.py [path/to/main.dart.js]

JS 来源：下载 https://web.oopz.cn 的 main.dart.js 保存到本地；
不传参数时默认读取本脚本同目录下的 web_main.js。
输出 oopz_priv.der / rsa_params.txt 到本脚本同目录。
"""
import base64
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JS_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'web_main.js')
JS = open(JS_PATH, encoding='utf-8', errors='replace').read()


def arr(name):
    m = re.search(r'\bB\.' + name + r'=A\.a\(s\(\[(.*?)\]\),t\.s\)', JS, re.S)
    body = m.group(1)
    out = []
    for lit, ident in re.findall(r'"([^"]*)"|u\.(\w+)', body):
        out.append(lit if lit else ident)
    return out


U_P = 'RDbdPGIvprQOPWj+2yWsVMWCVz/gxOnRiOPkYi6Q7NgjNGU3FACb+dgBd1f8oLS9'
U_AV = 'bIB9CveG9mSSVye3cQgjMVXJvxkwmLoc/mMapZJ7G1nxOvSnwr2ymV4+t+nXIt48'
U__ = 'x1/GymkrK0emVatysSuXrAvEvmlLufnxlWgp3wypAoGAGWO0G5EC/Ub7eMutFTuK'
U = {'P': U_P, 'av': U_AV, '_': U__}

bnw, bxY, bm6, biZ = arr('bnw'), arr('bxY'), arr('bm6'), arr('biZ')

def resolve(items):
    return ''.join(U[i] if i in U else i for i in items)

key_b64 = resolve(bnw) + resolve(bxY) + resolve(bm6) + resolve(biZ)
print("assembled base64 length:", len(key_b64))
der = base64.b64decode(key_b64)
print("DER length:", len(der))
print("DER head:", der[:32].hex())
print("DER tail:", der[-16:].hex())
open(os.path.join(HERE, 'oopz_priv.der'), 'wb').write(der)


# ---------- minimal DER parser ----------
def parse_tlv(buf, off):
    tag = buf[off]
    off += 1
    ln = buf[off]
    off += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[off:off + n], 'big')
        off += n
    return tag, buf[off:off + ln], off + ln


tag, body, _ = parse_tlv(der, 0)
print("\nouter tag: 0x%02x  len: %d" % (tag, len(body)))
off = 0
children = []
while off < len(body):
    t, v, off = parse_tlv(body, off)
    children.append((t, v))
print("children tags:", [hex(t) for t, _ in children])

# PKCS#8: [0]=version, [1]=algid, [2]=privateKey(OCTET STRING containing RSAPrivateKey)
if len(children) >= 3 and children[2][0] == 0x04:
    inner = children[2][1]
    print("inner RSAPrivateKey len:", len(inner))
    t, rb, _ = parse_tlv(inner, 0)
    o = 0
    ints = []
    while o < len(rb):
        t2, v2, o = parse_tlv(rb, o)
        ints.append((t2, v2))
    names = ['version', 'n(modulus)', 'e(publicExp)', 'd(privateExp)',
             'p(prime1)', 'q(prime2)', 'dp', 'dq', 'qinv']
    print("\n=== RSAPrivateKey fields ===")
    for i, (t2, v2) in enumerate(ints):
        nm = names[i] if i < len(names) else f'field{i}'
        if t2 == 0x02:
            val = int.from_bytes(v2, 'big')
            print(f"  {nm:14s} tag=INT  len={len(v2):4d}  intbits={val.bit_length()}  head={v2[:8].hex()}")
        else:
            print(f"  {nm:14s} tag={hex(t2)}  len={len(v2):4d}")
    if len(ints) >= 4:
        n = int.from_bytes(ints[1][1], 'big')
        e = int.from_bytes(ints[2][1], 'big')
        d = int.from_bytes(ints[3][1], 'big')
        print(f"\n  modulus bits: {n.bit_length()}")
        print(f"  public exponent: {e}")
        print(f"  private exponent bits: {d.bit_length()}")
        with open(os.path.join(HERE, 'rsa_params.txt'), 'w') as f:
            f.write(f"{n}\n{e}\n{d}\n")
        print("\n[+] saved n,e,d -> tools/rsa_params.txt")
