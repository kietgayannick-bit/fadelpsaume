#!/usr/bin/env python3
"""Fadelpsaume - serveur local (interface + API). Écoute uniquement sur 127.0.0.1."""
import argparse
import datetime
import json
import mimetypes
import os
import re
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import links
from engine import Engine, EngineError, engine_info, tcp_ping
from store import HOME, LOG, VERSION, Store, is_expired

WEB = os.environ.get("FDLP_WEB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
ARCHIVE = os.path.join(HOME, "Fadelpsaume.tar.gz")
STORE = Store()
ENGINE = Engine(STORE)
ENGINE_INFO = engine_info()
MAGIC = "FDLP1:"
SAFE_FIELDS = ("id", "name", "protocol", "locked", "expires", "note")
SECRET_STR = "••••••"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def public(s):
    """Version d'un serveur renvoyée à l'interface (les serveurs verrouillés sont masqués)."""
    if s.get("locked"):
        d = {k: s.get(k) for k in SAFE_FIELDS}
        d.update(address=SECRET_STR, port=0)
    else:
        d = dict(s)
    d["expired"] = is_expired(s)
    return d


def server_key(s):
    return json.dumps([s.get("protocol"), s.get("address"), s.get("port"), s.get("uuid"),
                       s.get("password"), s.get("user"), s.get("ns_domain")])


def safe_filename(name):
    name = re.sub(r"[^\w\-. ]", "_", (name or "").strip()) or "Fadelpsaume"
    name = re.sub(r"\.(rmv|fdlp)$", "", name, flags=re.I)
    return name + ".rmv"


def decode_container(text):
    t = (text or "").strip().lstrip("﻿")
    try:
        if t.startswith(MAGIC):
            obj = json.loads(links.b64decode(t[len(MAGIC):]))
        elif t.startswith("{"):
            obj = json.loads(t)
        else:
            return None
    except Exception:
        raise ApiError("Fichier illisible ou corrompu.")
    if not isinstance(obj, dict) or obj.get("app") != "Fadelpsaume":
        raise ApiError("Ce fichier n'est pas une configuration Fadelpsaume.")
    return obj


# ----------------------------------------------------------------------------
# Actions
# ----------------------------------------------------------------------------
_engine_cache = {"t": 0, "v": ENGINE_INFO}


def current_engine_info():
    if time.time() - _engine_cache["t"] > 10:
        _engine_cache.update(t=time.time(), v=engine_info())
    return _engine_cache["v"]


def api_state():
    st = STORE.settings()
    return {
        "app": VERSION, "now": time.time(),
        "servers": [public(s) for s in STORE.servers()],
        "active": STORE.active,
        "status": ENGINE.snapshot(),
        "engine": current_engine_info(),
        "ports": {"socks": st["socks_port"], "http": st["http_port"]},
        "archive": os.path.isfile(ARCHIVE),
        "android": bool(os.environ.get("FDLP_ANDROID")),
    }


def api_connect(body):
    try:
        ENGINE.connect(body.get("id"))
    except EngineError as e:
        raise ApiError(str(e))
    return {"ok": True}


def prepare_server(body, existing=None):
    raw = dict(body.get("server") or {})
    if existing:
        merged = dict(existing)
        merged.update(raw)
        raw = merged
        raw["id"] = existing["id"]
        raw["locked"] = existing.get("locked", False)
        raw["expires"] = existing.get("expires", "")
    s = links.clean(raw)
    err = links.validate(s)
    if err:
        raise ApiError(err)
    return s


def api_add(body):
    s = prepare_server(body)
    s["id"] = links.new_id()
    s["locked"] = False
    STORE.add(s)
    LOG.add("Serveur ajouté : %s (%s)" % (s["name"], s["protocol"]))
    return public(s)


def api_update(sid, body):
    old = STORE.get(sid)
    if not old:
        raise ApiError("Serveur introuvable.", 404)
    if old.get("locked"):
        raise ApiError("Ce serveur est verrouillé : modification impossible.", 403)
    s = prepare_server(body, old)
    STORE.update(sid, s)
    LOG.add("Serveur modifié : %s" % s["name"])
    return public(s)


def api_delete(sid):
    snap = ENGINE.snapshot()
    if snap["server_id"] == sid and snap["state"] != "idle":
        ENGINE.disconnect()
    if not STORE.delete(sid):
        raise ApiError("Serveur introuvable.", 404)
    LOG.add("Serveur supprimé.")
    return {"ok": True}


def api_import(body):
    text = body.get("text") or ""
    box = decode_container(text)
    note = ""
    if box:
        exp = box.get("expires") or ""
        if exp and is_expired({"expires": exp}):
            raise ApiError("Ce fichier a expiré le %s." % exp)
        servers, errors = [], []
        for item in box.get("servers") or []:
            try:
                s = links.clean(item)
                err = links.validate(s)
                if err:
                    raise ValueError(err)
                s["id"] = links.new_id()
                s["expires"] = exp or s.get("expires", "")
                s["locked"] = bool(box.get("locked")) or bool(item.get("locked"))
                servers.append(s)
            except ValueError as e:
                errors.append(str(e))
        note = box.get("note") or ""
    else:
        servers, errors = links.parse_any(text)
    known = {server_key(s) for s in STORE.servers()}
    added = dupes = 0
    for s in servers:
        k = server_key(s)
        if k in known:
            dupes += 1
            continue
        known.add(k)
        STORE.add(s)
        added += 1
    if added:
        LOG.add("%d serveur(s) importé(s)." % added)
    if not added and not dupes and errors:
        raise ApiError(errors[0])
    return {"added": added, "duplicates": dupes, "errors": errors, "note": note}


def api_export(body):
    ids = body.get("ids") or []
    servers = []
    for sid in ids:
        s = STORE.get(sid)
        if not s:
            continue
        if s.get("locked"):
            raise ApiError("« %s » est verrouillé : export impossible." % s.get("name"), 403)
        servers.append(s)
    if not servers:
        raise ApiError("Sélectionne au moins un serveur.")
    if body.get("mode") == "clipboard":
        return {"text": "\n".join(links.build_link(s) for s in servers), "count": len(servers)}
    exp = (body.get("expires") or "").strip()
    if exp:
        try:
            datetime.date.fromisoformat(exp)
        except ValueError:
            raise ApiError("Date d'expiration invalide.")
    box = {
        "app": "Fadelpsaume", "format": 1,
        "name": (body.get("filename") or "Fadelpsaume").strip(),
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "expires": exp, "note": (body.get("note") or "").strip()[:500],
        "locked": bool(body.get("locked")),
        "servers": [{k: v for k, v in s.items() if k not in ("id", "locked", "expires")} for s in servers],
    }
    content = MAGIC + links.b64encode(json.dumps(box, ensure_ascii=False))
    LOG.add("Export de %d serveur(s) vers un fichier .rmv." % len(servers))
    return {"filename": safe_filename(body.get("filename")), "content": content, "count": len(servers)}


def api_ping(body):
    ids = body.get("ids") or []
    srvs = [s for s in (STORE.get(i) for i in ids) if s]

    def one(s):
        if s.get("address"):
            return s["id"], tcp_ping(s["address"], s.get("port") or 22)
        return s["id"], None

    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(one, srvs))


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "Fadelpsaume/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # -- utilitaires -----------------------------------------------------
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _host_ok(self):
        h = self.headers.get("Host") or ""
        if h.startswith("["):
            host = h.split("]")[0] + "]"
        else:
            host = h.rsplit(":", 1)[0] if ":" in h else h
        return host in ALLOWED_HOSTS

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 5_000_000:
            raise ApiError("Contenu trop volumineux.", 413)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ApiError("Requête invalide.")

    def _route(self, method):
        u = urlparse(self.path)
        if not self._host_ok():
            return self._send(403, {"error": "Hôte non autorisé."})
        if u.path.startswith("/api/"):
            if self.headers.get("X-FDLP") != "1":
                return self._send(403, {"error": "Requête refusée."})
            try:
                return self._send(200, self._api(method, u))
            except ApiError as e:
                return self._send(e.code, {"error": str(e)})
            except Exception as e:  # noqa
                LOG.add("Erreur API : %s" % e, "ERROR")
                return self._send(500, {"error": "Erreur interne."})
        if method != "GET":
            return self._send(405, {"error": "Méthode non autorisée."})
        return self._static(u.path)

    def _api(self, method, u):
        path = u.path[5:].strip("/")
        parts = path.split("/")
        if method == "GET":
            if path == "state":
                return api_state()
            if path == "logs":
                since = int((parse_qs(u.query).get("since") or ["0"])[0])
                lines, n = LOG.since(since)
                return {"lines": lines, "n": n}
            if path == "app-archive":
                if not os.path.isfile(ARCHIVE):
                    raise ApiError("Archive introuvable (relance install.sh).", 404)
                with open(ARCHIVE, "rb") as f:
                    data = f.read()
                self._send(200, data, "application/gzip", {"Content-Disposition": 'attachment; filename="Fadelpsaume.tar.gz"'})
                raise _Handled()
        elif method == "POST":
            body = self._body()
            if path == "connect":
                return api_connect(body)
            if path == "disconnect":
                ENGINE.disconnect()
                return {"ok": True}
            if path == "active":
                if not STORE.get(body.get("id")):
                    raise ApiError("Serveur introuvable.", 404)
                STORE.set_active(body["id"])
                return {"ok": True}
            if path == "servers":
                return api_add(body)
            if path == "import":
                return api_import(body)
            if path == "export":
                return api_export(body)
            if path == "ping":
                return api_ping(body)
            if path == "logs/clear":
                LOG.clear()
                return {"ok": True}
        elif method == "PUT" and len(parts) == 2 and parts[0] == "servers":
            return api_update(parts[1], self._body())
        elif method == "DELETE" and len(parts) == 2 and parts[0] == "servers":
            return api_delete(parts[1])
        raise ApiError("Introuvable.", 404)

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not full.startswith(WEB + os.sep) or not os.path.isfile(full):
            return self._send(404, b"Not found", "text/plain")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ""))

    def do_GET(self):
        self._safe("GET")

    def do_HEAD(self):
        self._safe("GET")

    def do_POST(self):
        self._safe("POST")

    def do_PUT(self):
        self._safe("PUT")

    def do_DELETE(self):
        self._safe("DELETE")

    def _safe(self, method):
        try:
            self._route(method)
        except _Handled:
            pass
        except (BrokenPipeError, ConnectionResetError):
            pass


class _Handled(Exception):
    pass


def serve(host="127.0.0.1", port=8080, install_signals=True):
    """Démarre le serveur (bloquant). Utilisé par la ligne de commande et par l'application Android."""
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    pid_file = os.path.join(HOME, "run", "server.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    def shutdown(*_):
        LOG.add("Arrêt de Fadelpsaume.")
        ENGINE.disconnect(quiet=True)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    if install_signals and threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
    LOG.add("Fadelpsaume %s démarré sur http://%s:%d" % (VERSION, host, port))
    if not ENGINE_INFO["xray"]:
        LOG.add("Moteur Xray introuvable.", "WARN")
    print("Fadelpsaume prêt : http://%s:%d  (Ctrl+C pour arrêter)" % (host, port), flush=True)
    try:
        httpd.serve_forever()
    finally:
        ENGINE.disconnect(quiet=True)
        try:
            os.remove(pid_file)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="Fadelpsaume VPN - serveur local")
    ap.add_argument("--port", type=int, default=int(os.environ.get("FDLP_PORT", 8080)))
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
