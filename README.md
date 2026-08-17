# cloud-self-service

The umbrella Helm chart for the DHBW cloud self-service platform. It composes four services that each live, and are released, next to their own code:

| Subchart                   | Repository                                                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `dynamic-zones`            | [pfisterer/dynamic-zones](https://github.com/pfisterer/dynamic-zones) — self-service DNS zones on PowerDNS                  |
| `openstack-management-api` | [pfisterer/openstack-management-api](https://github.com/pfisterer/openstack-management-api) — OpenStack projects and quotas |
| `role-provider-service`    | [pfisterer/role-provider-service](https://github.com/pfisterer/role-provider-service) — groups and authorization            |
| `self-service-ui`          | [pfisterer/self-service-ui](https://github.com/pfisterer/self-service-ui) — the web frontend                                |

## Why an umbrella and not one big chart

Each chart stays with the code it describes, because they change together: a `Dockerfile` and a `securityContext` have had to move in a single commit more than once. What was missing was not fewer charts but a composition layer — and versioned chart artifacts instead of a pointer at a branch.

Pinning a subchart version pins that chart's `appVersion`, which pins the image tag. "New chart, old image" therefore stops being a state that can exist, rather than one that discipline has to prevent. One number now answers "what is running": the version of this chart.

## Installing

The chart is published as an OCI artifact and carries its subcharts inside it, so this needs neither a clone nor a dependency build:

```sh
helm install cloud-self-service \
  oci://ghcr.io/pfisterer/charts/cloud-self-service \
  --version 0.2.0 -f my-values.yaml
```

Every environment-specific value is passed in. Values for a subchart go under its chart name:

```yaml
dynamic-zones:
  dynamicZonesAPI:
    hostname: dyndnsapi.example.org
```

Each subchart ships a `values.schema.json`, so a misspelled key fails the render instead of being silently ignored.

To work on the chart itself, resolve the dependencies first — `build`, not `update`, so `Chart.lock` decides:

```sh
helm dependency build chart/
helm template cloud-self-service chart/ -f my-values.yaml
```

## What you need to bring

The chart installs the four services and the proxy in front of them. Everything they *talk to* is assumed to exist — the same way a chart expects a cluster rather than installing one.

**A Kubernetes cluster with an ingress controller and TLS.** The chart writes `Ingress` objects and leaves the certificate to the cluster; the DHBW installation serves a wildcard from a default TLS store, so no service carries its own.

**PostgreSQL** — only if you want the data to survive a pod restart. `dynamic-zones`, `openstack-management-api` and `role-provider-service` each also take `memory`, which seeds mock data instead and needs nothing at all; that is what [Minimal setup for development](#minimal-setup-for-development) uses.

There are two ways to hand a connection string over, and every subchart supports both. Either set the values (`db.connectionString` and friends) and the subchart renders its own Secret — the normal case — or pre-create that Secret yourself and name it in `existingSecret`, in which case the chart renders none and ignores those values.

The DHBW installation takes the second route, for three reasons worth knowing before copying it. Values reach the cluster inside an Argo CD `Application`, where everyone who may read Applications sees them in the UI and in `argocd app diff`; a Secret is separable by RBAC. One credential appears in two services' Secrets — the role provider's read token is also the management API's `role-provider-api-token` — and a single owner is what keeps those two in step. And rotating a Secret next to a Reloader annotation restarts the pods without touching a chart version.

**An OIDC issuer** with two clients: a public one the APIs validate tokens against, and a confidential one for the BFF proxy in front of the UI. The proxy needs `offline_access` to be grantable, or a long-idle tab is bounced back to the login instead of refreshed.

**A PowerDNS with its HTTP API enabled** — only if you want the DNS part. This is the one prerequisite that is not obvious, because the service does more than call the API: it pulls a zone's records over a TSIG-signed AXFR and writes changes over RFC 2136. So the nameserver needs

```ini
api=yes
webserver=yes
dnsupdate=yes
# Empty on purpose: no source IP is trusted, every update must carry a TSIG
# signature. Per-zone TSIG-ALLOW-AXFR metadata gates transfers the same way.
allow-dnsupdate-from=
dnsupdate-require-tsig=true
```

and it must be reachable from the cluster on port 53 for both TCP and UDP, not only through its API. [dynamic-zones](https://github.com/pfisterer/dynamic-zones) documents this in more detail, including what fronting it with [dnsdist](https://dnsdist.org/) buys you: an authoritative nameserver on the public internet is a reflection amplifier unless ANY-over-UDP is truncated and per-source rates are capped.

**An OpenStack** — only if you want the projects part, with an application credential that can create projects and set quotas.

Where a prerequisite is missing, switch that service off rather than letting it start into nothing:

```yaml
dynamic-zones:
  enabled: false             # no reachable PowerDNS
openstack-management-api:
  enabled: false             # no OpenStack
```

Both default to on, as do `role-provider-service` and `self-service-ui`. Note the one coupling the chart cannot enforce: switching off an API leaves the UI pointing at something that is gone, so clear the matching `selfServiceUI.dynamicZonesBaseUrl` or `cloudResourcesBaseUrl` in the same values.

## Minimal setup for development

Two things to know before writing values, both of which cost an afternoon if you find them out by trial:

- **Values are per subchart, not global.** No subchart reads `.Values.global`, so the issuer URL and the client id are repeated under each chart name. That is verbosity, not redundancy — the four services are released separately and can point at different clients.
- **The OIDC key is not in the same place everywhere.** `dynamic-zones` and `self-service-ui` take `auth.oidc`; `openstack-management-api` takes `openstackManagementApi.oidc`.

### Without any infrastructure

No database, no nameserver, no OpenStack — the three backends run on their in-memory store with mock data, and `dynamic-zones` stays off because it is the one service that genuinely cannot work without a PowerDNS. Enough to click through the UI, exercise the APIs and develop against them; nothing survives a pod restart.

```yaml
dynamic-zones:
  enabled: false

self-service-ui:
  selfServiceUI:
    hostname: selfservice.192.0.2.1.nip.io
    # Empty -> the DNS Zones tab's route is not registered and its nav link hides
    dynamicZonesBaseUrl: ""
    cloudResourcesBaseUrl: https://os-mgt.192.0.2.1.nip.io
  auth:
    oidc:
      issuerUrl: https://sso.example.org/realms/dev
      clientId: cloud-selfservice

openstack-management-api:
  openstackManagementApi:
    hostname: os-mgt.192.0.2.1.nip.io
    db:
      type: memory
      addMockData: true
    # "mock" serves built-in demo identities. See the note below before
    # switching this to "http".
    roleProvider:
      type: mock
    oidc:
      issuerUrl: https://sso.example.org/realms/dev
      clientId: cloud-selfservice

role-provider-service:
  roleProviderService:
    hostname: role-provider.192.0.2.1.nip.io
    db:
      type: memory
    api:
      tokens: dev-token
```

```sh
helm install dev oci://ghcr.io/pfisterer/charts/cloud-self-service \
  --version 0.2.0 -f my-values.yaml
```

To have the management API resolve real groups through `role-provider-service` instead of its demo identities, point it at the Service and give it one of that service's read tokens:

```yaml
openstack-management-api:
  openstackManagementApi:
    roleProvider:
      type: http
      url: http://role-provider-service:8085
      apiToken: dev-token     # must be one of role-provider's api.tokens
```

The token lands in the rendered Secret as `role-provider-api-token`. Worth knowing because the failure mode is quiet: the Deployment reads that key with `optional: true`, so leaving it empty does not stop the pod — every call to the role provider simply goes out unauthenticated and comes back 401.

### With PostgreSQL

For persistence, and to exercise the same storage path production uses. This assumes the [CloudNativePG](https://cloudnative-pg.io/) operator in the cluster; any other PostgreSQL works just as well, only the connection strings change.

```yaml
apiVersion: v1
kind: Secret
metadata: { name: dynamic-zones-db }
type: kubernetes.io/basic-auth
stringData: { username: dynamic_zones, password: dev }
---
apiVersion: v1
kind: Secret
metadata: { name: openstack-management-api-db }
type: kubernetes.io/basic-auth
stringData: { username: openstack_management_api, password: dev }
---
apiVersion: v1
kind: Secret
metadata: { name: role-provider-service-db }
type: kubernetes.io/basic-auth
stringData: { username: role_provider_service, password: dev }
---
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata: { name: postgres-cluster }
spec:
  instances: 1
  storage: { size: 2Gi }
  # Roles live inside the Cluster resource, which is why they are here and not
  # in the chart: a database cluster has exactly one owner.
  managed:
    roles:
      - { name: dynamic_zones, login: true, passwordSecret: { name: dynamic-zones-db } }
      - { name: openstack_management_api, login: true, passwordSecret: { name: openstack-management-api-db } }
      - { name: role_provider_service, login: true, passwordSecret: { name: role-provider-service-db } }
---
apiVersion: postgresql.cnpg.io/v1
kind: Database
metadata: { name: dynamic-zones }
spec:
  cluster: { name: postgres-cluster }
  name: dynamic_zones
  owner: dynamic_zones
---
apiVersion: postgresql.cnpg.io/v1
kind: Database
metadata: { name: openstack-management-api }
spec:
  cluster: { name: postgres-cluster }
  name: openstack_management_api
  owner: openstack_management_api
---
apiVersion: postgresql.cnpg.io/v1
kind: Database
metadata: { name: role-provider-service }
spec:
  cluster: { name: postgres-cluster }
  name: role_provider_service
  owner: role_provider_service
```

Then point each service at `postgres-cluster-rw`, and `dynamic-zones` at the nameserver:

```yaml
dynamic-zones:
  dynamicZonesAPI:
    hostname: dyndns.192.0.2.1.nip.io
    database:
      type: postgres
      hostname: postgres-cluster-rw
      name: dynamic_zones
      username: dynamic_zones
      password: dev
  auth:
    oidc:
      issuerUrl: https://sso.example.org/realms/dev
      clientId: cloud-selfservice
  powerDNS:
    apiUrl: http://pdns:8081
    apiKey: dev-api-key
    server:
      # PUBLIC address of the nameserver — it goes into the dig examples the UI
      # shows users, so it has to work from outside the cluster.
      ip: 192.0.2.53
      # Where the API sends its own AXFR and RFC 2136 traffic: in-cluster, by
      # Service name, so it never leaves and comes back in.
      queryTarget: pdns:53

openstack-management-api:
  openstackManagementApi:
    hostname: os-mgt.192.0.2.1.nip.io
    db:
      type: postgres
      connectionString: "host=postgres-cluster-rw user=openstack_management_api password=dev dbname=openstack_management_api port=5432 sslmode=disable TimeZone=UTC"
    roleProvider: { type: mock }
    oidc:
      issuerUrl: https://sso.example.org/realms/dev
      clientId: cloud-selfservice

role-provider-service:
  roleProviderService:
    hostname: role-provider.192.0.2.1.nip.io
    db:
      type: postgres
      connectionString: "host=postgres-cluster-rw user=role_provider_service password=dev dbname=role_provider_service port=5432 sslmode=disable TimeZone=UTC"
    api:
      tokens: dev-token

self-service-ui:
  selfServiceUI:
    hostname: selfservice.192.0.2.1.nip.io
    dynamicZonesBaseUrl: https://dyndns.192.0.2.1.nip.io
    cloudResourcesBaseUrl: https://os-mgt.192.0.2.1.nip.io
  auth:
    oidc:
      issuerUrl: https://sso.example.org/realms/dev
      clientId: cloud-selfservice
```

## Who owns what

The chart's boundary is not "everything it could install" but "everything whose only consumer is this platform". A cluster object that something else also uses belongs to whoever installs that something else — otherwise two things reconcile the same object and the last one to run wins.

| | Owner |
| --- | --- |
| Deployments, Services, Ingresses of the four services | this chart |
| Their Secrets — connection strings, API tokens, credentials | this chart, unless `existingSecret` names one you created |
| The BFF proxy in front of the UI (`bff.enabled` in `self-service-ui`) | this chart; it derives its upstream from that chart's own Service |
| Ingress controller, TLS certificate, shared Traefik middlewares | your cluster |
| PostgreSQL, PowerDNS, OIDC issuer, OpenStack | your cluster |
| Monitoring, alerting, backups | your cluster |

The DHBW installation is the same chart with every optional part switched off, because an Ansible playbook there owns the certificate, the shared PostgreSQL (whose roles four other consumers use), PowerDNS and dnsdist, the Traefik middlewares, monitoring and the Argo CD RBAC. None of that is in here, and none of it should be.
