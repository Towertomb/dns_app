# Lab 3 Problem 2 — dns_app

Implementation based on the uploaded Lab 3 PDF, Problem 2, pages 9–13.

## Services

| Service | Transport / port | Endpoint |
| --- | --- | --- |
| US | HTTP 8080 | GET /fibonacci?hostname=...&fs_port=...&number=...&as_ip=...&as_port=... |
| FS | HTTP 9090 | PUT /register; GET /fibonacci?number=... |
| AS | UDP 53533 | DNS-like registration and query |

Each service directory is an independent Docker build context.

## Run with Docker (PowerShell)

Run all commands from the directory containing this README. Docker Desktop must
be running with Linux containers enabled.

Create the network and persistent volume once. If `dns-lab` already exists, reuse
it and skip the network creation command.

```powershell
docker network create dns-lab
docker volume create dns-records
docker build -t lab3-as:latest ./AS
docker build -t lab3-fs:latest ./FS
docker build -t lab3-us:latest ./US
docker run -d --name lab3-as --network dns-lab -p 53533:53533/udp -v dns-records:/data lab3-as:latest
docker run -d --name lab3-fs --network dns-lab -p 9090:9090 lab3-fs:latest
docker run -d --name lab3-us --network dns-lab -p 8080:8080 lab3-us:latest
```

If these named containers already exist and their images have not changed,
start them instead of running `docker run` again:

```powershell
docker start lab3-as lab3-fs lab3-us
```

Register FS using the container addresses on the shared Docker network:

```powershell
$asIP = docker inspect -f '{{(index .NetworkSettings.Networks "dns-lab").IPAddress}}' lab3-as
$fsIP = docker inspect -f '{{(index .NetworkSettings.Networks "dns-lab").IPAddress}}' lab3-fs
$body = @{
    hostname = "fibonacci.com"
    ip = "$fsIP"
    as_ip = "$asIP"
    as_port = "53533"
} | ConvertTo-Json

$response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:9090/register" -Method Put -ContentType "application/json" -Body $body
$response.StatusCode
$response.Content

$queryUrl = "http://localhost:8080/fibonacci?hostname=fibonacci.com&fs_port=9090&number=10&as_ip=$asIP&as_port=53533"
$response = Invoke-WebRequest -UseBasicParsing -Uri $queryUrl
$response.StatusCode
$response.Content
```

Expected: registration returns `201` / `Registered`; query returns `200` / `55`.
Do not use localhost for communication between separate containers.
The `dns-records` volume preserves AS records when its container is recreated.

Stop the standalone containers before running the Python integration tests:

```powershell
docker stop lab3-us lab3-fs lab3-as
```

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

## Deploy to local Kubernetes with Minikube (PowerShell)

This repository includes `deploy_dns.yml` for local Minikube deployment.
The lab's extra-credit wording requires a **cloud Kubernetes cluster**;
local Minikube alone does not fulfill that cloud requirement. No cloud deployment
is claimed here.

### 1. Prerequisites and cluster startup

Install Docker Desktop, Minikube and kubectl. Start Docker Desktop with Linux
containers enabled. Open PowerShell in this project directory.

```powershell
minikube start --driver=docker
kubectl config use-context minikube
kubectl config set-context --current --namespace=default
minikube status
kubectl get nodes
```

`minikube start` creates or starts the local cluster; `use-context` directs
subsequent kubectl commands to it. The examples use the default namespace and
default Minikube profile. No standalone `docker run` services are needed.

### 2. Build and load application images

```powershell
docker build -t lab3-as:latest ./AS
docker build -t lab3-fs:latest ./FS
docker build -t lab3-us:latest ./US
minikube image load lab3-as:latest
minikube image load lab3-fs:latest
minikube image load lab3-us:latest
minikube image ls
```

All three `lab3-*` images should appear, possibly with the prefix
`docker.io/library/`. The manifest uses `imagePullPolicy: IfNotPresent`, so the
loaded images can be used without publishing them to a registry.

### 3. Apply the manifest and wait for readiness

```powershell
kubectl apply -f deploy_dns.yml
kubectl rollout status deployment/lab3-as --timeout=180s
kubectl rollout status deployment/lab3-fs --timeout=180s
kubectl rollout status deployment/lab3-us --timeout=180s
kubectl get pods
kubectl get services
kubectl get pvc
```

`apply` creates or updates the declared resources. `rollout status` waits for a
Deployment to finish; it does not initiate a restart or test business logic.

The file defines three single-replica Deployments, three NodePort Services, and
the `as-data` PersistentVolumeClaim. AS mounts the volume at `/data`, with
records stored in `/data/records.json`. The AS Deployment uses `Recreate` to
avoid overlapping writers during an update.

| Service | Internal service/container port | NodePort |
| --- | --- | --- |
| lab3-as | 53533/UDP | 30001/UDP |
| lab3-fs | 9090/TCP | 30002/TCP |
| lab3-us | 8080/TCP | 30003/TCP |

Expected: all three application Pods are `1/1 Running`; `as-data` is `Bound`.
`EXTERNAL-IP: <none>` is normal for these NodePort Services. Keep the built-in
`kubernetes` Service. A ready Pod alone does not prove registration/query works.

### 4. Open Windows access tunnels

With the Windows Docker driver, the Minikube node IP generally cannot be reached
directly from the Windows host. Open two additional PowerShell windows.

Window A (FS):

```powershell
minikube service lab3-fs --url
```

Window B (US):

```powershell
minikube service lab3-us --url
```

Keep both windows running. Copy the HTTP URL printed in each window; the local
ports are assigned dynamically and need not be 30002 or 30003. These tunnels do
not change the NodePorts configured in the manifest. AS is accessed over UDP
from inside the cluster, so it needs no Windows HTTP tunnel.

### 5. Register FS

Back in the main PowerShell window, replace the two URL placeholders with the
actual URLs from step 4:

```powershell
$fsUrl = "http://127.0.0.1:REPLACE_WITH_FS_TUNNEL_PORT"
$usUrl = "http://127.0.0.1:REPLACE_WITH_US_TUNNEL_PORT"
$asIP = kubectl get service lab3-as -o jsonpath='{.spec.clusterIP}'
$fsIP = kubectl get service lab3-fs -o jsonpath='{.spec.clusterIP}'

$body = @{
    hostname = "fibonacci.com"
    ip = "$fsIP"
    as_ip = "$asIP"
    as_port = "53533"
} | ConvertTo-Json

$response = Invoke-WebRequest -UseBasicParsing -Uri "$fsUrl/register" -Method Put -ContentType "application/json" -Body $body
$response.StatusCode
$response.Content
```

Expected: `201` and `Registered`. The request reaches FS, which sends the
specified registration message to AS over UDP. The registered address is the
FS **Service ClusterIP**, not a Pod IP or Windows localhost address. This Service
IP remains stable across Pod replacements, as long as the Service is retained.

### 6. Request a Fibonacci number through US

```powershell
$queryUrl = "$usUrl/fibonacci?hostname=fibonacci.com&fs_port=9090&number=10&as_ip=$asIP&as_port=53533"
$response = Invoke-WebRequest -UseBasicParsing -Uri $queryUrl
$response.StatusCode
$response.Content
```

Expected: `200` and `55`. US queries AS for the registered address, then requests
the Fibonacci result from FS. Internal communication uses ports 53533 and 9090,
not the external NodePorts. You can also paste the value of `$queryUrl` into a
browser while the US tunnel remains open.

### 7. Verify persistence after replacing the AS Pod

```powershell
kubectl rollout restart deployment/lab3-as
kubectl rollout status deployment/lab3-as --timeout=180s
Invoke-RestMethod -Uri $queryUrl
```

Do not re-register between these commands. A result of `55` demonstrates that
the new AS Pod can read the existing registration from the mounted volume.
Minikube storage survives this Pod replacement; it is not a backup against
deleting the cluster or its storage.

### 8. Diagnose problems

```powershell
kubectl get pods
kubectl get events --sort-by=.metadata.creationTimestamp
kubectl describe deployment lab3-as
kubectl describe pvc as-data
kubectl logs deployment/lab3-as --tail=100
kubectl logs deployment/lab3-fs --tail=100
kubectl logs deployment/lab3-us --tail=100
```

- `ImagePullBackOff`: confirm exact image names and tags in the manifest, then
  confirm those images appear in `minikube image ls`.
- Pending PVC: check `kubectl get storageclass` and `minikube addons list`.
  This manifest requires a default StorageClass. If disabled, enable Minikube's
  `storage-provisioner` and `default-storageclass` addons.
- HTTP 502/504: inspect FS/US and AS logs; recheck the current AS Service IP and
  internal port 53533. Do not put the Windows tunnel address into `as_ip`.
- Tunnel stopped: rerun the corresponding `minikube service ... --url` command
  and update the URL variable if its port changed.
- Service deleted/recreated: refresh both ClusterIP variables and register FS
  again, because the old stored Service IP may no longer be valid.

### 9. Stop and resume

Press Ctrl+C in the two tunnel windows, then stop the local cluster:

```powershell
minikube stop
```

Resume with `minikube start`, confirm the context and Pod state, then reopen the
tunnels and refresh the PowerShell variables. Do not use `minikube delete` if
you want to retain this cluster and its local data.

For intentional removal of just this application's workloads and Services,
while retaining its PVC:

```powershell
kubectl delete deployment lab3-as lab3-fs lab3-us
kubectl delete service lab3-as lab3-fs lab3-us
```

Avoid `kubectl delete -f deploy_dns.yml` when preserving records: that command
also deletes the PVC and may delete its backing storage. Recreating Services
later requires refreshing their addresses and re-registering FS.

### Reference documentation

- [Minikube Docker driver and Windows networking](https://minikube.sigs.k8s.io/docs/drivers/docker/)
- [Accessing Minikube applications](https://minikube.sigs.k8s.io/docs/handbook/accessing/)
- [Kubernetes image pull policies](https://kubernetes.io/docs/concepts/containers/images/)

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

With Flask installed and ports 8080, 9090 and 53533 free (docker deployment is not needed):

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
