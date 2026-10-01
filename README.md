# Lab 3 Problem 2 — dns_app

Implementation based on the uploaded Lab 3 PDF, Problem 2, pages 9–13.

## Services

| Service | Transport / port | Endpoint |
| --- | --- | --- |
| US | HTTP 8080 | GET /fibonacci?hostname=...&fs_port=...&number=...&as_ip=...&as_port=... |
| FS | HTTP 9090 | PUT /register; GET /fibonacci?number=... |
| AS | UDP 53533 | DNS-like registration and query |

Each service directory is an independent Docker build context.

## Run with Docker

From the dns_app directory:

```sh
docker network create dns-lab
docker volume create dns-records
docker build -t lab3-as ./AS
docker build -t lab3-fs ./FS
docker build -t lab3-us ./US
docker run -d --name lab3-as --network dns-lab -p 53533:53533/udp -v dns-records:/data lab3-as
docker run -d --name lab3-fs --network dns-lab -p 9090:9090 lab3-fs
docker run -d --name lab3-us --network dns-lab -p 8080:8080 lab3-us
docker network inspect dns-lab
```

Use the AS and FS container IPv4 addresses shown by the last command. In the
following examples, replace `AS_IP` and `FS_IP` with those addresses. On Windows
PowerShell use `curl.exe` instead of the `curl` alias.

```sh
curl -i -X PUT http://localhost:9090/register -H "Content-Type: application/json" --data '{"hostname":"fibonacci.com","ip":"FS_IP","as_ip":"AS_IP","as_port":"53533"}'
curl -i "http://localhost:8080/fibonacci?hostname=fibonacci.com&fs_port=9090&number=10&as_ip=AS_IP&as_port=53533"
```

Expected: registration HTTP 201; Fibonacci HTTP 200 with body `55`.
Do not use localhost as the AS/FS address between separate containers.
The named volume preserves AS records when the AS container is recreated.

## Run locally

Install Python 3.12+ and dependencies:

```sh
python -m pip install -r FS/requirements.txt
```

Open three terminals in dns_app and run one command in each:

```sh
python AS/server.py
python FS/app.py
python US/app.py
```

For local requests, use `127.0.0.1` for both `ip` and `as_ip`, and `53533`
for `as_port`. The default record file is `AS/data/records.json`.
`DNS_RECORD_FILE` can override its location.

## Exact DNS-like wire messages

Messages use ASCII, LF newlines, no separator dashes, and a final newline.
The second line of a registration/response contains three space-separated fields.

Registration sent by FS:

```text
TYPE=A
NAME=fibonacci.com VALUE=127.0.0.1 TTL=10
```

Query sent by US:

```text
TYPE=A
NAME=fibonacci.com
```

AS query response:

```text
TYPE=A
NAME=fibonacci.com VALUE=127.0.0.1 TTL=10
```

AS distinguishes the two request types by their fields. It writes registrations
to a JSON file atomically, and reads that file to answer queries. Re-registering
a hostname replaces its record. AS always listens on UDP 53533; clients use the
provided `as_port` (which also supports externally mapped ports).

## Required behavior and unspecified cases

- US: missing any of the five query parameters returns 400; success returns 200.
- FS: PUT registration returns 201 only after AS confirms persistence.
- FS: GET Fibonacci returns 200; missing or non-integer `number` returns 400.
- The PDF does not specify registration acknowledgement bytes or error datagrams.
  This implementation uses `OK\n`, `ERROR=BAD_REQUEST\n`,
  `ERROR=NOT_FOUND\n`, and `ERROR=SERVER_ERROR\n` for those cases only.
  The prescribed registration/query/record messages above are unchanged.
- The PDF does not specify indexing at zero or negative inputs. This implementation
  uses F(0)=0, F(1)=1 and rejects negative indices with 400.
- TTL is stored and returned as 10 seconds. Authoritative records are retained;
  the lab does not require a cache or deletion of authoritative records after TTL.
- Additional failure handling: malformed HTTP inputs return 400; unknown names
  return 404 at US; upstream failures return 502 and socket timeouts return 504.
  US forwards FS error status codes, including 400 for non-integer input.

## Tests

With Flask installed and ports 8080, 9090 and 53533 free:

```sh
python -m unittest -v test_integration.py
```

Tests start real HTTP/UDP processes, verify registration, exact DNS response bytes,
end-to-end calculation, missing parameters, invalid input, method handling,
unknown names, and persistence across an AS process restart. Temporary records
are isolated from the application's own database, and test processes are stopped.

Stop any manually started US/FS/AS instances before running tests. On Windows,
the test checks exclusive ownership of the ports. Startup failures are reported
explicitly, failed assertions include the HTTP response body, and server logs
are printed after the test run to help diagnose UDP/network failures.

## Submission

The ZIP contains the top-level `dns_app/` folder and its US, FS and AS directories.
The PDF also requires committing the folder to GitHub and submitting the ZIP to
Brightspace. Its deliverables section gives the filename pattern
`DCN-firstname_lastname_lab_3.zip`; rename the provided ZIP using your own name
if required. The optional Kubernetes extra-credit deployment is not included.
