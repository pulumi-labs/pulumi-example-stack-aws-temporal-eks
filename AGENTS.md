# Maintaining the Temporal EKS invoice example

- Keep Python Pulumi entrypoint `__main__.py`, `settings.py`, `foundation.py`,
  `services.py`, pins, both complete hash locks, config/CA inputs and `worker/`
  as one standalone runtime closure. `Pulumi.yaml` is project metadata.
- Preserve exact official chart archive verification, immutable image pins,
  wheel hashes and upstream notices. Generated worker images need an actual
  digest and complete pre-execution scan; no fake prebuilt application pin.
- Do not execute dependencies, providers, Helm or workloads on the workstation.
  Use the approved scanned sandbox and record real installed-schema/render/
  serialization, useful workflow, denied-client and cleanup results.
- Use explicit AWS account/us-east-2 and secret kubeconfig providers. Keep all
  owned AWS names under resourcePrefix and pulumi-project/pulumi-stack tags.
  The cluster/VPC/nodes/scoped execution identity remain operator-owned.
- Master DB credential belongs only in the bootstrap Job. Application login
  owns the two databases. Both schema/server clients and bootstrap psql must
  verify the real RDS hostname using the pinned regional AWS CA.
- Frontend and internode require mTLS from the dedicated CA. Server certificates
  need SAN temporal.internal and both server/client EKUs; worker clients receive
  only their separate client key. No plaintext/internal-frontend/public bypass.
  Accepted certificates have full dedicated-server trust, not tenant isolation.
- Preserve schema-before-server and namespace-before-worker ordering, exact
  native SQL schema paths and fixed billing namespace retention semantics.
  History shard count is immutable after initialization. Updates/rotations need
  maintenance; do not claim HA, restore or scaling validation without evidence.
- Keep tests and research evidence in the builder/run directories, outside this
  minimal export. Runtime changes invalidate downstream validation.
- Do not commit state, real config, kubeconfig, keys, private logs or acquired
  artifact/scan payloads. Preserve encrypted state until cleanup is independently
  reconciled, including retained snapshots and shared-resource exclusions.
- Do not select a license for authored code, publish, enable CI, or change
  repository visibility without applicable owner authorization.
