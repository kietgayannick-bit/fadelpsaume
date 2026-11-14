"""Fadelpsaume - analyse et génération des liens de serveurs.

Formats gérés : vmess:// vless:// trojan:// ss:// et sshdns:// (format propre à Fadelpsaume).
"""
import base64
import json
import re
import time
import uuid
from urllib.parse import urlparse, parse_qs, unquote, quote

PROTOCOLS = ("vmess", "vless", "trojan", "ss", "sshdns")

# Seules ces clés sont conservées dans un serveur (évite d'enregistrer n'importe quoi).
ALLOWED_KEYS = {
    "id", "name", "protocol", "address", "port", "created", "note", "expires", "locked",
    # V2Ray / Xray
    "uuid", "alterId", "encryption", "flow", "password", "method",
    "network", "security", "sni", "host", "path", "serviceName", "headerType",
    "alpn", "fingerprint", "allowInsecure", "publicKey", "shortId", "spiderX", "mode", "extra",
    # proxy + payload (style HTTP Injector)
    "proxy", "proxySni", "payload",
    # SSH SlowDNS
    "ns_domain", "resolver", "dns_type", "user", "pubkey",
}
INT_KEYS = {"port", "alterId", "created"}
BOOL_KEYS = {"allowInsecure", "locked"}

LINK_RE = re.compile(r"(?:vmess|vless|trojan|ss|sshdns)://[^\s<>\"']+", re.I)


NET_ALIAS = {"raw": "tcp", "splithttp": "xhttp", "http": "h2", "http2": "h2", "mkcp": "kcp",
             "websocket": "ws", "": "tcp"}
SEC_ALIAS = {"xtls": "tls", "": "none"}


def norm_net(v):
    v = (v or "tcp").strip().lower()
    return NET_ALIAS.get(v, v)


def norm_sec(v, default="none"):
    v = (v if v is not None else default).strip().lower() or default
    return SEC_ALIAS.get(v, v)


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def new_id():
    return uuid.uuid4().hex[:10]


def b64decode(s):
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s).decode("utf-8", "replace")


def b64encode(s, urlsafe=False, pad=True):
    raw = s.encode() if isinstance(s, str) else s
    out = (base64.urlsafe_b64encode(raw) if urlsafe else base64.b64encode(raw)).decode()
    return out if pad else out.rstrip("=")


def _base(protocol, name, address, port):
    return {
        "id": new_id(),
        "name": (name or address or "").strip(),
        "protocol": protocol,
        "address": address,
        "port": int(port),
        "network": "tcp",
        "security": "none",
        "created": int(time.time()),
    }


# ----------------------------------------------------------------------------
# Nettoyage / validation
# ----------------------------------------------------------------------------
def clean(s):
    """Normalise un serveur : types corrects, clés inconnues supprimées."""
    out = {}
    for k, v in (s or {}).items():
        if k not in ALLOWED_KEYS:
            continue
        if k in INT_KEYS:
            try:
                v = int(v) if v not in ("", None) else 0
            except (TypeError, ValueError):
                v = 0
        elif k in BOOL_KEYS:
            v = v in (True, 1, "1", "true", "True", "on")
        elif isinstance(v, str):
            v = v.strip()
        elif v is None:
            v = ""
        out[k] = v
    out.setdefault("id", new_id())
    out.setdefault("created", int(time.time()))
    return out


def validate(s):
    """Retourne None si le serveur est correct, sinon un message d'erreur (français)."""
    p = s.get("protocol")
    if p not in PROTOCOLS:
        return "Protocole inconnu."
    if not (s.get("name") or "").strip():
        return "Le nom du serveur est obligatoire."
    port = int(s.get("port") or 0)
    if p == "sshdns":
        if not s.get("user"):
            return "Le nom d'utilisateur SSH est obligatoire."
        if s.get("ns_domain"):
            if not s.get("pubkey"):
                return "La clé publique (dnstt) est obligatoire avec un Name Server."
            if not s.get("resolver"):
                return "Le DNS resolver est obligatoire avec un Name Server."
        elif not s.get("address"):
            return "Renseigne soit le Name Server (SlowDNS), soit l'IP du serveur SSH."
        if s.get("address") and not (1 <= port <= 65535):
            return "Port invalide (1 à 65535)."
        return None
    if not s.get("address"):
        return "L'adresse du serveur est obligatoire."
    if not (1 <= port <= 65535):
        return "Port invalide (1 à 65535)."
    if p in ("vmess", "vless") and not s.get("uuid"):
        return "L'UUID (ID utilisateur) est obligatoire."
    if p == "trojan" and not s.get("password"):
        return "Le mot de passe est obligatoire."
    if p == "ss":
        if not s.get("method"):
            return "La méthode de chiffrement est obligatoire."
        if s.get("method") != "none" and not s.get("password"):
            return "Le mot de passe est obligatoire."
    px = (s.get("proxy") or "").strip()
    if px:
        h, _, pt = px.rpartition(":")
        if not h or not pt.isdigit() or not (1 <= int(pt) <= 65535):
            return "Proxy invalide : écris hôte:port (ex. 1.2.3.4:8080)."
    if s.get("security") == "reality" and not s.get("publicKey"):
        return "La clé publique Reality (pbk) est obligatoire."
    return None


# ----------------------------------------------------------------------------
# Analyse (lien -> serveur)
# ----------------------------------------------------------------------------
def _parse_vmess(uri):
    raw = uri.split("://", 1)[1].strip()
    frag = ""
    if "#" in raw:
        raw, frag = raw.split("#", 1)
    try:
        j = json.loads(b64decode(raw))
    except Exception:
        raise ValueError("Lien vmess invalide (base64/JSON illisible).")
    if not j.get("add") or not j.get("port") or not j.get("id"):
        raise ValueError("Lien vmess incomplet.")
    s = _base("vmess", j.get("ps") or unquote(frag), j["add"], j["port"])
    net = norm_net(j.get("net"))
    tlsv = str(j.get("tls") or "").lower()
    s.update(
        uuid=j["id"],
        alterId=int(j.get("aid") or 0),
        encryption=j.get("scy") or "auto",
        network=net,
        security=("reality" if tlsv == "reality" else "tls" if tlsv in ("tls", "true", "1", "xtls") else "none"),
        allowInsecure=truthy(j.get("allowInsecure") or j.get("insecure") or j.get("allow_insecure")),
        publicKey=j.get("pbk") or "", shortId=j.get("sid") or "", spiderX=j.get("spx") or "",
        proxy=j.get("proxy") or "", proxySni=j.get("proxySni") or "", payload=j.get("payload") or "",
        sni=j.get("sni") or "",
        host=j.get("host") or "",
        path=j.get("path") or "",
        headerType=j.get("type") or "none",
        alpn=j.get("alpn") or "",
        fingerprint=j.get("fp") or "",
    )
    if net == "grpc":
        s["serviceName"] = s["path"]
    if net == "xhttp":
        s["mode"] = j.get("mode") or ""
    return s


def _parse_std(uri, proto):
    p = urlparse(uri)
    try:
        host, port = p.hostname, p.port
    except ValueError:
        raise ValueError("Port invalide dans le lien %s." % proto)
    if not host or not port:
        raise ValueError("Lien %s incomplet (adresse ou port manquant)." % proto)
    qs = parse_qs(p.query, keep_blank_values=True)

    def q(key, default=""):
        v = qs.get(key)
        return v[0] if v else default

    s = _base(proto, unquote(p.fragment), host, port)
    cred = unquote(p.username or "")
    s["network"] = norm_net(q("type", "tcp"))
    s["security"] = norm_sec(q("security"), "tls" if proto == "trojan" else "none")
    s["sni"] = q("sni") or q("peer")
    s["host"] = q("host")
    s["path"] = q("path")
    s["serviceName"] = q("serviceName")
    s["headerType"] = q("headerType", "none")
    s["alpn"] = q("alpn")
    s["fingerprint"] = q("fp")
    s["allowInsecure"] = any(truthy(q(k)) for k in ("allowInsecure", "insecure", "allow_insecure"))
    s["mode"] = q("mode")
    s["extra"] = q("extra")
    s["proxy"] = q("proxy")
    s["proxySni"] = q("proxysni") or q("proxySni")
    s["payload"] = q("payload")
    if s["network"] == "kcp":
        s["path"] = q("seed") or s["path"]
    if s["network"] == "grpc" and not s["serviceName"]:
        s["serviceName"] = s["path"]
    s["publicKey"] = q("pbk")
    s["shortId"] = q("sid")
    s["spiderX"] = q("spx")
    if proto == "vless":
        if not cred:
            raise ValueError("Lien vless sans UUID.")
        s["uuid"] = cred
        s["encryption"] = q("encryption", "none")
        s["flow"] = q("flow")
    else:
        if not cred:
            raise ValueError("Lien trojan sans mot de passe.")
        s["password"] = cred
    return s


def _parse_ss(uri):
    rest = uri.split("://", 1)[1].strip()
    frag = ""
    if "#" in rest:
        rest, frag = rest.split("#", 1)
    query = ""
    if "?" in rest:
        rest, query = rest.split("?", 1)
    rest = rest.rstrip("/")
    try:
        if "@" in rest:
            userinfo, hostport = rest.rsplit("@", 1)
            u = unquote(userinfo)
            if ":" not in u:
                u = b64decode(userinfo)
        else:
            decoded = b64decode(rest)
            u, hostport = decoded.rsplit("@", 1)
        method, password = u.split(":", 1)
        host, port = hostport.rsplit(":", 1)
        host = host.strip("[]")
        s = _base("ss", unquote(frag), host, int(port))
    except Exception:
        raise ValueError("Lien Shadowsocks invalide.")
    s["method"] = method
    s["password"] = password
    try:
        qs = parse_qs(query, keep_blank_values=True)
    except Exception:
        qs = {}

    def q(key, default=""):
        v = qs.get(key)
        return v[0] if v else default

    plugin = q("plugin")
    if plugin:
        name, *opts = plugin.split(";")
        if "v2ray-plugin" not in name and "xray-plugin" not in name:
            raise ValueError("Plugin Shadowsocks « %s » non pris en charge (seuls v2ray-plugin/xray-plugin le sont)." % name)
        o = {}
        for it in opts:
            k, _, v = it.partition("=")
            o[k.strip()] = v.strip()
        s["network"] = "ws"
        s["security"] = "tls" if "tls" in o else "none"
        s["host"] = o.get("host", "")
        s["path"] = o.get("path", "")
        if o.get("mode") == "quic":
            raise ValueError("Mode quic du plugin non pris en charge.")
    else:
        s["network"] = norm_net(q("type", "tcp"))
        s["security"] = norm_sec(q("security"))
        s["host"], s["path"], s["sni"] = q("host"), q("path"), q("sni")
        s["serviceName"] = q("serviceName")
        s["alpn"], s["fingerprint"] = q("alpn"), q("fp")
        s["allowInsecure"] = any(truthy(q(k)) for k in ("allowInsecure", "insecure"))
    s["proxy"], s["proxySni"], s["payload"] = q("proxy"), q("proxysni"), q("payload")
    return s


def _parse_sshdns(uri):
    raw = uri.split("://", 1)[1].strip()
    try:
        j = json.loads(b64decode(raw))
    except Exception:
        raise ValueError("Lien sshdns invalide.")
    j["protocol"] = "sshdns"
    s = clean(j)
    s["id"] = new_id()
    return s


def parse_link(uri):
    uri = uri.strip()
    scheme = uri.split("://", 1)[0].lower()
    if scheme == "vmess":
        s = _parse_vmess(uri)
    elif scheme in ("vless", "trojan"):
        s = _parse_std(uri, scheme)
    elif scheme == "ss":
        s = _parse_ss(uri)
    elif scheme == "sshdns":
        s = _parse_sshdns(uri)
    else:
        raise ValueError("Format non pris en charge.")
    s = clean(s)
    err = validate(s)
    if err:
        raise ValueError(err)
    return s


def parse_any(text):
    """Extrait tous les liens d'un texte. Retourne (serveurs, erreurs)."""
    text = (text or "").strip()
    if text and "://" not in text:  # peut-être un abonnement encodé en base64
        try:
            text = b64decode(text)
        except Exception:
            pass
    servers, errors = [], []
    for link in LINK_RE.findall(text):
        try:
            servers.append(parse_link(link))
        except ValueError as e:
            errors.append(str(e))
    if not servers and not errors:
        errors.append("Aucun lien vmess://, vless://, trojan:// ou ss:// trouvé.")
    return servers, errors


# ----------------------------------------------------------------------------
# Génération (serveur -> lien)
# ----------------------------------------------------------------------------
def _query(s, keys):
    pairs = []
    for key, field in keys:
        v = s.get(field)
        if v in (None, "", False):
            continue
        if v is True:
            v = "1"
        pairs.append("%s=%s" % (key, quote(str(v), safe="")))
    return "&".join(pairs)


def _host(addr):
    return "[%s]" % addr if ":" in addr and not addr.startswith("[") else addr


def build_link(s):
    p = s["protocol"]
    name = quote(s.get("name") or "", safe="")
    if p == "vmess":
        j = {
            "v": "2", "ps": s.get("name", ""), "add": s["address"], "port": str(s["port"]),
            "id": s["uuid"], "aid": str(s.get("alterId") or 0), "scy": s.get("encryption") or "auto",
            "net": s.get("network") or "tcp", "type": s.get("headerType") or "none",
            "host": s.get("host", ""),
            "path": s.get("serviceName") if s.get("network") == "grpc" else s.get("path", ""),
            "tls": s.get("security") if s.get("security") in ("tls", "reality") else "",
            "sni": s.get("sni", ""), "alpn": s.get("alpn", ""), "fp": s.get("fingerprint", ""),
        }
        for k_json, k_s in (("proxy", "proxy"), ("proxySni", "proxySni"), ("payload", "payload"), ("mode", "mode")):
            if s.get(k_s):
                j[k_json] = s[k_s]
        if s.get("allowInsecure"):
            j["allowInsecure"] = "1"
        return "vmess://" + b64encode(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
    if p in ("vless", "trojan"):
        keys = [("type", "network"), ("security", "security"), ("sni", "sni"), ("host", "host"),
                ("path", "path"), ("serviceName", "serviceName"), ("alpn", "alpn"),
                ("fp", "fingerprint"), ("pbk", "publicKey"), ("sid", "shortId"),
                ("spx", "spiderX"), ("allowInsecure", "allowInsecure"), ("mode", "mode"),
                ("extra", "extra"), ("proxy", "proxy"), ("proxysni", "proxySni"), ("payload", "payload")]
        if s.get("headerType") not in (None, "", "none"):
            keys.append(("headerType", "headerType"))
        if p == "vless":
            keys = [("encryption", "encryption"), ("flow", "flow")] + keys
            cred = quote(s["uuid"], safe="")
        else:
            cred = quote(s["password"], safe="")
        qs = _query(s, keys)
        return "%s://%s@%s:%s%s#%s" % (p, cred, _host(s["address"]), s["port"],
                                       ("?" + qs) if qs else "", name)
    if p == "ss":
        ui = b64encode("%s:%s" % (s["method"], s.get("password", "")), urlsafe=True, pad=False)
        keys = [("type", "network"), ("security", "security"), ("sni", "sni"), ("host", "host"), ("path", "path"),
                ("serviceName", "serviceName"), ("alpn", "alpn"), ("fp", "fingerprint"),
                ("allowInsecure", "allowInsecure"), ("proxy", "proxy"), ("proxysni", "proxySni"),
                ("payload", "payload")]
        if s.get("network") in (None, "", "tcp"):
            keys = [k for k in keys if k[0] in ("proxy", "proxysni", "payload")]
        elif s.get("security") in (None, "", "none"):
            keys = [k for k in keys if k[0] not in ("sni", "alpn", "fp", "allowInsecure")]
        qs = _query(s, keys)
        return "ss://%s@%s:%s%s#%s" % (ui, _host(s["address"]), s["port"], ("?" + qs) if qs else "", name)
    if p == "sshdns":
        j = {k: v for k, v in s.items() if k in ALLOWED_KEYS and k not in ("id", "created", "locked")}
        return "sshdns://" + b64encode(json.dumps(j, ensure_ascii=False, separators=(",", ":")), urlsafe=True)
    raise ValueError("Protocole inconnu.")
