"""Brings the umbrella's subcharts to their newest published versions and gives the umbrella its next version.

Used by the scheduled workflow (bump.yml) and by `make bump` on a developer's machine, so both decide the same way.

Without an argument it is the scheduled job's rule: the newest subchart versions including prereleases (">=0.0.0-0"; the services publish -test.N), and the result is always a PRERELEASE — staging resolves ">=0.0.0-0" and picks it up, production resolves ">=0.0.0" and cannot see it, so this can never move production on its own.

With a version (`bump.py 0.1.91`), it is a deliberate promotion: a stable version takes the newest STABLE subcharts only (">=0.0.0"), a -test version the newest of all.

Prints `version=…` and `changed=…` lines (GitHub step outputs); `changed=` is empty when nothing moved and no version was given.
"""
import re
import subprocess
import sys

CHART = "chart/Chart.yaml"


def newest(name, constraint):
    out = subprocess.check_output(
        ["helm", "show", "chart", f"oci://ghcr.io/pfisterer/charts/{name}", "--version", constraint],
        text=True, stderr=subprocess.DEVNULL)
    return re.search(r"^version: (\S+)$", out, re.M).group(1)


def next_prerelease(cur):
    pre = re.match(r"^(\d+)\.(\d+)\.(\d+)-test\.(\d+)$", cur)
    if pre:
        major, minor, patch, n = (int(g) for g in pre.groups())
        return f"{major}.{minor}.{patch}-test.{n + 1}"
    major, minor, patch = (int(g) for g in re.match(r"^(\d+)\.(\d+)\.(\d+)$", cur).groups())
    return f"{major}.{minor}.{patch + 1}-test.1"


def main():
    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    stable = bool(wanted) and "-" not in wanted
    chart = open(CHART).read()
    changed = []
    for name, current in re.findall(r"  - name: (\S+)\n    version: (\S+)\n", chart):
        latest = newest(name, ">=0.0.0" if stable else ">=0.0.0-0")
        if latest != current:
            chart = chart.replace(f"  - name: {name}\n    version: {current}\n", f"  - name: {name}\n    version: {latest}\n", 1)
            changed.append(f"{name} {current} -> {latest}")
    if not changed and not wanted:
        print("changed=")
        return
    # A new set of subcharts is a new platform version, or the artifact would be republished under a version that already means something else.
    new = wanted or next_prerelease(re.search(r"^version: (\S+)$", chart, re.M).group(1))
    chart = re.sub(r"^version: .*$", f"version: {new}", chart, count=1, flags=re.M)
    chart = re.sub(r'^appVersion: .*$', f'appVersion: "{new}"', chart, count=1, flags=re.M)
    open(CHART, "w").write(chart)
    print(f"version={new}")
    print("changed=" + ("; ".join(changed) or "subcharts unchanged"))


if __name__ == "__main__":
    main()
