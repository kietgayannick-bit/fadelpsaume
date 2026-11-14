"""Fadelpsaume - client SSH intégré avec proxy SOCKS5 local (équivalent de « ssh -N -D »).

Utilisé sur Android, où il n'y a pas de programme « ssh ». Nécessite le module Python « paramiko ».
Seul le TCP est transporté (commande CONNECT de SOCKS5) ; l'UDP est refusé.
"""
import select
import socket
import struct
import threading

try:
    import paramiko  # type: ignore
except Exception:  # noqa
    paramiko = None


def available():
    return paramiko is not None


class SshSocks:
    def __init__(self, host, port, user, password, listen_port, log=None):
        self.host, self.port = host, int(port)
        self.user, self.password = user, password
        self.listen_port = int(listen_port)
        self.log = log or (lambda m: None)
        self.client = None
        self.transport = None
        self.server = None
        self._stop = threading.Event()

    # -- état ------------------------------------------------------------
    def alive(self):
        return (not self._stop.is_set()) and self.transport is not None and self.transport.is_active()

    # -- démarrage -------------------------------------------------------
    def start(self):
        if paramiko is None:
            raise RuntimeError("module paramiko absent")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.host, port=self.port, username=self.user, password=self.password or None,
                            timeout=30, banner_timeout=40, auth_timeout=40,
                            allow_agent=False, look_for_keys=False)
        self.transport = self.client.get_transport()
        self.transport.set_keepalive(15)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", self.listen_port))
        self.server.listen(64)
        self.server.settimeout(1.0)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self.log("Session SSH ouverte, proxy SOCKS5 sur 127.0.0.1:%d" % self.listen_port)

    def stop(self):
        self._stop.set()
        for obj in (self.server, self.client):
            try:
                if obj:
                    obj.close()
            except Exception:  # noqa
                pass

    # -- SOCKS5 ----------------------------------------------------------
    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    @staticmethod
    def _recv_exact(conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("fermé")
            buf += chunk
        return buf

    def _handle(self, conn):
        chan = None
        try:
            conn.settimeout(15)
            ver, nmeth = self._recv_exact(conn, 2)
            if ver != 5:
                return
            self._recv_exact(conn, nmeth)
            conn.sendall(b"\x05\x00")
            ver, cmd, _, atyp = self._recv_exact(conn, 4)
            if atyp == 1:
                addr = socket.inet_ntoa(self._recv_exact(conn, 4))
            elif atyp == 3:
                ln = self._recv_exact(conn, 1)[0]
                addr = self._recv_exact(conn, ln).decode("utf-8", "ignore")
            elif atyp == 4:
                addr = socket.inet_ntop(socket.AF_INET6, self._recv_exact(conn, 16))
            else:
                conn.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            port = struct.unpack(">H", self._recv_exact(conn, 2))[0]
            if cmd != 1:      # seul CONNECT (TCP) est géré
                conn.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            try:
                chan = self.transport.open_channel("direct-tcpip", (addr, port), ("127.0.0.1", 0), timeout=20)
            except Exception:  # noqa
                conn.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            conn.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            conn.settimeout(None)
            self._pump(conn, chan)
        except Exception:  # noqa
            pass
        finally:
            for o in (chan, conn):
                try:
                    if o:
                        o.close()
                except Exception:  # noqa
                    pass

    def _pump(self, conn, chan):
        while not self._stop.is_set():
            r, _, _ = select.select([conn, chan], [], [], 1.0)
            if conn in r:
                data = conn.recv(32768)
                if not data:
                    return
                chan.sendall(data)
            if chan in r:
                data = chan.recv(32768)
                if not data:
                    return
                conn.sendall(data)
