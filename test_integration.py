"""Run from dns_app with: python -m unittest -v test_integration.py"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(port, path, body=None, method="GET"):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 method=method, headers={"Content-Type": "application/json"})
    try:
        response = HTTP.open(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.read().decode()


def udp(message):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        sock.connect(("127.0.0.1", 53533))
        sock.send(message)
        return sock.recv(4096)


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Windows permits some overlapping binds unless exclusivity is requested.
        for port, kind in [(8080, socket.SOCK_STREAM), (9090, socket.SOCK_STREAM), (53533, socket.SOCK_DGRAM)]:
            with socket.socket(socket.AF_INET, kind) as probe:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                try:
                    probe.bind(("0.0.0.0", port))
                except OSError as exc:
                    raise RuntimeError(f"Cannot reserve port {port}: {exc}. Stop existing US/FS/AS servers, and check whether Windows blocks or reserves this port.") from exc
        cls.temp = tempfile.TemporaryDirectory()
        cls.processes = []
        cls.logs = []
        cls.addClassCleanup(cls.cleanup)
        cls.env = dict(os.environ, DNS_RECORD_FILE=str(Path(cls.temp.name) / "records.json"), PYTHONDONTWRITEBYTECODE="1")
        cls.as_process = cls.start("AS/server.py")
        cls.start("FS/app.py")
        cls.start("US/app.py")
        for port in (8080, 9090):
            for _ in range(100):
                try:
                    cls.check_processes()
                    http(port, "/")
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("HTTP service did not start")
        for _ in range(10):
            try:
                cls.check_processes()
                if udp(b"TYPE=A\nNAME=readiness\n") != b"ERROR=NOT_FOUND\n":
                    raise RuntimeError("Unexpected response from AS during startup")
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("AS did not start")

    @classmethod
    def start(cls, file):
        log_path = Path(cls.temp.name) / (file.replace("/", "_") + f".{len(cls.logs)}.log")
        log = log_path.open("wb")
        cls.logs.append((log, log_path))
        process = subprocess.Popen([sys.executable, str(ROOT / file)], env=cls.env,
                                   stdout=log, stderr=subprocess.STDOUT)
        cls.processes.append(process)
        return process

    @classmethod
    def check_processes(cls):
        for process in cls.processes:
            if process.poll() is not None:
                raise RuntimeError(f"Server exited with status {process.returncode}; see server logs below")

    @classmethod
    def cleanup(cls):
        for process in cls.processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        for log, path in cls.logs:
            log.close()
            print(f"\n--- {path.name} ---\n{path.read_text(encoding='utf-8', errors='replace')}", file=sys.stderr)
        cls.temp.cleanup()

    def register(self):
        result = http(9090, "/register", {"hostname": "fibonacci.com", "ip": "127.0.0.1",
                                         "as_ip": "127.0.0.1", "as_port": "53533"}, "PUT")
        self.assertEqual(result[0], 201, f"FS registration response: {result!r}")

    def test_end_to_end_and_exact_wire_format(self):
        self.register()
        self.assertEqual(udp(b"TYPE=A\nNAME=fibonacci.com\n"),
                         b"TYPE=A\nNAME=fibonacci.com VALUE=127.0.0.1 TTL=10\n")
        status, body = http(8080, "/fibonacci?hostname=fibonacci.com&fs_port=9090&number=10&as_ip=127.0.0.1&as_port=53533")
        self.assertEqual((status, body), (200, "55"))

    def test_us_missing_each_parameter(self):
        params = dict(hostname="fibonacci.com", fs_port="9090", number="10", as_ip="127.0.0.1", as_port="53533")
        for field in params:
            with self.subTest(field=field):
                query = urllib.parse.urlencode({k: v for k, v in params.items() if k != field})
                self.assertEqual(http(8080, "/fibonacci?" + query)[0], 400)

    def test_fibonacci_values_and_invalid_inputs(self):
        for n, expected in [(0, "0"), (1, "1"), (2, "1"), (10, "55"), (50, "12586269025")]:
            self.assertEqual(http(9090, f"/fibonacci?number={n}"), (200, expected))
        for value in ("", "abc", "1.5", "-1"):
            self.assertEqual(http(9090, "/fibonacci?number=" + value)[0], 400)

    def test_registration_validation_and_methods(self):
        self.assertEqual(http(9090, "/register", {}, "PUT")[0], 400)
        self.assertEqual(http(9090, "/register")[0], 405)
        self.assertEqual(udp(b"TYPE=A\nNAME=bad VALUE=no_ip TTL=10\n"), b"ERROR=BAD_REQUEST\n")
        self.assertEqual(udp(b"not a request"), b"ERROR=BAD_REQUEST\n")

    def test_unknown_and_upstream_errors(self):
        self.assertEqual(udp(b"TYPE=A\nNAME=missing.test\n"), b"ERROR=NOT_FOUND\n")
        base = "/fibonacci?hostname=missing.test&fs_port=9090&number=5&as_ip=127.0.0.1&as_port=53533"
        result = http(8080, base)
        self.assertEqual(result[0], 404, f"US lookup response: {result!r}")
        self.register()
        self.assertEqual(http(8080, base.replace("missing.test", "fibonacci.com").replace("number=5", "number=abc"))[0], 400)

    def test_z_persistence_after_restart(self):
        self.register()
        process = type(self).as_process
        process.terminate()
        process.wait(timeout=5)
        type(self).as_process = self.start("AS/server.py")
        for _ in range(10):
            try:
                answer = udp(b"TYPE=A\nNAME=fibonacci.com\n")
                break
            except OSError:
                time.sleep(.1)
        else:
            self.fail("AS restart failed")
        self.assertEqual(answer, b"TYPE=A\nNAME=fibonacci.com VALUE=127.0.0.1 TTL=10\n")


if __name__ == "__main__":
    unittest.main()
