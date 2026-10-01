"""Lab 3 User Server (HTTP 8080)."""
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from flask import Flask, Response, request

app = Flask(__name__)


def reply(text, status):
    return Response(text, status=status, mimetype="text/plain")


@app.get("/fibonacci")
def fibonacci():
    fields = ("hostname", "fs_port", "number", "as_ip", "as_port")
    if any(not request.args.get(key) for key in fields):
        return reply("Missing required parameter", 400)
    hostname = request.args["hostname"]
    try:
        if re.search(r"[\s=]", hostname):
            raise ValueError()
        hostname.encode("ascii")
        as_ip = str(ipaddress.IPv4Address(request.args["as_ip"]))
        ports = [request.args[key] for key in ("fs_port", "as_port")]
        if any(not re.fullmatch(r"[0-9]+", port) for port in ports):
            raise ValueError()
        fs_port, as_port = map(int, ports)
        if any(not 1 <= port <= 65535 for port in (fs_port, as_port)):
            raise ValueError()
    except (ValueError, UnicodeError):
        return reply("Invalid hostname, address or port", 400)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(3)
            sock.connect((as_ip, as_port))
            sock.send(f"TYPE=A\nNAME={hostname}\n".encode("ascii"))
            answer = sock.recv(4096).decode("ascii")
    except socket.timeout:
        return reply("Authoritative server timed out", 504)
    except (OSError, UnicodeError):
        app.logger.exception("UDP DNS query failed: AS=%s:%s", as_ip, as_port)
        return reply("DNS query failed", 502)
    if answer == "ERROR=NOT_FOUND\n":
        return reply("Hostname not registered", 404)
    match = re.fullmatch(r"TYPE=A\nNAME=([^\s=]+) VALUE=([^\s=]+) TTL=([0-9]+)\n", answer)
    if not match or match[1] != hostname:
        app.logger.error("Unexpected AS response: %r", answer)
        return reply("Invalid DNS response", 502)
    try:
        fs_ip = str(ipaddress.IPv4Address(match[2]))
    except ValueError:
        return reply("Invalid DNS address", 502)
    query = urllib.parse.urlencode({"number": request.args["number"]})
    url = f"http://{fs_ip}:{fs_port}/fibonacci?{query}"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as response:
            return reply(response.read(), response.status)
    except urllib.error.HTTPError as exc:
        return reply(exc.read(), exc.code)
    except (TimeoutError, socket.timeout):
        return reply("Fibonacci server timed out", 504)
    except (urllib.error.URLError, OSError):
        return reply("Fibonacci server unavailable", 502)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
