"""Fadelpsaume - point d'entrée Android (appelé depuis Java via Chaquopy)."""
import os
import sys


def start(files_dir, native_dir, port):
    """Prépare l'environnement puis lance le serveur local (bloquant, à appeler dans un thread)."""
    os.environ["FDLP_ANDROID"] = "1"
    os.environ["FDLP_HOME"] = os.path.join(files_dir, "fdlp")
    os.environ["FDLP_WEB"] = os.path.join(files_dir, "fdlp", "web")
    os.environ["FDLP_XRAY"] = os.path.join(native_dir, "libxray.so")
    os.environ["FDLP_DNSTT"] = os.path.join(native_dir, "libdnstt.so")
    os.environ["HOME"] = files_dir

    import engine
    import server

    def _svc():
        from java import jclass
        return jclass("com.fadelpsaume.vpn.FadelVpnService")

    def _ctx():
        from java import jclass
        return jclass("com.chaquo.python.Python").getPlatform().getApplication()

    def up(settings):
        import threading
        import time
        from store import LOG
        svc = _svc()
        svc.startTunnel(_ctx(), int(settings["socks_port"]), str(settings.get("dns") or "1.1.1.1"))

        def report():
            time.sleep(2.5)
            try:
                LOG.add("Tunnel VPN Android : %s" % svc.status())
            except Exception as e:  # noqa
                LOG.add("Tunnel VPN Android : état illisible (%s)" % e, "WARN")
        threading.Thread(target=report, daemon=True).start()

    def down():
        _svc().stopTunnel(_ctx())

    engine.HOOKS["up"] = up
    engine.HOOKS["down"] = down
    server.serve("127.0.0.1", int(port), install_signals=False)
