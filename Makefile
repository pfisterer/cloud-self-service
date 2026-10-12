# Releasing the umbrella from this machine instead of waiting for the scheduled job (bump.yml, every 15 minutes) and chart.yml.
#
#   make bump              newest subcharts including -test.N, next -test version (what the scheduled job does)
#   make bump V=0.1.91     a deliberate version; a stable one takes only stable subcharts (production resolves ">=0.0.0" and syncs it on its own)
#   make publish           commit first; then lock, lint, package, push the chart to GHCR and push the commits
#
# Needs `helm registry login ghcr.io` with a token that may write packages.

.PHONY: bump publish

# The lock is updated here, so it goes into the same commit as the new pins.
bump:
	@python3 hack/bump.py $(V)
	@helm dependency update chart/ >/dev/null
	@echo "→ git commit -am 'release <version>' && make publish"

publish:
	@test -z "$$(git status --porcelain)" || { echo "✗ uncommitted changes — commit first (git commit -am 'release <version>')"; exit 1; }
	@set -e; V=$$(awk '/^version:/{print $$2; exit}' chart/Chart.yaml); \
	if helm show chart oci://ghcr.io/pfisterer/charts/cloud-self-service --version "$$V" >/dev/null 2>&1; then echo "✗ cloud-self-service $$V is already published — make bump first"; exit 1; fi; \
	helm dependency build chart/ >/dev/null; \
	helm lint chart/ >/dev/null; \
	helm template cloud-self-service chart/ >/dev/null; \
	rm -rf tmp/chart && mkdir -p tmp/chart && helm package chart/ --destination tmp/chart >/dev/null; \
	helm push tmp/chart/*.tgz oci://ghcr.io/pfisterer/charts; \
	git push; \
	echo "✅ cloud-self-service $$V published, commits pushed"
