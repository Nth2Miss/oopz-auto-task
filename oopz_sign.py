#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Oopz 自动签到 / 每日任务

════════════════════════════════════════════════════════════════════════
签名算法（从 web.oopz.cn 的 Flutter Web 产物 main.dart.js 逆向，已用 3 个真实
签名样本 100% 验证通过）：

    sign = Base64( RSA_PKCS1v15_SHA256( hex(MD5(路径含query + JSON请求体)) + 毫秒时间戳 ) )

    · 路径含 query string，如 /general/v3/settings?oopzChannel=Web&versionNo=88053
    · 无请求体时用空字符串
    · RSA-2048 私钥硬编码在客户端里（本脚本已内置），填充方式 PKCS#1 v1.5

必需请求头（Web 端取值）：
    oopz-sign                 上面算出的签名
    oopz-time                 毫秒时间戳（与签名里用的必须一致）
    oopz-request-id           UUID
    oopz-device-id            UUID
    oopz-platform             windows
    oopz-channel              Web
    oopz-app-version-number   88053
    oopz-web                  true
    oopz-signature            登录后的 token（此头放 token，不是签名）
    oopz-person               用户 uid

返回码：
    401 签名不正确     403 缺少请求头     405 方法不对
    428 需要登录 / 登录态失效（token 缺失或无效）
════════════════════════════════════════════════════════════════════════

用法：
    python oopz_sign.py login        # 拉起浏览器，你登录，凭证自动保存
    python oopz_sign.py whoami       # 校验凭证
    python oopz_sign.py check        # 查询签到/任务状态
    python oopz_sign.py sign         # 执行签到
    python oopz_sign.py tasks        # 执行每日任务（笔记相关）
    python oopz_sign.py probe        # 探测各接口真实响应（排障）
    python oopz_sign.py loop --at 08:30
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
import re
import uuid

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

GATEWAY = "https://gateway.oopz.cn"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "oopz_config.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "oopz_sign.log")
LOGIN_HELPER = os.path.join(SCRIPT_DIR, "tools", "oopz_login.js")

PLATFORM = "windows"
CHANNEL = "Web"
APP_VER = "88053"

# ══════════════════════════════════════════════════════════════════════
# 账号配置（可选）：直接填写后，无需 oopz_config.json 即可全自动登录
#   · 填了 ACCOUNT_PHONE + ACCOUNT_PASSWORD：token 失效/缺失时自动密码重登，彻底无人值守
#   · 两者留空：沿用 oopz_config.json / 环境变量 / 交互式登录
# ══════════════════════════════════════════════════════════════════════
ACCOUNT_PHONE = ""      # 例如 "13812345678"
ACCOUNT_PASSWORD = ""   # 例如 "your_password_here"

ERROR_HINTS = {
    401: "签名不正确 (cSignNotCorrect)",
    403: "缺少请求头 (headerIsMissing)",
    405: "请求方法不正确",
    428: "需要登录 / 登录态失效 —— token 缺失或无效",
    502: "服务端错误",
}

# ── 客户端硬编码的 RSA-2048 私钥（PKCS#8 DER 的 base64）──────────────────
PRIV_B64 = (
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC/dbSx0kagPRmhBdaExF7PPTr4CEc0wNE/pZQXjZwIIiaGruKg"
    "w4fPS/steNZLmLo/223cUcW17Vza/hhvhY9byP4spq9aEGdUjDYHHyBynlUYTdkbcYm2IeCQnQ99uZOPvL/Z6bJIVUXfCp2I+8hz"
    "slK7aIjNgf15YfHXdi6MPic+6lFCYk38RK+OKXlq4jZxHvM4igVxJcCwU+dP1D0Y9D/ne4WIijSIz9HTx9ANc3YeR4cxN98loo9z"
    "c11cR677midk3Z6Qn0BsHeQ48wtz8l1LgYUFiaQKUS7LbtbkfYOHBDDRMi4HQxTZmxh357jaeBNRep4Fij2dUqtkc1lRAgMBAAEC"
    "ggEAUQEsAlBFMWaogUhHCsVKl8QAPxDBj8BEx/j2P0Da01YflrxHhl00CLDNBOArSrDDnGDqilzOmbpjnwQCsqx/iwXvBFVBu4lV"
    "LqBj+39f6x6yQiYtxT60VSrgKE9LTpZFqHrjcP8/PvtVJJkJLfvZQ5ofBsujlc95vvGBsPd/mjW2LPc0+qYGMvSuySQuCmsy5jHA"
    "9zLn6TNgAuC6dDhjfD8ovNkPUt7BQn6LyvBj+Zu3mYzVSDO6aZcyzPe4hakwnFHQ/BDpgLuv+JKKHhdKbJcsgX+00oVGDThqivKq"
    "Y7MiyQIOEvO/AZIVTVIyXwYfsYZUg4noghpOoq2AEJi/QQKBgQDpQu59XGfN3cbW6n/lOTtkXLL8JSUapjY+5esir150JMxEDEnM"
    "uAwpdIxVT0OJdtjHCgMO//3vR57Af3PBCqjO9QDXhrXvwh4yDmaI8RYRZQibc1HbVsFFE5xP2c2bZcVjU9QIowt03gYSUakmxNtC"
    "M0vutKymejDvgp57PQGAJwKBgQDSH5vKkydAhCuyjCW+5e7u31jX0vPFdI/+jpNWFgUAv9aw/6omUCQLEU+dhP6/CT0Ej5LFsv1Y"
    "6+LAlfNyY+wTO+dVWl7hBDn+9rtR9+7ri7js5htd4aczzmSWO/WIGnCRr2BlcCpl8fsQIHirE+AC6sXdUey6uGCvL0XQvntNxwKB"
    "gD63nVIdh1eF2tGsSWkDg2GPvxwmjJxmtk0hGqC/0ECgKD/fofQmRDbdPGIvprQOPWj+2yWsVMWCVz/gxOnRiOPkYi6Q7NgjNGU3"
    "FACb+dgBd1f8oLS91cdR54RcxniS24jCYE9WL11j2PQR+s4OvflFu5PaBlXYotGzKBNwqrefAoGBAICKzaeTdgPF12WWztCFoTGI"
    "eLUvW+mDcUNsvT2AovbeZNxKyzA8/o+2u1nFroH3iNhtbIB9CveG9mSSVye3cQgjMVXJvxkwmLoc/mMapZJ7G1nxOvSnwr2ymV4+"
    "t+nXIt48x1/GymkrK0emVatysSuXrAvEvmlLufnxlWgp3wypAoGAGWO0G5EC/Ub7eMutFTuKM3OqZe1QfsA0czqSmRm6BxJScsZ1"
    "FUxaTfhgt/gukhcI8VSOLB9V45zOz9ZDurh5OCDhNYaGJWgvkSUQyywAM0S/ZM6xQ4RdUa3ul7iIFitxwZHBPJvIF1zlc5pD+rje"
    "+rlKfKY1WLUGaXs5QRXfEr4="
)


# ══════════════════════════════════════════════════════════════════════
# 从内嵌 PKCS#8 私钥中解析出 n / d
# ══════════════════════════════════════════════════════════════════════
def _der_walk(buf, off, out):
    """极简 DER 遍历，收集所有 INTEGER 的字节串"""
    while off < len(buf):
        tag = buf[off]
        ln = buf[off + 1]
        off += 2
        if ln & 0x80:
            nbytes = ln & 0x7F
            ln = int.from_bytes(buf[off:off + nbytes], 'big')
            off += nbytes
        val = buf[off:off + ln]
        if tag == 0x30:
            _der_walk(val, 0, out)
        elif tag == 0x04:
            _der_walk(val, 0, out)
        elif tag == 0x02:
            out.append(val)
        off += ln
    return out


def _load_key():
    der = base64.b64decode(PRIV_B64)
    ints = _der_walk(der, 0, [])
    # 收集到的 INTEGER 顺序：
    #   [0] PKCS#8 version
    #   [1] RSAPrivateKey.version  [2] n  [3] e  [4] d  [5] p  [6] q  ...
    if len(ints) < 5:
        raise RuntimeError(f"私钥解析失败（只找到 {len(ints)} 个 INTEGER）")
    n = int.from_bytes(ints[2], 'big')
    d = int.from_bytes(ints[4], 'big')
    return n, d


N, D = _load_key()
K = (N.bit_length() + 7) // 8
SHA256_DIGESTINFO_PREFIX = bytes.fromhex('3031300d060960864801650304020105000420')


def make_sign(path_with_query: str, body_str: str, ts_ms: str) -> str:
    """官方签名算法（已用真实样本验证）"""
    md5_hex = hashlib.md5((path_with_query + body_str).encode('utf-8')).hexdigest()
    payload = (md5_hex + ts_ms).encode('utf-8')
    t = SHA256_DIGESTINFO_PREFIX + hashlib.sha256(payload).digest()
    em = b'\x00\x01' + b'\xff' * (K - len(t) - 3) + b'\x00' + t
    sig = pow(int.from_bytes(em, 'big'), D, N).to_bytes(K, 'big')
    return base64.b64encode(sig).decode('ascii')


# ══════════════════════════════════════════════════════════════════════
def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception:
        pass


class OopzClient:
    def __init__(self, token=None, uid=None, verbose=True):
        self.token = str(token) if token else None
        self.uid = str(uid) if uid else ""
        self.verbose = verbose

    def request(self, path, method="POST", body=None, with_auth=True):
        ts = str(int(time.time() * 1000))
        body_str = "" if body is None else json.dumps(body, separators=(',', ':'), ensure_ascii=False)
        headers = {
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json;charset=utf-8",
            "oopz-app-version-number": APP_VER,
            "oopz-channel": CHANNEL,
            "oopz-device-id": str(uuid.uuid4()),
            "oopz-platform": PLATFORM,
            "oopz-request-id": str(uuid.uuid4()),
            "oopz-time": ts,
            "oopz-web": "true",
            "oopz-sign": make_sign(path, body_str, ts),
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "origin": "https://web.oopz.cn",
            "referer": "https://web.oopz.cn/",
        }
        if with_auth and self.token:
            headers["oopz-signature"] = self.token
            headers["oopz-person"] = self.uid
        req = urllib.request.Request(GATEWAY + path, method=method,
                                     data=body_str.encode('utf-8') if body_str else None,
                                     headers=headers)
        if self.verbose:
            print(f"  -> {method} {path}" + (f"  {body_str}" if body_str else ""))
        try:
            r = urllib.request.urlopen(req, timeout=25)
            return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as ex:
            return ex.code, ex.read().decode('utf-8', 'replace')
        except Exception as ex:
            return None, f"{type(ex).__name__}: {ex}"

    @staticmethod
    def describe(status, raw):
        if status is None:
            return f"网络错误: {raw}"
        hint = ERROR_HINTS.get(status, "")
        msg = (raw or "").strip() or "(空响应)"
        if len(msg) > 400:
            msg = msg[:400] + "..."
        return f"HTTP {status}" + (f"  [{hint}]" if hint else "") + f"\n       {msg}"

    @staticmethod
    def ok(status, raw):
        return status == 200 and '"status":true' in (raw or "").replace(" ", "")


# ── 候选接口 ────────────────────────────────────────────────────────
# 登录类接口实测必须带 /client/v1 前缀；其余接口两种写法都列上逐个尝试
LOGIN_API = "/client/v1/login/v2/login"
SMS_API = "/client/v1/sms/v2/sendSmsCode"

# 密码加密公钥（RSA-OAEP-256，JWK 格式，取自客户端代码）
PASSWORD_PUB_N_B64URL = (
    "wf935Evk12yBMDq5u-2WGXG7rI80-WTu5BQXVnMm2HRZWKmOEdjW5XG4WhsbidDF2hhxO4emVqRlEE-"
    "EAZ8Ro936fk-oDvuYcLGbe_AUhgkb_uCldl32inF7dYXuONb-eigNSlGjapv8Ef__rFi0srg1dJg7_j8I"
    "QBm2RC5Hgd98-7QKokpjZHQmi-WpYAyaW7rZk1s6Ac6vZiAAq8HEa-eaEFTeQBcxrgYMwL65FfNFomh3"
    "Xvd1tMMtTx-dp4dfARfJB8UHhC8_xsUlHp14KYg4YRq9eRelnM_pV1ZXEAjPCbl6hwEsGrxWz40m-OeVs"
    "EZy-XGcoeeZfZ5dbTsicQ"
)


def _b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _mgf1_sha256(seed, length):
    out = bytearray()
    c = 0
    while len(out) < length:
        out.extend(hashlib.sha256(seed + c.to_bytes(4, "big")).digest())
        c += 1
    return bytes(out[:length])


def encrypt_password(password: str) -> str:
    """RSA-OAEP-256 加密（与客户端 AC() 一致），返回 base64"""
    n_pub = int.from_bytes(_b64url_decode(PASSWORD_PUB_N_B64URL), "big")
    k = (n_pub.bit_length() + 7) // 8
    hlen = 32
    msg = password.encode("utf-8")
    lhash = hashlib.sha256(b"").digest()
    ps = b"\x00" * (k - len(msg) - 2 * hlen - 2)
    db = lhash + ps + b"\x01" + msg
    seed = os.urandom(hlen)
    masked_db = bytes(a ^ b for a, b in zip(db, _mgf1_sha256(seed, len(db))))
    masked_seed = bytes(a ^ b for a, b in zip(seed, _mgf1_sha256(masked_db, hlen)))
    em = b"\x00" + masked_seed + masked_db
    sig = pow(int.from_bytes(em, "big"), 65537, n_pub).to_bytes(k, "big")
    return base64.b64encode(sig).decode("ascii")


# 服务端登录错误类型（data.type）
LOGIN_ERR_HINTS = {
    "ERROR_PASSWORD": "密码错误",
    "ERROR_SMSCODE": "验证码错误或已过期",
    "ERROR_RETRY_LIMIT": "尝试过于频繁，请稍后再试",
    "ERROR_USER_NOT_FOUND": "用户不存在",
    "ERROR_USER_DISABLE": "账号已被禁用",
}

STATUS_CANDIDATES = [
    ("/user_points/v1/level_info", "GET", None),
    ("/client/v1/user_points/v1/level_info", "GET", None),
    ("/user_points/v1/prizes", "GET", None),
    ("/task/v1/detail", "GET", None),
]
SIGNIN_CANDIDATES = [
    # 每日签到（星辉）唯一真实接口。实测 /user_points/v1/sign_in 是空接口：
    # 永远返回 {"status":true,"data":true} 但服务端不记账（签到日历不变），已弃用
    ("/task/v1/signIn", "POST", {}),
]
# 每日任务相关（笔记）
TASK_CANDIDATES = {
    "feed(浏览)": [("/community/v1/feed", "POST", {"page": 1, "pageSize": 10})],
    "like(点赞)": [("/community/v1/like", "POST", {"momentId": None, "like": True})],
    "comment(评论)": [("/community/v1/moment/comment_commit", "POST", {"momentId": None, "content": "打卡"})],
    "share(分享)": [("/community/v1/share", "POST", {"momentId": None})],
    "publish(发布)": [("/community/v1/publish", "POST", {"content": None})],
}

ALREADY_HINTS = ("已签到", "已经签到", "重复签到", "已领取", "今日已", "请勿重复")


# ══════════════════════════════════════════════════════════════════════
def cmd_whoami(client):
    print("[*] 校验凭证 ...")
    st, raw = client.request("/general/v3/settings?oopzChannel=Web&versionNo=88053", "GET")
    print("  " + client.describe(st, raw))
    if client.ok(st, raw):
        print("[+] 凭证有效")
        return True
    if st == 428:
        print("[!] token 无效或已过期")
    return False


def ensure_credentials():
    """确保凭证可用。

    凭证来源优先级：
      1. 环境变量 OOPZ_TOKEN / OOPZ_UID
      2. 脚本顶部 ACCOUNT_PHONE / ACCOUNT_PASSWORD（缺失或失效时自动密码登录）
      3. oopz_config.json（login 系列命令写入的 token；含 login_password 时可自动重登）
    """
    cfg = load_config()
    token = os.environ.get("OOPZ_TOKEN") or cfg.get("token")
    uid = os.environ.get("OOPZ_UID") or cfg.get("uid")

    # 脚本顶部配置了账号密码 → 无 token 时直接登录
    if not token and ACCOUNT_PHONE and ACCOUNT_PASSWORD:
        print(f"[*] 使用脚本顶部配置的账号 {ACCOUNT_PHONE} 自动登录 ...")
        if cmd_login_password(ACCOUNT_PHONE, ACCOUNT_PASSWORD):
            cfg2 = load_config()
            return OopzClient(cfg2.get("token"), cfg2.get("uid"))
        print("[!] 自动登录失败，请检查 ACCOUNT_PHONE / ACCOUNT_PASSWORD")
        sys.exit(3)

    if not token:
        has_top = bool(ACCOUNT_PHONE and ACCOUNT_PASSWORD)
        print("=" * 70)
        print("尚未配置凭证。三种方式：")
        print()
        print("  1) 脚本顶部填 ACCOUNT_PHONE / ACCOUNT_PASSWORD（推荐，改一次永久自动）")
        print("  2) 命令行登录（成功后写入 oopz_config.json）：")
        print("       python oopz_sign.py login-password --phone <手机号> --password <密码>")
        print("  3) 微信扫码：python oopz_sign.py login-wechat")
        if not has_top:
            print()
            print("（当前脚本顶部 ACCOUNT_PHONE/ACCOUNT_PASSWORD 为空）")
        print("=" * 70)
        sys.exit(2)

    client = OopzClient(token, uid)
    st, _ = client.request("/general/v3/settings?oopzChannel=Web&versionNo=88053", "GET")
    if st == 200:
        return client

    # token 失效 → 自动重登（优先脚本顶部配置，其次 config 里存的）
    print("[*] token 失效，尝试自动重新登录 ...")
    phone = ACCOUNT_PHONE or cfg.get("login_phone")
    password = ACCOUNT_PASSWORD or cfg.get("login_password")
    if phone and password:
        if cmd_login_password(phone, password):
            cfg2 = load_config()
            return OopzClient(cfg2.get("token"), cfg2.get("uid"))
        print("[!] 自动重登失败（密码可能已修改），请更新账号配置")
        sys.exit(3)
    print("[!] 凭证已失效且无密码可自动重登。")
    print("    在脚本顶部填 ACCOUNT_PHONE / ACCOUNT_PASSWORD 即可永久自动续期。")
    sys.exit(3)


def cmd_probe(client):
    print("\n########## 状态查询 ##########")
    for p, m, b in STATUS_CANDIDATES:
        st, raw = client.request(p, m, b)
        print("  " + client.describe(st, raw) + "\n")
    print("########## 签到 ##########")
    for p, m, b in SIGNIN_CANDIDATES:
        st, raw = client.request(p, m, b)
        print("  " + client.describe(st, raw) + "\n")


def cmd_check(client):
    print("[*] 查询状态 ...")
    info = _signin_state(client)
    if info:
        num, today = info
        print(f"    [签到] 今日{'已' if today else '未'}签到，连续签到 {num} 天")
    for p, m, b in STATUS_CANDIDATES:
        st, raw = client.request(p, m, b)
        print("  " + client.describe(st, raw))
        if client.ok(st, raw):
            return raw
    return None


def _signin_state(client):
    """读取每日签到状态，返回 (连续签到天数, 今日是否已签到)；读取失败返回 None"""
    st, raw = client.request("/task/v1/detail", "GET")
    if not client.ok(st, raw):
        return None
    try:
        s = (json.loads(raw).get("data") or {}).get("signInEveryDay") or {}
        if not s:
            return None
        return s.get("signInNum", 0), bool(s.get("isTodaySignIn"))
    except Exception:
        return None


def cmd_sign(client):
    print("[*] 执行签到 ...")
    for p, m, b in SIGNIN_CANDIDATES:
        st, raw = client.request(p, m, b)
        print("  " + client.describe(st, raw))
        if st == 428:
            log("签到失败: token 失效")
            print("[!] token 失效，请重新 login")
            return False
        # 已签到（幂等）：{"status":true,"data":null,"message":"今日已签到"}
        if st == 200 and any(h in raw for h in ALREADY_HINTS):
            log(f"今日已签到 [{m} {p}]")
            print("[=] 今日已经签到过了")
            return True
        # 签到成功：{"status":true,"data":{"awardType":"DIAMOND","awardNum":5},...}；
        # data 为 null 不算成功，避免空接口误报
        if client.ok(st, raw) and '"data":null' not in raw.replace(" ", ""):
            log(f"签到成功 [{m} {p}]")
            print(f"[+] 签到成功：{m} {p}")
            info = _signin_state(client)
            if info:
                num, today = info
                print(f"    已确认：今日{'已' if today else '仍未'}签到，连续签到 {num} 天")
                if not today:
                    print("[!] 服务端签到状态未更新，请稍后重试")
                    return False
            return True
    log("签到未成功")
    print("[!] 未签到成功，可运行 probe 查看各接口真实响应")
    return False


# 每日任务的默认执行内容
COMMENT_TEXT = "打卡打卡，内容不错，支持一下！"
PUBLISH_TITLES = ["今日份的游戏日常", "随手记录一下", "开黑碎片时间", "今天的对局感受", "水一发社区"]

UA_WEB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}


def _http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=UA_WEB)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _hitokoto(min_len=8, max_len=45):
    """一言 API：https://developer.hitokoto.cn/sentence/"""
    u = (f"https://v1.hitokoto.cn/?encode=json&min_length={min_len}&max_length={max_len}"
         "&c=a&c=b&c=c&c=d&c=e&c=f&c=i&c=k")
    try:
        return _http_get_json(u)
    except Exception:
        return None


def _bing_daily_image():
    """微软必应每日一图。返回 (图片字节, 宽, 高, 信息dict) 或 None"""
    try:
        meta = _http_get_json("https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1")
        img = (meta.get("images") or [None])[0]
        if not img:
            return None
        url = "https://cn.bing.com" + img.get("url", "")
        req = urllib.request.Request(url, headers=UA_WEB)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        w = h = 0
        try:
            from PIL import Image
            import io as _io
            im = Image.open(_io.BytesIO(data))
            w, h = im.size
        except Exception:
            pass
        return data, w, h, img
    except Exception:
        return None


def build_note_content(min_total=32):
    """正文来源：一言 API。单句不够长就拼接多条，保证 ≥20 字（目标 min_total）。

    返回 (正文, 引用出处列表)
    """
    parts, seen, total, sources = [], set(), 0, []
    for _ in range(8):
        h = _hitokoto(8, 45)
        if not h:
            continue
        s = (h.get("hitokoto") or "").strip()
        if not s or s in seen:
            time.sleep(0.6)
            continue
        seen.add(s)
        parts.append(s)
        src = h.get("from") or h.get("from_who") or ""
        if src:
            sources.append(src)
        total += len(s)
        if total >= min_total:
            break
        time.sleep(0.6)
    if not parts:
        parts = ["今天也是元气满满的一天呢"]
        sources = []
    return "\n\n".join(parts), sources


def _fetch_feed(client, n=12):
    st, raw = client.request("/community/v1/feed?pageSize=%d" % n, "GET")
    if not client.ok(st, raw):
        return []
    try:
        return (json.loads(raw).get("data") or {}).get("list") or []
    except Exception:
        return []


def _upload_image(client, data=None, filename="a.png", content_type="image/png"):
    """presign 上传图片到 COS。data 为空时上传 1x1 占位 PNG。

    返回资源 URL。注意必须保留 hostUrl 上的 CDN 签名（?sign=...）——
    发布接口校验资源地址，去掉签名的地址会报「上传类型错误」。
    """
    import struct
    import zlib

    if data is None:
        def chunk(t, d):
            cc = t + d
            return struct.pack(">I", len(d)) + cc + struct.pack(">I", zlib.crc32(cc))
        data = (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
                + chunk(b"IEND", b""))

    for _ in range(2):                      # 预签名 URL 有效期 3 分钟，过期就重新申请
        st, raw = client.request("/v1/upload/getCommunityImagePreSignUrl", "POST",
                                 {"fileName": filename, "contentType": content_type})
        if not client.ok(st, raw):
            return None
        up = (json.loads(raw).get("data") or {})
        put_url = up.get("url")
        if not put_url:
            return None
        for _ in range(3):                  # 上传偶发网络抖动，重试几次
            try:
                req = urllib.request.Request(put_url, data=data, method="PUT",
                                             headers={"Content-Type": content_type})
                urllib.request.urlopen(req, timeout=120)
                break
            except Exception:
                time.sleep(1.5)
        else:
            continue
        # hostUrl 是完整资源地址（含 path 与 sign 签名参数，发布时原样带上）
        if up.get("hostUrl"):
            return up["hostUrl"]
        path = up.get("path") or urllib.parse.unquote(urllib.parse.urlparse(put_url).path)
        origin = urllib.parse.urlparse(put_url)
        if not path.startswith("/"):
            path = "/" + path
        return f"{origin.scheme}://{origin.netloc}{path}"
    return None


def _publish_note(client, title, content, bing_info=None):
    """发布一篇笔记。有 bing_info（必应每日一图）时用真图，否则用 1x1 占位图。"""
    if bing_info:
        data, w, h, meta = bing_info
        res = _upload_image(client, data=data, filename="bing.jpg", content_type="image/jpeg")
        if not res:
            print("  [!] 必应图上传失败，改用占位图")
            res = _upload_image(client)
            w = h = 1
    else:
        res = _upload_image(client)
        w = h = 1
    if not res:
        print("  [!] 图片上传失败，跳过发布任务")
        return False
    body = {
        "groupType": "article",
        "title": title,
        "content": content,
        # 资源字段名必须是 imageList（驼峰，实测 APP 端结构）；
        # 写成 resources / image_list 会被忽略并返回「上传类型错误」
        "imageList": [{"cover": res, "resource": res, "resourceType": "IMAGE",
                       "sourceResource": "", "height": w and h or 1, "width": w or 1}],
    }
    st, raw = client.request("/community/v1/publish", "POST", body)
    ok = client.ok(st, raw)
    msg = ""
    try:
        d = json.loads(raw)
        msg = str(d.get("message") or d.get("error") or "")[:60]
    except Exception:
        pass
    print(f"  发布: {'成功' if ok else '失败(' + msg + ')'}")
    return ok


def _task_status(client):
    """拉取每日任务进度，返回 {id: (title, progress, state)}"""
    st, raw = client.request("/task/v1/detail", "GET")
    if not client.ok(st, raw):
        return {}
    try:
        lst = ((json.loads(raw).get("data") or {}).get("taskEveryDay") or {}).get("list") or []
        return {t["id"]: (t.get("title", ""), t.get("progress", ""), t.get("state", 0)) for t in lst}
    except Exception:
        return {}


def cmd_tasks(client):
    """每日任务全流程：浏览 → 点赞 → 评论 → 分享 → 发布 → 领取奖励"""
    print("[*] 每日任务 ...")
    before = _task_status(client)
    if before:
        for tid, (title, prog, state) in sorted(before.items()):
            mark = "已完成" if state != 0 else prog
            print(f"    [{tid}] {title}: {mark}")

    # 1) 浏览 10 篇：feed 拉列表 + 逐篇拉详情（服务端按 detail 查看计数）
    feed = _fetch_feed(client, 12)
    print(f"\n  浏览: 拉取 {len(feed)} 篇笔记")
    if not feed:
        print("  [!] feed 为空，后续任务无法进行")
        return False
    viewed = 0
    for mo in feed:
        if viewed >= 10:
            break
        st, raw = client.request(f"/community/v1/detail?momentId={mo['momentId']}", "GET")
        if client.ok(st, raw):
            viewed += 1
        time.sleep(0.3)
    print(f"  浏览: {viewed} 篇详情")

    # 2) 点赞 3 篇（顺带取消，避免给社区留痕迹？——任务奖励按行为计数，保留点赞）
    like_ok = 0
    for mo in feed:
        if like_ok >= 3:
            break
        st, raw = client.request("/community/v1/like", "POST",
                                 {"momentId": mo["momentId"], "author": mo["author"], "like": 1})
        if client.ok(st, raw):
            like_ok += 1
        time.sleep(0.4)
    print(f"  点赞: {like_ok} 篇成功")

    # 3) 评论 1 篇
    mo = feed[0]
    st, raw = client.request("/community/v1/moment/comment_commit", "POST",
                             {"momentId": mo["momentId"], "content": COMMENT_TEXT})
    comment_ok = client.ok(st, raw)
    print(f"  评论: {client.describe(st, raw)}")

    # 4) 分享 1 篇
    st, raw = client.request("/community/v1/share", "POST",
                             {"momentId": mo["momentId"], "author": mo["author"]})
    share_ok = client.ok(st, raw)
    print(f"  分享: {client.describe(st, raw)}")

    # 5) 发布 1 篇（20 字以上正文 + 图）—— 当天已完成就跳过，避免重复发帖
    #    正文：一言 API 拼接；配图：必应每日一图。
    #    "上传类型错误"根因是资源字段名（须为 imageList）与 URL 签名（须保留
    #    hostUrl 的 ?sign= 参数），已修复；仍保留一次重试覆盖偶发网络抖动
    pub_done = (before.get(9) or (None, None, 0))[2] != 0
    if pub_done:
        print("\n  发布: 今日已完成，跳过")
    else:
        import random
        title = random.choice(PUBLISH_TITLES)
        note_content, sources = build_note_content()
        if len(note_content) < 20:
            note_content += "\n今日打卡，顺便记录一下游戏日常！"
        bing = _bing_daily_image()
        if bing:
            bing_title = (bing[3].get("title") or "").strip()
            if bing_title and bing_title not in title:
                title = f"{title}｜{bing_title}"
            if sources:
                note_content += f"\n\n—— 摘自{'、'.join(sources[:2])}"
            note_content += f"\n\n配图：今日必应每日一图 · {bing[3].get('copyright', '')}"
        print(f"  发布: 《{title}》（正文 {len(note_content)} 字，配图 {'必应每日一图' if bing else '占位图'}）")
        publish_ok = _publish_note(client, title, note_content, bing_info=bing)
        if not publish_ok:
            time.sleep(3)
            print("  发布: 重试一次 ...")
            note_content2 = note_content + "\n补充：祝大家周末愉快，把把超神！"
            publish_ok = _publish_note(client, title, note_content2, bing_info=bing)

    # 6) 领取奖励（任务完成后 state 变化，尝试领取所有可领的）
    time.sleep(2)
    after = _task_status(client)
    print("\n  任务进度：")
    got = 0
    for tid, (title2, prog, state) in sorted(after.items()):
        print(f"    [{tid}] {title2}: {prog}  state={state}")
    for tid, (title2, prog, state) in after.items():
        # state: 0=未完成 1=可领取 2=已领取（以实测为准，逐个尝试）
        st, raw = client.request("/task/v1/receive", "POST", {"taskId": tid})
        if client.ok(st, raw):
            got += 1
            print(f"    [+] 领取成功: {title2}")
        time.sleep(0.3)
    print(f"\n  领取奖励: {got} 个")
    return True


def cmd_publish(client, content):
    import random
    if not content:
        content, sources = build_note_content()
        if len(content) < 20:
            content += "\n今日打卡，顺便记录一下游戏日常！"
        print(f"[*] 正文来自一言 API（{len(content)} 字）")
    if len(content) < 20:
        print("[!] 正文不足 20 字，任务要求正文 20 字以上")
        return False
    title = random.choice(PUBLISH_TITLES)
    bing = _bing_daily_image()
    if bing and bing[3].get("title"):
        title = f"{title}｜{bing[3]['title'].strip()}"
    print(f"[*] 发布笔记《{title}》...")
    return _publish_note(client, title, content, bing_info=bing)


def _login_request(client, body, cfg_extra=None):
    """发起登录请求并处理响应；成功时保存凭证返回 True"""
    st, raw = client.request(LOGIN_API, "POST", body, with_auth=False)
    print("  " + client.describe(st, raw))
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    data = payload.get("data") or {}
    token = uid = None
    if isinstance(data, dict):
        token = data.get("signature") or data.get("token")
        uid = data.get("uid")
    if token and uid is not None:
        cfg = load_config()
        cfg.update({"token": str(token), "uid": str(uid), "name": data.get("name"),
                    "platform": PLATFORM, "channel": CHANNEL, "app_version_number": APP_VER})
        if cfg_extra:
            cfg.update(cfg_extra)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        log(f"登录成功，凭证已保存 uid={uid}")
        print(f"\n[+] 登录成功！账号: {data.get('name')}  uid: {uid}")
        print(f"    凭证已写入 {CONFIG_PATH}")
        if cfg_extra and cfg_extra.get("login_password"):
            print("    （密码已加密保存在配置里 —— token 失效时将自动重新登录，全程无人值守）")
        print("\n[*] 立即校验凭证 ...")
        cmd_whoami(OopzClient(str(token), str(uid)))
        return True
    # 失败诊断
    dtype = data.get("type") if isinstance(data, dict) else None
    if dtype and dtype in LOGIN_ERR_HINTS:
        if dtype == "ERROR_RETRY_LIMIT" and isinstance(data, dict) and data.get("endTime"):
            wait_s = max(0, int(data["endTime"] / 1000 - time.time()))
            print(f"[!] {LOGIN_ERR_HINTS[dtype]}（约 {wait_s // 60 + 1} 分钟后可重试）")
        else:
            print(f"[!] 登录失败：{LOGIN_ERR_HINTS[dtype]}")
    elif payload.get("error"):
        print(f"[!] 服务端错误：{payload.get('error')}")
    else:
        print("[!] 登录未成功，完整响应：")
        print("    " + raw[:600])
    return False


def cmd_login_password(phone, password, store_password=True):
    """密码登录：全自动，零人工介入

    协议要点（逆向自客户端）：
      · 接口 /client/v1/login/v2/login（必须带 /client/v1 前缀）
      · 加密密码放在 code 字段（不是 password 字段）
      · 加密算法 RSA-OAEP-256，公钥硬编码在客户端
    store_password=True 时把密码存入配置，供 token 失效后自动重登。
    """
    print("[*] 密码登录（全自动）...")
    device_id = str(uuid.uuid4())
    body = {
        "auto": True,
        "code": encrypt_password(password),
        "loginType": "PASSWORD",
        "phone": phone,
        "autoRegister": False,
        "yunhaiToken": "",
        "deviceId": device_id,
        "deviceRam": "TBD",
        "deviceProcessor": "0",
        "loggedIn": device_id,
        "osEdition": "web",
        "osVersion": "web/_BrowserName.chrome",
        "resolution": "TBD",
        "graphics": "TBD",
        "clientVersion": "0.88.53",
    }
    client = OopzClient(verbose=True)
    extra = {"login_type": "PASSWORD", "login_phone": phone}
    if store_password:
        extra["login_password"] = password
    return _login_request(client, body, extra)


def cmd_login_sms(phone, code):
    """短信验证码登录：验证码需在手机 App 里点一次“获取验证码”后获得"""
    print("[*] 短信验证码登录 ...")
    device_id = str(uuid.uuid4())
    body = {
        "auto": True,
        "code": code,
        "loginType": "SMSCODE",
        "phone": phone,
        "autoRegister": True,
        "deviceId": device_id,
        "deviceRam": "TBD",
        "deviceProcessor": "0",
        "loggedIn": device_id,
        "osEdition": "web",
        "osVersion": "web/_BrowserName.chrome",
        "resolution": "TBD",
        "graphics": "TBD",
        "clientVersion": "0.88.53",
    }
    client = OopzClient(verbose=True)
    return _login_request(client, body, {"login_type": "SMSCODE", "login_phone": phone})


def cmd_login(phone=None, password=None, code=None):
    """登录入口：优先密码登录（全自动），否则短信验证码"""
    interactive = phone is None
    if not phone:
        phone = input("请输入手机号: ").strip()
    if not phone:
        print("[!] 手机号不能为空")
        return False

    # 密码登录优先（无需任何人工验证）
    if password is None and interactive and not code:
        try_use_pwd = input("是否有密码？[Y/n]（密码登录全自动；n 则走短信验证码）: ").strip().lower()
        if try_use_pwd in ("", "y", "yes"):
            password = input("请输入密码: ").strip()
    if password:
        ok = cmd_login_password(phone, password)
        if ok:
            return True
        print("\n[i] 密码登录失败，可改用短信验证码方式（python oopz_sign.py login-sms）")
        return False

    print()
    print("── 获取验证码 ──────────────────────────────────────────")
    print("请打开【手机上的 Oopz App】，用这个手机号点一次“获取验证码”，")
    print("（发短信接口要求腾讯人机验证，无法纯脚本触发，这一步需人工点）")
    print("收到短信后把 6 位验证码填到下面。")
    print("───────────────────────────────────────────────────────")

    interactive_code = code is None
    for attempt in range(1, 4):
        if attempt == 1 and code:
            current = code
        elif interactive_code:
            current = input(f"短信验证码{'（第 %d 次尝试）' % attempt if attempt > 1 else ''}: ").strip()
        else:
            return False
        if not current:
            print("[!] 验证码不能为空")
            if not interactive_code:
                return False
            continue

        client = OopzClient(verbose=True)
        device_id = str(uuid.uuid4())
        body = {
            "auto": True, "code": current, "loginType": "SMSCODE", "phone": phone,
            "autoRegister": True, "deviceId": device_id, "deviceRam": "TBD",
            "deviceProcessor": "0", "loggedIn": device_id, "osEdition": "web",
            "osVersion": "web/_BrowserName.chrome", "resolution": "TBD",
            "graphics": "TBD", "clientVersion": "0.88.53",
        }
        print("\n[*] 正在登录 ...")
        return _login_request(client, body, {"login_type": "SMSCODE", "login_phone": phone})
    return False


def cmd_loop(client, at):
    print(f"[*] 常驻模式：每天 {at} 签到（Ctrl+C 退出）")
    while True:
        if time.strftime("%H:%M") == at:
            print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 定时任务 =====")
            if cmd_whoami(client):
                cmd_sign(client)
            time.sleep(70)
        else:
            time.sleep(20)


WECHAT_URL_API = "/v1/login/wxLoginUrl"
WECHAT_QUERY_API = "/v1/login/v2/loginQuery?state="


def _device_body():
    dev = str(uuid.uuid4())
    return {"deviceRam": "TBD", "deviceProcessor": "0", "loggedIn": dev,
            "osVersion": "web/_BrowserName.chrome", "osEdition": "web",
            "resolution": "TBD", "graphics": "TBD", "clientVersion": "0.88.53", "auto": True}, dev


def _open_file_viewer(path):
    """用系统默认程序打开图片（Windows/Win 服务器也可用）"""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def _render_qr_terminal(url):
    """在终端渲染二维码（每个模块 1 列宽，半块字符两行并一行）。

      上黑下黑=█  上黑下白=▀  上白下黑=▄  上白下白=空格
    不会错位粘连；另生成 PNG 备用（只给路径不弹窗）。
    """
    try:
        import qrcode
    except ImportError:
        print("[!] 未安装 qrcode 库（pip install qrcode），只能输出链接：")
        print(url)
        return
    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(url)
    qr.make(fit=True)
    m = qr.get_matrix()
    rows = len(m)

    print()
    print("请用微信「扫一扫」扫描下面的二维码（若显示错乱，用同目录下的 login_qr.png）：")
    print()
    for y in range(0, rows, 2):
        line = []
        for x in range(len(m[y])):
            top = m[y][x]
            bottom = m[y + 1][x] if y + 1 < rows else False
            line.append("█" if (top and bottom) else "▀" if top else "▄" if bottom else " ")
        print("".join(line))
    print()

    png_path = os.path.join(SCRIPT_DIR, "login_qr.png")
    try:
        qr.make_image(fill_color="black", back_color="white").save(png_path)
        print(f"[*] PNG 备用: {png_path}")
    except Exception:
        pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """回调可能 302，我们只要首跳响应即可"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _wechat_fetch_qr(login_url):
    """请求微信 qrconnect 页面，返回 (uuid, 真二维码图片字节)。

    login_url 是 Oopz 下发的 qrconnect 链接（state 已含其中）。
    页面里的 uuid 对应真正要扫的二维码：
      图片 https://open.weixin.qq.com/connect/qrcode/{uuid}
      内容 https://open.weixin.qq.com/connect/confirm?uuid={uuid}
    """
    UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}
    html = urllib.request.urlopen(
        urllib.request.Request(login_url, headers=UA), timeout=20).read().decode("utf-8", "replace")
    mt = re.search(r"uuid=([A-Za-z0-9_=\-]+)", html)
    if not mt:
        raise RuntimeError("qrconnect 页面中未找到 uuid")
    uuid = mt.group(1)
    img = urllib.request.urlopen(
        urllib.request.Request(f"https://open.weixin.qq.com/connect/qrcode/{uuid}", headers=UA),
        timeout=20).read()
    return uuid, img


def _wechat_long_poll(uuid, timeout_s=30):
    """微信长轮询一次。返回 wx_errcode 与 wx_code。

    408=等待扫码  405=已扫码待确认  200=已确认（wx_code 有值）
    """
    UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(
                f"https://long.open.weixin.qq.com/connect/l/qrconnect?uuid={uuid}", headers=UA),
            timeout=timeout_s)
        body = r.read().decode("utf-8", "replace")
    except Exception:
        return None, ""
    err = re.search(r"wx_errcode=(\d+)", body)
    code = re.search(r"wx_code='([^']*)'", body)
    return (int(err.group(1)) if err else None), (code.group(1) if code else "")


def cmd_login_wechat(timeout=180, poll=2.0):
    """微信扫码登录：终端直接显示「真二维码」，手机扫一下即完成。

    流程（逆向自客户端 + 微信开放平台页面，全部实测）：
      1. POST /v1/login/wxLoginUrl → Oopz 下发 state + qrconnect 链接
      2. 请求 qrconnect 页面拿 uuid → 下载真二维码（connect/qrcode/{uuid}）→ 终端渲染
         （真二维码内容 = connect/confirm?uuid=xxx，手机扫它才直接弹授权确认，
           而不是先打开一个还要再扫一次的网页）
      3. 微信长轮询 uuid 拿 wx_code；同时 Oopz 服务端收到微信回调后使 state 生效
      4. 轮询 GET /v1/login/v2/loginQuery?state=xxx，signature/uid 非空即成功
    """
    print("[*] 微信扫码登录 ...")
    client = OopzClient(verbose=False)
    body, dev = _device_body()
    st, raw = client.request(WECHAT_URL_API, "POST", body, with_auth=False)
    if not client.ok(st, raw):
        print("  " + client.describe(st, raw))
        print("[!] 获取微信授权链接失败")
        return False
    data = json.loads(raw).get("data") or {}
    login_url, state = data.get("loginUrl"), data.get("state")
    if not login_url or not state:
        print("[!] 响应中缺少 loginUrl/state")
        return False

    try:
        uuid, img_bytes = _wechat_fetch_qr(login_url)
    except Exception as e:
        print(f"[!] 获取微信二维码失败: {e}")
        print(f"    可手动在浏览器打开下面的链接扫码：\n    {login_url}")
        return False

    # 保存真二维码 PNG（不弹窗）
    png_path = os.path.join(SCRIPT_DIR, "login_qr.png")
    try:
        with open(png_path, "wb") as f:
            f.write(img_bytes)
    except Exception:
        png_path = None

    print(f"[*] state = {state}")
    # 把真二维码内容渲染到终端
    import io as _io
    try:
        import zxingcpp
        from PIL import Image
        confirm_url = zxingcpp.read_barcodes(Image.open(_io.BytesIO(img_bytes)))[0].text
        _render_qr_terminal(confirm_url)
    except Exception:
        # 解码失败就直接展示原始图片路径
        print(f"[*] 真二维码图片: {png_path or '(生成失败)'}")
        print(f"    或用浏览器打开: {login_url}")
    if png_path:
        print(f"    （上面二维码扫不出来时，可打开 {png_path} 扫描）")

    print(f"[*] 等待扫码确认（最长 {timeout} 秒）...")
    if not os.path.exists(CONFIG_PATH):
        json.dump({}, open(CONFIG_PATH, "w", encoding="utf-8"))

    deadline = time.time() + timeout
    waited = 0
    wxcode = ""
    while time.time() < deadline and not wxcode:
        t0 = time.time()
        err, wxcode = _wechat_long_poll(uuid, timeout_s=30)
        waited += time.time() - t0
        if wxcode:
            break
        label = {408: "等待扫码", 405: "已扫码，请在手机上确认"}.get(err, f"errcode={err}")
        print(f"\r    {int(waited):3d} 秒 · {label}   ", end="", flush=True)

    print()
    if not wxcode:
        print("[!] 超时未完成扫码。可重新运行（二维码有时效）。")
        return False
    print(f"[+] 微信已确认！（{int(waited)} 秒）")

    # 关键一步：模拟浏览器的回调跳转。
    # 真实流程中 qrconnect 页面的 JS 拿到 wx_code 后会自动 302 到
    #   redirect_uri?code=wx_code&state=xxx
    # 该回调打到 Oopz 网关后 state 才会生效。脚本必须自己请求这个回调 URL。
    print("[*] 回调 Oopz 网关（模拟浏览器跳转）...")
    try:
        redirect_uri = urllib.parse.parse_qs(urllib.parse.urlparse(login_url).query)["redirect_uri"][0]
        cb = f"{redirect_uri}?code={urllib.parse.quote(wxcode)}&state={urllib.parse.quote(state)}"
        cb_req = urllib.request.Request(cb, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"})
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            resp = opener.open(cb_req, timeout=20)
            status, body = resp.status, resp.read().decode("utf-8", "replace")[:200]
        except urllib.error.HTTPError as ex:
            status, body = ex.code, ex.read().decode("utf-8", "replace")[:200]
        print(f"    回调 {cb[:80]}...")
        print(f"    -> HTTP {status}  {body[:120]}")
    except Exception as e:
        print(f"[!] 回调请求失败: {e}")

    # 微信回调 Oopz 网关后 state 生效；轮询 Oopz 拿凭证
    print("[*] 获取登录凭证 ...")
    deadline = time.time() + 30
    while time.time() < deadline:
        st, raw = client.request(WECHAT_QUERY_API + state, "GET", None, with_auth=False)
        if st == 200:
            try:
                d = (json.loads(raw).get("data") or {})
            except Exception:
                d = {}
            sig, uid = d.get("signature"), d.get("uid")
            if sig and uid:
                cfg = load_config()
                cfg.update({"token": str(sig), "uid": str(uid),
                            "name": d.get("nickname"), "platform": PLATFORM,
                            "channel": CHANNEL, "app_version_number": APP_VER,
                            "login_type": "WECHAT", "wx_union_id": d.get("wxUnionId")})
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                log(f"微信扫码登录成功 uid={uid}")
                print(f"[+] 登录成功！nickname = {d.get('nickname')}  uid = {uid}")
                print(f"    凭证已写入 {CONFIG_PATH}")
                if d.get("phone"):
                    print("\n[*] 立即校验凭证 ...")
                    cmd_whoami(OopzClient(str(sig), str(uid)))
                    return True
                print("\n[!] 该微信尚未绑定手机号，已保存当前凭证，可尝试直接运行 sign。")
                return True
        time.sleep(poll)
    print("[!] 微信已确认但 Oopz 未返回凭证。可能网络延迟，稍后重跑 login-wechat 或改用密码登录。")
    return False


def cmd_login_web():
    """备选：用浏览器登录助手（需要 Node + 浏览器）"""
    if not os.path.exists(LOGIN_HELPER):
        print(f"[!] 未找到登录助手: {LOGIN_HELPER}")
        return False
    print("[*] 启动浏览器登录助手 ...")
    try:
        rc = subprocess.call(["node", LOGIN_HELPER], cwd=SCRIPT_DIR)
    except FileNotFoundError:
        print("[!] 未找到 node")
        return False
    if rc == 0:
        cfg = load_config()
        if cfg.get("token"):
            cmd_whoami(OopzClient(cfg.get("token"), cfg.get("uid")))
            return True
    return False


def main():
    p = argparse.ArgumentParser(description="Oopz 自动签到 / 每日任务")
    p.add_argument("command", nargs="?", default="sign",
                   choices=["login", "login-password", "login-sms", "login-wechat", "login-web",
                            "whoami", "check", "sign", "tasks", "publish", "probe", "loop"])
    p.add_argument("args", nargs="*", help="publish 的正文")
    p.add_argument("--phone", default=None, help="login 用：手机号")
    p.add_argument("--password", default=None, help="login-password 用：密码")
    p.add_argument("--code", default=None, help="login-sms 用：短信验证码")
    p.add_argument("--timeout", type=int, default=180, help="login-wechat 用：扫码超时秒数")
    p.add_argument("--at", default="08:30")
    opts = p.parse_args()

    if opts.command == "login":
        cmd_login(opts.phone, None, opts.code)
        return
    if opts.command == "login-password":
        if not opts.phone or not opts.password:
            print("用法: python oopz_sign.py login-password --phone <手机号> --password <密码>")
            sys.exit(1)
        cmd_login_password(opts.phone, opts.password)
        return
    if opts.command == "login-sms":
        if not opts.phone or not opts.code:
            print("用法: python oopz_sign.py login-sms --phone <手机号> --code <验证码>")
            sys.exit(1)
        cmd_login_sms(opts.phone, opts.code)
        return
    if opts.command == "login-wechat":
        cmd_login_wechat(timeout=opts.timeout)
        return
    if opts.command == "login-web":
        cmd_login_web()
        return

    cfg = load_config()
    token = os.environ.get("OOPZ_TOKEN") or cfg.get("token")
    uid = os.environ.get("OOPZ_UID") or cfg.get("uid")

    if not token:
        print("=" * 70)
        print("尚未配置登录凭证。三种登录方式（任选其一，凭证自动保存）：")
        print()
        print("  1) 密码登录（推荐，全自动，token 过期自动续期）：")
        print("       python oopz_sign.py login-password --phone 手机号 --password 密码")
        print()
        print("  2) 微信扫码（二维码显示在终端，Linux 可直接扫）：")
        print("       python oopz_sign.py login-wechat")
        print()
        print("  3) 短信验证码（验证码需在手机 App 里点一次获取）：")
        print("       python oopz_sign.py login")
        print("=" * 70)
        sys.exit(2)

    client = ensure_credentials()
    print(f"[i] 网关 {GATEWAY}   uid={client.uid or '(未知)'}")

    if opts.command == "whoami":
        cmd_whoami(client)
    elif opts.command == "check":
        cmd_check(client)
    elif opts.command == "sign":
        if cmd_whoami(client):
            cmd_sign(client)
    elif opts.command == "tasks":
        cmd_tasks(client)
    elif opts.command == "publish":
        cmd_publish(client, " ".join(opts.args).strip())
    elif opts.command == "probe":
        cmd_probe(client)
    elif opts.command == "loop":
        cmd_loop(client, opts.at)


if __name__ == "__main__":
    main()
