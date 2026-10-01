"""Lab 3 Fibonacci Server (HTTP 9090)."""
import ipaddress
import re
import socket
import sys

from flask import Flask, Response, request

app = Flask(__name__)
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


def reply(text, status):
    return Response(str(text), status=status, mimetype="text/plain")


@app.put("/register")
def register():
    data = request.get_json(silent=True)
    required = ("hostname", "ip", "as_ip", "as_port")
    if not isinstance(data, dict) or any(k not in data for k in required):
        return reply("Missing registration fields", 400)
    try:
        hostname = data["hostname"]
        if not isinstance(hostname, str) or not hostname or re.search(r"[\s=]", hostname):
            raise ValueError()
        ip = str(ipaddress.IPv4Address(data["ip"]))
        as_ip = str(ipaddress.IPv4Address(data["as_ip"]))
        if isinstance(data["as_port"], bool) or not re.fullmatch(r"[0-9]+", str(data["as_port"])):
            raise ValueError()
        port = int(data["as_port"])
        if not 1 <= port <= 65535:
            raise ValueError()
    except (ValueError, TypeError, ipaddress.AddressValueError):
        return reply("Invalid registration fields", 400)
    message = f"TYPE=A\nNAME={hostname} VALUE={ip} TTL=10\n"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(3)
            sock.connect((as_ip, port))
            sock.send(message.encode("ascii"))
            acknowledgement = sock.recv(4096)
    except socket.timeout:
        return reply("Authoritative server timed out", 504)
    except (OSError, UnicodeError):
        app.logger.exception("UDP registration failed: AS=%s:%s", as_ip, port)
        return reply("Registration failed", 502)
    if acknowledgement != b"OK\n":
        app.logger.error("AS rejected registration: %r", acknowledgement)
        return reply("Registration rejected", 502)
    return reply("Registered", 201)


def fibonacci(n):
    # Fast doubling, using F(0)=0 and F(1)=1.
    a, b = 0, 1
    for bit in bin(n)[2:]:
        c, d = a * (2 * b - a), a * a + b * b
        a, b = (c, d) if bit == "0" else (d, c + d)
    return a


@app.get("/fibonacci")
def calculate():
    number = request.args.get("number", "")
    if not re.fullmatch(r"[+-]?[0-9]+", number):
        return reply("number must be an integer", 400)
    n = int(number)
    if n < 0:
        return reply("number must be nonnegative", 400)
    return reply(fibonacci(n), 200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090)
