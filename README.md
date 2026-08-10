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
  --version 0.1.0-test.1 -f my-values.yaml
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

## Adopting an existing installation

Resource names stay put, because `chart/values.yaml` pins each subchart's `fullnameOverride`. The **labels** do not: `app.kubernetes.io/instance` derives from the release name, and a Deployment's `spec.selector` is immutable — so the Services get the new selector while the running pods keep the old labels, every endpoint list empties, and everything answers 502.

Delete the four Deployments during the switch. Argo CD (or `helm upgrade`) recreates them with matching labels; the cost is one pod start, not a rename.

## What you need to bring

The chart installs the four services and the proxy in front of them. Everything they *talk to* is assumed to exist — the same way a chart expects a cluster rather than installing one.

**A Kubernetes cluster with an ingress controller and TLS.** The chart writes `Ingress` objects and leaves the certificate to the cluster; the DHBW installation serves a wildcard from a default TLS store, so no service carries its own. If you are starting from nothing, [k3s-dhbw-cloud-role](https://github.com/pfisterer/k3s-dhbw-cloud-role) is the Ansible role we use.

**PostgreSQL.** One database per service that needs one. Connection strings are passed through pre-created Secrets (`existingSecret`), never as values — so the chart never sees a password and none ends up in a rendered manifest.

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

## What is deliberately not here

Postgres, cert-manager, Argo CD, the monitoring stack, PowerDNS and dnsdist. Those are substrate. The DHBW installation drives them from a private Ansible repository, which is not published: eleven of its steps are `helm install <upstream chart>`, the cluster bootstrap is the public role linked above, and what remains is specific to one university's certificate authority, alerting and directory. Publishing it would mostly hand you our idiosyncrasies to undo.

## Names

`chart/values.yaml` pins each subchart's `fullnameOverride`. Resource names would otherwise derive from the release name, and adopting existing installations under one release would rename every object — including the Service names that the reverse proxies forward to. Change those only in a window where every reference moves with them.
