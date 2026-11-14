"""Fadelpsaume - moteur de connexion.

Le moteur pilote Xray-core (vmess / vless / trojan / shadowsocks) et, pour le mode
SSH SlowDNS, enchaîne  dnstt-client -> ssh -D -> Xray.  Dans tous les cas l'utilisateur
obtient un proxy local SOCKS5 + HTTP et des compteurs de trafic fiables (statistiques Xray).
"""
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import threading
import time

from store import HOME, LOG, is_expired
import relay as relaymod

PRIVATE_CIDRS = [
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
    "169.254.0.0/16", "100.64.0.0/10", "fc00::/7", "fe80::/10", "::1/128",
]


class EngineError(Exception):
    pass


# Crochets facultatifs (utilisés par la version Android pour ouvrir / fermer le tunnel VPN système)
HOOKS = {"up": None, "down": None}


def _hook(name, *args):
    fn = HOOKS.get(name)
    if fn:
        try:
            fn(*args)
        except Exception as e:  # noqa
            LOG.add("Crochet %s : %s" % (name, e), "WARN")


class ThreadProc:
    """Faux processus pour un travail Python en thread (client SSH intégré)."""

    def __init__(self, obj):
        self.obj = obj
        self.pid = -1
        self.returncode = None
        self.stdout = iter(())

    def poll(self):
        if self.obj.alive():
            return None
        self.returncode = 1
        return 1

    def wait(self, timeout=None):
        return self.returncode

    def stop(self):
        self.obj.stop()


# ----------------------------------------------------------------------------
# Outils
# ----------------------------------------------------------------------------
def find_bin(name, env=None):
    cands = []
    if env and os.environ.get(env):
        cands.append(os.environ[env])
    cands.append(os.path.join(HOME, "bin", name))
    if os.environ.get("PREFIX"):
        cands.append(os.path.join(os.environ["PREFIX"], "bin", name))
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which(name)


def _internal_ssh():
    try:
        import sshsocks
        return sshsocks.available()
    except Exception:  # noqa
        return False


def engine_info():
    xray = find_bin("xray", "FDLP_XRAY")
    version = ""
    if xray:
        try:
            out = subprocess.run([xray, "version"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"Xray\s+([\w.\-]+)", out)
            version = m.group(1) if m else out.strip().split("\n")[0][:40]
        except Exception:
            version = "?"
    return {
        "xray": bool(xray), "xray_version": version, "xray_path": xray or "",
        "ssh": bool(find_bin("ssh", "FDLP_SSH")) or _internal_ssh(),
        "dnstt": bool(find_bin("dnstt-client", "FDLP_DNSTT")),
    }


def is_ip(host):
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def resolve_host(host):
    """Résout un nom en IP côté Python (les binaires Go sous Termux n'ont pas de resolv.conf)."""
    if not host or is_ip(host):
        return host
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        for fam, _, _, _, sa in infos:
            if fam == socket.AF_INET:
                return sa[0]
        return infos[0][4][0]
    except Exception as e:
        LOG.add("Résolution DNS impossible pour %s : %s" % (host, e), "WARN")
        return host


def port_open(port, host="127.0.0.1", timeout=0.4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def tcp_ping(host, port, timeout=3.0):
    """Latence TCP en ms, ou None."""
    try:
        t = time.time()
        with socket.create_connection((resolve_host(host), int(port)), timeout=timeout):
            return int((time.time() - t) * 1000)
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Configuration Xray
# ----------------------------------------------------------------------------
def _split(v):
    return [x for x in re.split(r"[,\s]+", v or "") if x]


def build_stream(s, dom):
    net = (s.get("network") or "tcp").lower()
    net = {"h2": "http", "mkcp": "kcp", "splithttp": "xhttp", "raw": "tcp", "websocket": "ws",
           "http2": "http"}.get(net, net)
    sec = {"xtls": "tls", "": "none"}.get((s.get("security") or "none").lower(), (s.get("security") or "none").lower())
    st = {"network": net}
    sni = s.get("sni") or s.get("host") or ("" if is_ip(dom) else dom)
    if sec == "tls":
        t = {}
        if sni:
            t["serverName"] = sni
        if s.get("allowInsecure"):
            t["allowInsecure"] = True
        if _split(s.get("alpn")):
            t["alpn"] = _split(s.get("alpn"))
        if s.get("fingerprint"):
            t["fingerprint"] = s["fingerprint"]
        st["security"] = "tls"
        st["tlsSettings"] = t
    elif sec == "reality":
        st["security"] = "reality"
        st["realitySettings"] = {
            "serverName": sni,
            "fingerprint": s.get("fingerprint") or "chrome",
            "publicKey": s.get("publicKey", ""),
            "shortId": s.get("shortId", ""),
            "spiderX": s.get("spiderX") or "",
        }
    host = s.get("host") or sni
    path = s.get("path") or ""
    if net == "ws":
        w = {"path": path or "/"}
        if host:
            w["headers"] = {"Host": host}
        st["wsSettings"] = w
    elif net == "grpc":
        g = {"serviceName": s.get("serviceName") or path}
        if (s.get("mode") or "").lower() == "multi":
            g["multiMode"] = True
        st["grpcSettings"] = g
    elif net == "http":
        h = {"path": path or "/"}
        if host:
            h["host"] = _split(host)
        st["httpSettings"] = h
    elif net == "httpupgrade":
        st["httpupgradeSettings"] = {"path": path or "/", "host": host}
    elif net == "xhttp":
        x = {"path": path or "/", "host": host}
        if s.get("mode") in ("auto", "packet-up", "stream-up", "stream-one"):
            x["mode"] = s["mode"]
        if s.get("extra"):
            try:
                x["extra"] = json.loads(s["extra"]) if isinstance(s["extra"], str) else s["extra"]
            except ValueError:
                pass
        st["xhttpSettings"] = x
    elif net == "kcp":
        k = {"header": {"type": s.get("headerType") or "none"}}
        if path:
            k["seed"] = path
        k.setdefault("mtu", 1350)
        k.setdefault("tti", 20)
        k.setdefault("uplinkCapacity", 12)
        k.setdefault("downlinkCapacity", 100)
        st["kcpSettings"] = k
    elif net == "tcp" and s.get("headerType") == "http":
        st["tcpSettings"] = {"header": {"type": "http", "request": {
            "path": [path or "/"], "headers": {"Host": _split(host) or [""]}}}}
    return st


def uses_relay(s):
    return bool((s.get("proxy") or "").strip() or (s.get("payload") or "").strip())


def build_outbound(s, relay_port=None):
    p = s["protocol"]
    dom = s["address"]
    if relay_port:
        addr, port = "127.0.0.1", int(relay_port)
    else:
        addr, port = resolve_host(dom), int(s["port"])
    if p == "vmess":
        settings = {"vnext": [{"address": addr, "port": port, "users": [{
            "id": s["uuid"], "alterId": int(s.get("alterId") or 0),
            "security": s.get("encryption") or "auto"}]}]}
    elif p == "vless":
        user = {"id": s["uuid"], "encryption": s.get("encryption") or "none"}
        sec_ = (s.get("security") or "none").lower()
        net_ = (s.get("network") or "tcp").lower()
        # Le flow « vision » n'existe qu'avec TLS/Reality en TCP : sinon Xray refuse de démarrer.
        if s.get("flow") and sec_ in ("tls", "reality", "xtls") and net_ in ("tcp", "raw"):
            user["flow"] = s["flow"]
        settings = {"vnext": [{"address": addr, "port": port, "users": [user]}]}
    elif p == "trojan":
        settings = {"servers": [{"address": addr, "port": port, "password": s["password"]}]}
    elif p == "ss":
        settings = {"servers": [{"address": addr, "port": port, "method": s["method"],
                                 "password": s.get("password", "")}]}
    else:
        raise EngineError("Protocole non pris en charge : %s" % p)
    ob = {"tag": "proxy", "protocol": "shadowsocks" if p == "ss" else p, "settings": settings}
    if p != "ss" or (s.get("network") or "tcp") not in ("tcp", "raw") or (s.get("security") or "none") != "none":
        ob["streamSettings"] = build_stream(s, dom)
        ob["streamSettings"]["sockopt"] = {"tcpNoDelay": True, "tcpKeepAliveIdle": 30, "tcpKeepAliveInterval": 15}
    return ob


def build_config(outbound, st, tcp_dns=False):
    rules = [{"type": "field", "inboundTag": ["api"], "outboundTag": "api"}]
    if st.get("bypass_lan", True):
        rules.append({"type": "field", "ip": PRIVATE_CIDRS, "outboundTag": "direct"})
    dns_servers = _split(st.get("dns")) or ["1.1.1.1"]
    outbounds = [outbound,
                 {"tag": "direct", "protocol": "freedom", "settings": {}},
                 {"tag": "block", "protocol": "blackhole", "settings": {}}]
    if tcp_dns:   # SSH ne transporte que du TCP : on résout les noms en DNS-sur-TCP
        dns_servers = ["tcp://" + s for s in dns_servers if not s.startswith(("tcp://", "https"))] or ["tcp://1.1.1.1"]
        outbounds.append({"tag": "dns-out", "protocol": "dns", "settings": {}})
        rules.insert(1, {"type": "field", "inboundTag": ["socks-in"], "network": "udp", "port": 53,
                         "outboundTag": "dns-out"})
    return {
        "log": {"loglevel": "warning"},
        "stats": {},
        "api": {"tag": "api", "services": ["StatsService"]},
        "policy": {
            "levels": {"0": {"handshake": 8, "connIdle": 300, "uplinkOnly": 2, "downlinkOnly": 5,
                             "bufferSize": 512}},
            "system": {"statsOutboundUplink": True, "statsOutboundDownlink": True},
        },
        "dns": {"servers": dns_servers, "queryStrategy": "UseIPv4", "disableFallback": False},
        "inbounds": [
            {"tag": "socks-in", "listen": "127.0.0.1", "port": st["socks_port"], "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True, "ip": "127.0.0.1"},
             "sniffing": {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": False}},
            {"tag": "http-in", "listen": "127.0.0.1", "port": st["http_port"], "protocol": "http",
             "settings": {}},
            {"tag": "api", "listen": "127.0.0.1", "port": st["api_port"], "protocol": "dokodemo-door",
             "settings": {"address": "127.0.0.1"}},
        ],
        "outbounds": outbounds,
        "routing": {"domainStrategy": "AsIs", "rules": rules},
    }


def query_stats(xray, api_port):
    """Retourne (octets envoyés, octets reçus) du trafic sortant 'proxy'."""
    try:
        out = subprocess.run([xray, "api", "statsquery", "--server=127.0.0.1:%d" % api_port],
                             capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return None
    up = down = 0
    try:
        for it in json.loads(out).get("stat", []):
            name, val = it.get("name", ""), int(it.get("value", 0) or 0)
            if name.startswith("outbound>>>proxy>>>traffic>>>"):
                if name.endswith("uplink"):
                    up = val
                elif name.endswith("downlink"):
                    down = val
    except ValueError:  # ancien format texte
        for name, val in re.findall(r'name:\s*"([^"]+)"\s*value:\s*(\d+)', out):
            if name.startswith("outbound>>>proxy>>>traffic>>>"):
                if name.endswith("uplink"):
                    up = int(val)
                elif name.endswith("downlink"):
                    down = int(val)
    return up, down


# ----------------------------------------------------------------------------
# Moteur
# ----------------------------------------------------------------------------
class Engine:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.gen = 0
        self.state = "idle"      # idle | connecting | connected | error
        self.message = ""
        self.server_id = None
        self.since = None
        self.up = self.down = 0
        self.up_speed = self.down_speed = 0
        self.procs = []          # [(nom, Popen)]
        self.askpass = None

    # -- API publique ----------------------------------------------------
    def snapshot(self):
        with self.lock:
            st = self.store.settings()
            return {
                "state": self.state, "message": self.message, "server_id": self.server_id,
                "since": self.since, "up": self.up, "down": self.down,
                "up_speed": self.up_speed, "down_speed": self.down_speed,
                "socks_port": st["socks_port"], "http_port": st["http_port"],
            }

    def connect(self, sid):
        srv = self.store.get(sid)
        if not srv:
            raise EngineError("Serveur introuvable.")
        if is_expired(srv):
            raise EngineError("Ce serveur a expiré le %s." % srv.get("expires"))
        self.disconnect(quiet=True)
        with self.lock:
            self.gen += 1
            gen = self.gen
            self.state, self.message, self.server_id = "connecting", "", sid
            self.since = None
            self.up = self.down = self.up_speed = self.down_speed = 0
        self.store.set_active(sid)
        threading.Thread(target=self._connect_thread, args=(srv, gen), daemon=True).start()

    def disconnect(self, quiet=False):
        with self.lock:
            was = self.state
            self.gen += 1
            procs, self.procs = self.procs, []
            self.state, self.message, self.since = "idle", "", None
            self.up_speed = self.down_speed = 0
        self._kill(procs)
        self._drop_askpass()
        if not quiet:
            _hook("down")
        if was in ("connected", "connecting") and not quiet:
            LOG.add("Déconnecté.")

    # -- internes --------------------------------------------------------
    def _alive(self, gen):
        return self.gen == gen

    def _fail(self, gen, msg):
        LOG.add(msg, "ERROR")
        with self.lock:
            if self.gen != gen:
                return
            procs, self.procs = self.procs, []
            self.state, self.message, self.since = "error", msg, None
        self._kill(procs)
        self._drop_askpass()
        _hook("down")

    def _connect_thread(self, srv, gen):
        """Boucle principale : connexion, surveillance, reconnexion automatique si le lien tombe."""
        tries, ever = 0, False
        while self._alive(gen):
            try:
                outcome = self._session(srv, gen)
            except EngineError as e:
                if not ever:                     # première connexion : erreur franche (mauvais identifiants…)
                    self._fail(gen, str(e))
                    return
                LOG.add("Reconnexion impossible : %s" % e, "WARN")
                outcome = "lost"
            except Exception as e:  # noqa
                self._fail(gen, "Erreur inattendue : %s" % e)
                return
            if outcome == "stable":
                ever, tries = True, 0
            elif outcome == "lost-first":
                ever = True
            if outcome == "cancelled" or not self._alive(gen):
                return
            tries += 1
            if tries > 5:
                self._fail(gen, "Connexion perdue : 5 tentatives de reconnexion ont échoué.")
                return
            LOG.add("Connexion perdue. Reconnexion automatique (%d/5)…" % tries, "WARN")
            with self.lock:
                if self.gen != gen:
                    return
                procs, self.procs = self.procs, []
                self.state, self.since = "connecting", None
                self.up_speed = self.down_speed = 0
            self._kill(procs)
            self._drop_askpass()
            for _ in range(min(2 * tries, 8) * 5):      # attente interruptible
                if not self._alive(gen):
                    return
                time.sleep(0.2)

    def _session(self, srv, gen):
        """Une session complète. Retourne 'cancelled', 'lost-first' ou 'stable' (connexion perdue)."""
        LOG.add("Connexion à « %s » (%s)…" % (srv["name"], srv["protocol"].upper()))
        xray = find_bin("xray", "FDLP_XRAY")
        if not xray:
            raise EngineError("Moteur Xray introuvable. Lance dans Termux : fadelpsaume install-engine")
        st = self.store.settings()
        tcp_dns = False
        if srv["protocol"] == "sshdns":
            outbound = self._start_sshdns(srv, st, gen)
            tcp_dns = True
        else:
            outbound = build_outbound(srv, self._start_relay(srv, gen))
        if not self._alive(gen):
            return "cancelled"
        cfg_path = os.path.join(HOME, "run", "config.json")
        with open(cfg_path, "w") as f:
            json.dump(build_config(outbound, st, tcp_dns), f)
        os.chmod(cfg_path, 0o600)
        proc = self._spawn("xray", [xray, "run", "-c", cfg_path], gen)
        deadline = time.time() + 10
        while time.time() < deadline and self._alive(gen):
            if proc.poll() is not None:
                raise EngineError("Xray s'est arrêté (code %s). Voir le journal." % proc.returncode)
            if port_open(st["socks_port"], timeout=0.15):
                break
            time.sleep(0.05)
        else:
            if not self._alive(gen):
                return "cancelled"
            raise EngineError("Xray n'a pas démarré à temps.")
        if not self._alive(gen):
            return "cancelled"
        t0 = time.time()
        with self.lock:
            if self.gen != gen:
                return "cancelled"
            self.state, self.since, self.message = "connected", t0, ""
            self.up = self.down = 0
        LOG.add("Connecté. Proxy SOCKS5 127.0.0.1:%d — HTTP 127.0.0.1:%d" % (st["socks_port"], st["http_port"]))
        _hook("up", st)
        lost = self._monitor(xray, st, gen)
        if not lost:
            return "cancelled"
        return "stable" if time.time() - t0 > 60 else "lost-first"

    def _monitor(self, xray, st, gen):
        """Surveille la connexion. Retourne True si elle est perdue, False si annulée."""
        last_t, last_up, last_down = time.time(), 0, 0
        while self._alive(gen):
            for _ in range(10):                       # 2 s, interruptible
                if not self._alive(gen):
                    return False
                time.sleep(0.2)
            with self.lock:
                dead = [n for n, p in self.procs if p.poll() is not None]
            if dead:
                LOG.add("Le processus « %s » s'est arrêté." % dead[0], "WARN")
                return True
            if not port_open(st["socks_port"], timeout=0.5):
                LOG.add("Le proxy local ne répond plus.", "WARN")
                return True
            res = query_stats(xray, st["api_port"])
            if res is None:
                continue
            now = time.time()
            dt = max(now - last_t, 0.001)
            with self.lock:
                if self.gen != gen:
                    return False
                self.up, self.down = res
                self.up_speed = max(0, int((res[0] - last_up) / dt))
                self.down_speed = max(0, int((res[1] - last_down) / dt))
            last_t, last_up, last_down = now, res[0], res[1]
        return False

    # -- SSH SlowDNS -----------------------------------------------------
    def _start_relay(self, srv, gen):
        """Lance le relais proxy/payload si le serveur en a besoin. Retourne son port local (ou None)."""
        if not uses_relay(srv):
            return None
        rl = relaymod.Relay(srv["address"], srv["port"], srv.get("proxy", ""), srv.get("proxySni", ""),
                            srv.get("payload", ""), srv.get("allowInsecure"), log=LOG.add)
        port = rl.start()
        with self.lock:
            if self.gen != gen:
                rl.stop()
                raise EngineError("Connexion annulée.")
            self.procs.append(("relay", ThreadProc(rl)))
        LOG.add("Relais proxy/payload actif (%s)." % (srv.get("proxy") or "connexion directe"))
        return port

    def _start_sshdns(self, srv, st, gen):
        ssh = find_bin("ssh", "FDLP_SSH")
        internal = False
        if not ssh:
            try:
                import sshsocks  # noqa: F401
                internal = sshsocks.available()
            except Exception:  # noqa
                internal = False
            if not internal:
                raise EngineError("Client SSH introuvable. Dans Termux : pkg install openssh")
        ns = (srv.get("ns_domain") or "").strip()
        host = (srv.get("address") or "").strip()
        port = int(srv.get("port") or 22)
        if ns:
            dnstt = find_bin("dnstt-client", "FDLP_DNSTT")
            if not dnstt:
                raise EngineError("Module SlowDNS (dnstt-client) absent. Lance : fadelpsaume install-slowdns")
            resolver = (srv.get("resolver") or "").strip()
            kind = srv.get("dns_type") or "udp"
            args = [dnstt]
            if kind == "doh":
                args += ["-doh", resolver]
            elif kind == "dot":
                h, _, pt = resolver.partition(":")
                args += ["-dot", "%s:%s" % (resolve_host(h), pt or "853")]
            else:
                h, _, pt = resolver.partition(":")
                args += ["-udp", "%s:%s" % (resolve_host(h), pt or "53")]
            args += ["-pubkey", srv["pubkey"], ns, "127.0.0.1:%d" % st["dnstt_port"]]
            LOG.add("Démarrage du tunnel SlowDNS via le resolver %s…" % resolver)
            p = self._spawn("dnstt", args, gen)
            for _ in range(50):
                if p.poll() is not None:
                    raise EngineError("dnstt-client s'est arrêté. Vérifie le Name Server, la clé publique et le resolver.")
                if port_open(st["dnstt_port"]):
                    break
                time.sleep(0.2)
            else:
                raise EngineError("Le tunnel SlowDNS n'a pas démarré.")
            target_host, target_port = "127.0.0.1", st["dnstt_port"]
        else:
            target_host, target_port = host, port

        if internal:
            import sshsocks
            LOG.add("Ouverture de la session SSH (client intégré) vers %s:%s…" % (target_host, target_port))
            job = sshsocks.SshSocks(target_host, target_port, srv["user"], srv.get("password") or "",
                                    st["ssh_port"], lambda m: LOG.add("[ssh] " + m))
            with self.lock:
                if self.gen != gen:
                    raise EngineError("Connexion annulée.")
                self.procs.append(("ssh", ThreadProc(job)))
            try:
                job.start()
            except Exception as e:  # noqa
                raise EngineError("Connexion SSH impossible : %s" % e)
            return {"tag": "proxy", "protocol": "socks",
                    "settings": {"servers": [{"address": "127.0.0.1", "port": st["ssh_port"]}]}}

        env = dict(os.environ)
        pw = srv.get("password") or ""
        args = [ssh, "-N", "-D", "127.0.0.1:%d" % st["ssh_port"], "-p", str(target_port),
                "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
                "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=40", "-o", "LogLevel=ERROR",
                "-o", "Compression=no", "-o", "TCPKeepAlive=yes", "-o", "IPQoS=none",
                "-c", "chacha20-poly1305@openssh.com,aes128-gcm@openssh.com,aes128-ctr"]
        if pw:
            self._write_askpass()
            env.update(SSH_ASKPASS=self.askpass, SSH_ASKPASS_REQUIRE="force", DISPLAY=env.get("DISPLAY", ":0"),
                       FDLP_SSH_PASS=pw)
            args += ["-o", "PreferredAuthentications=password,keyboard-interactive",
                     "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1"]
        args.append("%s@%s" % (srv["user"], target_host))
        LOG.add("Ouverture de la session SSH vers %s:%s…" % (target_host, target_port))
        p = self._spawn("ssh", args, gen, env=env)
        deadline = time.time() + 60
        while time.time() < deadline and self._alive(gen):
            if p.poll() is not None:
                raise EngineError("Connexion SSH refusée ou interrompue. Vérifie l'utilisateur et le mot de passe.")
            if port_open(st["ssh_port"]):
                break
            time.sleep(0.3)
        else:
            if self._alive(gen):
                raise EngineError("La session SSH n'a pas abouti (délai dépassé).")
        return {"tag": "proxy", "protocol": "socks",
                "settings": {"servers": [{"address": "127.0.0.1", "port": st["ssh_port"]}]}}

    def _write_askpass(self):
        path = os.path.join(HOME, "run", "askpass.sh")
        with open(path, "w") as f:
            f.write("#!%s\nprintf '%%s\\n' \"$FDLP_SSH_PASS\"\n" % (shutil.which("sh") or "/bin/sh"))
        os.chmod(path, stat.S_IRWXU)
        self.askpass = path

    def _drop_askpass(self):
        if self.askpass:
            try:
                os.remove(self.askpass)
            except OSError:
                pass
            self.askpass = None

    # -- processus -------------------------------------------------------
    def _spawn(self, name, args, gen, env=None):
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1, start_new_session=True, env=env)
        with self.lock:
            if self.gen != gen:
                self._kill([(name, p)])
                raise EngineError("Connexion annulée.")
            self.procs.append((name, p))

        def pump():
            for line in p.stdout:
                line = line.rstrip()
                if line:
                    LOG.add("[%s] %s" % (name, line))

        threading.Thread(target=pump, daemon=True).start()
        return p

    @staticmethod
    def _kill(procs):
        for _, p in procs:
            if isinstance(p, ThreadProc):
                try:
                    p.stop()
                except Exception:  # noqa
                    pass
                continue
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        for _, p in procs:
            if isinstance(p, ThreadProc):
                continue
            try:
                p.wait(timeout=2)
            except Exception:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except Exception:
                    pass
