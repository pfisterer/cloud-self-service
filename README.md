# cloud-self-service

The umbrella Helm chart for the DHBW cloud self-service platform. It composes four services that each live, and are released, next to their own code:

| Subchart | Repository |
|---|---|
| `dynamic-zones` | [pfisterer/dynamic-zones](https://github.com/pfisterer/dynamic-zones) — self-service DNS zones on PowerDNS |
| `openstack-management-api` | [pfisterer/openstack-management-api](https://github.com/pfisterer/openstack-management-api) — OpenStack projects and quotas |
| `role-provider-service` | [pfisterer/role-provider-service](https://github.com/pfisterer/role-provider-service) — groups and authorization |
| `self-service-ui` | [pfisterer/self-service-ui](https://github.com/pfisterer/self-service-ui) — the web frontend |

## Why an umbrella and not one big chart

Each chart stays with the code it describes, because they change together: a `Dockerfile` and a `securityContext` have had to move in a single commit more than once. What was missing was not fewer charts but a composition layer — and versioned chart artifacts instead of a pointer at a branch.

Pinning a subchart version pins that chart's `appVersion`, which pins the image tag. "New chart, old image" therefore stops being a state that can exist, rather than one that discipline has to prevent. One number now answers "what is running": the version of this chart.

## Installing

The subcharts come from `oci://ghcr.io/pfisterer/charts`, published by each service's own CI:

```sh
helm dependency build chart/
helm install cloud-self-service chart/ -f my-values.yaml
```

Every environment-specific value is passed in. Values for a subchart go under its chart name:

```yaml
dynamic-zones:
  dynamicZonesAPI:
    hostname: dyndnsapi.example.org
```

Each subchart ships a `values.schema.json`, so a misspelled key fails the render instead of being silently ignored.

## What is deliberately not here

Postgres, cert-manager, Argo CD itself, the monitoring stack, PowerDNS and dnsdist, and the reverse proxy in front of the UI. Those are substrate: they are assumed to exist, and the reference deployment brings them along separately.

## Names

`chart/values.yaml` pins each subchart's `fullnameOverride`. Resource names would otherwise derive from the release name, and adopting existing installations under one release would rename every object — including the Service names that the reverse proxies forward to. Change those only in a window where every reference moves with them.
