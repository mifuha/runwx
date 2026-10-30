"""Fail before this local pilot can open sockets or launch other programs."""
import sys


def install():
    def guard(event, args):
        if event in {"socket.__new__", "socket.getaddrinfo", "socket.gethostbyname",
                     "urllib.Request", "subprocess.Popen", "os.system"}:
            raise RuntimeError(f"offline pilot blocks {event}")
    sys.addaudithook(guard)
