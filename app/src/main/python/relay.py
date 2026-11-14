"""Fadelpsaume - relais « proxy + payload » (style HTTP Injector).

Xray se connecte à ce relais local au lieu du vrai serveur. Pour chaque connexion, le relais :
  1. se connecte au proxy (hôte:port) — ou directement au serveur si aucun proxy n'est donné ;
  2. enveloppe la connexion en TLS avec le SNI du proxy si demandé ;
  3. envoie le payload (avec [host_port], [crlf], [method]… remplacés) ;
  4. lit et jette la réponse HTTP (200 / 101…), puis relaie les octets dans les deux sens.
"""
import re
import select
import socket
import ssl
import threading
import time

DEFAULT_PAYLOAD = "[method] [host_port] [protocol][crlf]Host: [host][crlf][crlf]"
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"


def expand(payload, host, port, split_marker="\x00SPLIT\x00"):
    """Remplace les variables du payload. [split] devient un marqueur interne."""
    hp = "%s:%s" % (host, port)
    out = payload or DEFAULT_PAYLOAD
    # [netData] / [raw] d'abord (ils contiennent d'autres variables)
    out = re.sub(r"\[(netData|raw)\]", "[method] [host_port] [protocol]", out, flags=re.I)
    table = {
        "method": "CONNECT", "host_port": hp, "host": host, "port": str(port), "protocol": "HTTP/1.1",
        "crlf": "\r\n", "cr": "\r", "lf": "\n", "lfcr": "\n\r", "ua": UA, "split": split_marker,
    }
    return re.sub(r"\[([A-Za-z_]+)\]", lambda m: table.get(m.group(1).lower(), m.group(0)), out)


def parse_hostport(v, default_port=80):
    v = (v or "").strip()
    if not v:
        return None
    if v.startswith("["):                       # IPv6 [::1]:8080
        h, _, rest = v[1:].partition("]")
        return h, int(rest.lstrip(":") or default_port)
    if v.count(":") == 1:
        h, p = v.split(":")
        return h, int(p or default_port)
    return v, default_port


class Relay:
    def __init__(self, target_host, target_port, proxy="", proxy_sni="", payload="",
                 insecure=False, log=None):
        self.target = (target_host, int(target_port))
        self.proxy = parse_hostport(proxy)
        self.proxy_sni = (proxy_sni or "").strip()
        self.payload = payload or ""
        self.insecure = bool(insecure)
        self.log = log or (lambda m, lv="INFO": None)
        self.port = 0
        self._stop = threading.Event()
        self._srv = None
        self._warned = False

    # -- vie ---------------------------------------------------------------
    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(128)
        s.settimeout(1.0)
        self._srv = s
        self.port = s.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()
        return self.port

    def alive(self):
        return not self._stop.is_set()

    def stop(self):
        self._stop.set()
        try:
            self._srv.close()
        except Exception:  # noqa
            pass

    def _accept(self):
        while not self._stop.is_set():
            try:
                c, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(c,), daemon=True).start()

    # -- une connexion -----------------------------------------------------
    def _open_upstream(self):
        host, port = self.proxy or self.target
        up = socket.create_connection((host, port), timeout=15)
        up.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if self.proxy and self.proxy_sni:
            ctx = ssl.create_default_context()
            if self.insecure:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            up = ctx.wrap_socket(up, server_hostname=self.proxy_sni)
        return up

    @staticmethod
    def _read_head(up, timeout):
        """Lit l'en-tête HTTP de réponse (jusqu'à \\r\\n\\r\\n). Retourne (en-tête, reste) ou (None, b'')."""
        buf = b""
        end = time.time() + timeout
        up.settimeout(0.5)
        while b"\r\n\r\n" not in buf and time.time() < end and len(buf) < 65536:
            try:
                chunk = up.recv(8192)
            except socket.timeout:
                continue
            except ssl.SSLWantReadError:
                continue
            if not chunk:
                break
            buf += chunk
        if b"\r\n\r\n" in buf:
            head, rest = buf.split(b"\r\n\r\n", 1)
            return head, rest
        return None, buf

    def _handle(self, client):
        up = None
        try:
            up = self._open_upstream()
            # Avec un proxy, on envoie toujours un payload (CONNECT par défaut). Sans proxy, seulement si fourni.
            if self.proxy or self.payload.strip():
                data = expand(self.payload, self.target[0], self.target[1])
                parts = data.split("\x00SPLIT\x00")
                for i, part in enumerate(parts):
                    if part:
                        up.sendall(part.encode("latin-1", "replace"))
                    if i < len(parts) - 1:
                        time.sleep(0.15)
                is_connect = data.lstrip().upper().startswith("CONNECT")
                head, rest = self._read_head(up, 12 if is_connect else 2.0)
                if head is not None:
                    first = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
                    m = re.match(r"HTTP/\d\.\d\s+(\d{3})", first)
                    code = int(m.group(1)) if m else 0
                    if is_connect and not (200 <= code < 300):
                        if not self._warned:
                            self._warned = True
                            self.log("Le proxy a refusé la connexion : %s" % first[:80], "WARN")
                        return
                elif is_connect:
                    if not self._warned:
                        self._warned = True
                        self.log("Le proxy n'a pas répondu au payload.", "WARN")
                    return
                if rest:
                    client.sendall(rest)
            self._pump(client, up)
        except Exception as e:  # noqa
            if not self._warned:
                self._warned = True
                self.log("Relais : %s" % e, "WARN")
        finally:
            for o in (client, up):
                try:
                    if o:
                        o.close()
                except Exception:  # noqa
                    pass

    def _pump(self, a, b):
        a.settimeout(None)
        b.settimeout(None)
        while not self._stop.is_set():
            # les sockets TLS peuvent avoir des données déjà déchiffrées en attente
            pending = isinstance(b, ssl.SSLSocket) and b.pending()
            r, _, _ = select.select([a, b], [], [], 1.0)
            if a in r:
                d = a.recv(65536)
                if not d:
                    return
                b.sendall(d)
            if b in r or pending:
                d = b.recv(65536)
                if not d:
                    return
                a.sendall(d)
