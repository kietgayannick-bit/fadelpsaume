"""Fadelpsaume - stockage des serveurs, réglages et journal."""
import collections
import copy
import datetime
import json
import os
import threading
import time

VERSION = "2.0.0"
HOME = os.environ.get("FDLP_HOME") or os.path.join(os.path.expanduser("~"), ".fadelpsaume")
for _d in ("", "bin", "run", "logs"):
    os.makedirs(os.path.join(HOME, _d), exist_ok=True)
DATA_FILE = os.path.join(HOME, "data.json")
LOG_FILE = os.path.join(HOME, "logs", "fadelpsaume.log")

ANDROID = bool(os.environ.get("FDLP_ANDROID"))

DEFAULT_SETTINGS = {
    "socks_port": 10808,   # proxy SOCKS5 local
    "http_port": 10809,    # proxy HTTP local
    "api_port": 10085,     # API de statistiques du moteur (interne)
    "ssh_port": 10807,     # SOCKS interne ouvert par ssh -D (mode SSH SlowDNS)
    "dnstt_port": 5300,    # port local du tunnel dnstt
    "dns": "1.1.1.1,8.8.8.8",
    "bypass_lan": True,
}
if ANDROID:  # ports différents de ceux de Termux / v2rayNG pour éviter les conflits
    DEFAULT_SETTINGS.update(socks_port=20808, http_port=20809, api_port=20085, ssh_port=20807, dnstt_port=5301)


class Logger:
    def __init__(self):
        self.lines = collections.deque(maxlen=3000)
        self.n = 0
        self.lock = threading.Lock()

    def add(self, msg, level="INFO"):
        line = "%s [%s] %s" % (time.strftime("%H:%M:%S"), level, msg)
        with self.lock:
            self.n += 1
            self.lines.append((self.n, line))
            try:
                if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 1_000_000:
                    os.replace(LOG_FILE, LOG_FILE + ".1")
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass

    def since(self, n):
        with self.lock:
            return [l for i, l in self.lines if i > n], self.n

    def clear(self):
        with self.lock:
            self.lines.clear()
            try:
                open(LOG_FILE, "w").close()
            except OSError:
                pass


LOG = Logger()


def is_expired(s):
    e = s.get("expires")
    if not e:
        return False
    try:
        return datetime.date.today() > datetime.date.fromisoformat(e)
    except ValueError:
        return False


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.data = self._load()

    def _load(self):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        d.setdefault("servers", [])
        d.setdefault("active", None)
        st = dict(DEFAULT_SETTINGS)
        st.update(d.get("settings") or {})
        d["settings"] = st
        return d

    def _save(self):
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, DATA_FILE)

    # -- lecture ---------------------------------------------------------
    def servers(self):
        with self.lock:
            return copy.deepcopy(self.data["servers"])

    def get(self, sid):
        with self.lock:
            for s in self.data["servers"]:
                if s["id"] == sid:
                    return copy.deepcopy(s)
        return None

    def settings(self):
        with self.lock:
            return dict(self.data["settings"])

    @property
    def active(self):
        with self.lock:
            return self.data.get("active")

    # -- écriture --------------------------------------------------------
    def add(self, s):
        with self.lock:
            self.data["servers"].append(s)
            if not self.data.get("active"):
                self.data["active"] = s["id"]
            self._save()

    def update(self, sid, s):
        with self.lock:
            for i, old in enumerate(self.data["servers"]):
                if old["id"] == sid:
                    s["id"] = sid
                    s["created"] = old.get("created", s.get("created"))
                    self.data["servers"][i] = s
                    self._save()
                    return True
        return False

    def delete(self, sid):
        with self.lock:
            n = len(self.data["servers"])
            self.data["servers"] = [s for s in self.data["servers"] if s["id"] != sid]
            if self.data.get("active") == sid:
                self.data["active"] = self.data["servers"][0]["id"] if self.data["servers"] else None
            self._save()
            return len(self.data["servers"]) != n

    def set_active(self, sid):
        with self.lock:
            self.data["active"] = sid
            self._save()
