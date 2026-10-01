"""Persistent simplified authoritative DNS server (UDP 53533)."""
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import socket

RECORD_FILE = Path(os.environ.get("DNS_RECORD_FILE", Path(__file__).parent / "data" / "records.json"))
QUERY = re.compile(r"TYPE=A\nNAME=([^\s=]+)\n")
REGISTRATION = re.compile(r"TYPE=A\nNAME=([^\s=]+) VALUE=([^\s=]+) TTL=([0-9]+)\n")


def handle(message, path=RECORD_FILE):
    registration = REGISTRATION.fullmatch(message)
    query = QUERY.fullmatch(message)
    if not registration and not query:
        return b"ERROR=BAD_REQUEST\n"
    # Read the persistent file for queries, as required by the lab.
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if registration:
        hostname, ip, ttl = registration.groups()
        try:
            ip = str(ipaddress.IPv4Address(ip))
        except ValueError:
            return b"ERROR=BAD_REQUEST\n"
        records[hostname] = {"type": "A", "value": ip, "ttl": int(ttl)}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(records, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return b"OK\n"
    hostname = query[1]
    record = records.get(hostname)
    if record is None:
        return b"ERROR=NOT_FOUND\n"
    return f"TYPE=A\nNAME={hostname} VALUE={record['value']} TTL={record['ttl']}\n".encode("ascii")


def main():
    logging.basicConfig(level=logging.INFO)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", 53533))
        logging.info("AS listening on UDP 53533; records: %s", RECORD_FILE)
        while True:
            message, address = sock.recvfrom(65535)
            try:
                response = handle(message.decode("ascii"))
            except UnicodeError:
                response = b"ERROR=BAD_REQUEST\n"
            except (OSError, ValueError, KeyError, TypeError):
                logging.exception("Unable to process DNS request")
                response = b"ERROR=SERVER_ERROR\n"
            sock.sendto(response, address)


if __name__ == "__main__":
    main()
