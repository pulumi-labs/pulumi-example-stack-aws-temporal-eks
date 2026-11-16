# Temporal invoice workflows on Amazon EKS with PostgreSQL and Python Pulumi

Deploy a private Temporal server and a separate Python invoice worker on an
existing Amazon EKS cluster. Python Pulumi connects encrypted RDS PostgreSQL
history and visibility databases, schema initialization, mTLS credentials and
the worker. The workflow calculates an invoice, retries a requested transient
activity failure and exposes the completed result through workflow queries and
SQL visibility.

**Validation status, November 16, 2026 (UTC):** Native deployment and the
live invoice proof passed in an approved disposable EKS environment. The result
was 2598 subtotal, 208 tax and 2806 total cents on activity attempt 2. Persisted
retry history, the completed workflow query and SQL visibility matched. A
client with only the trusted CA was rejected with
`TLSV13_ALERT_CERTIFICATE_REQUIRED`.

The corrected image's explicit UID 1000 source ownership passed both non-root
startup imports and the live workflow. The 10 focused worker tests passed on
November 15. This remains a private review draft, with no production-readiness,
HA, restore or capacity claim.

## What it creates

* One private RDS PostgreSQL 15.18 `db.t4g.micro`, 20 GiB encrypted gp3 storage,
  seven-day backups, subnet/parameter/security groups and a node-to-RDS ingress rule.
* One Kubernetes namespace and dedicated token-free service account, database
  and mTLS Secrets, reviewed AWS CA and SQL bootstrap ConfigMap/Job.
* Official Temporal chart 1.8.0 with Server/admin-tools 1.32.2: separate frontend,
  history, matching and system-worker services. Schema and `billing` namespace
  creation use the chart's standard hooks. Web UI and persistent admin-tools
  Deployment are disabled.
* One independent Python application worker using a digest-pinned image you
  build from `worker/Dockerfile`. No application AWS identity is created.

All application services are ClusterIP. All clients require a certificate from
the dedicated trusted CA. Every accepted certificate has administrative trust in
this dedicated server. The example does not implement multi-tenant namespace
authorization. Kubernetes access and private networking do not replace mTLS.

## Prerequisites and versions

Use an existing EKS cluster in `us-east-2`, a VPC and two private RDS subnets in
different availability zones, selected worker-node security group, private API
route/DNS, AMD64 Linux nodes and an operator kubeconfig scoped to the example.
The node SG must be the actual SG used for pod-to-RDS traffic. Security Groups
for Pods require the matching source SG instead. Supply the exact private subnet
CIDRs for network-policy database egress. Verify CNI policy enforcement and
node-metadata/control-channel isolation in your platform; this stack does not
modify shared cluster, node, IAM, CNI or routing infrastructure.

The provisioner needs native RDS/EC2 lifecycle and tagging permissions in the
selected account, plus namespace/Secret/ConfigMap/Job/Deployment/Service and Helm
permissions in Kubernetes. Port-forward users need `pods/portforward` access.
The AWS provider sets `pulumi-project` and `pulumi-stack` tags. `resourcePrefix`
controls database identifiers and AWS name prefixes so an operator can scope
trial permissions. No IAM roles or mandatory permissions boundaries are added.

Infrastructure: Pulumi CLI/SDK 3.273.0, AWS 7.52.1, Kubernetes 4.34.2, CPython
3.12 ARM64 Linux glibc provisioner. `requirements.lock` inherits the reviewed
provider closure and adds hashed Pydantic 2.12.3 configuration parsing.
Worker: CPython 3.12.12 AMD64 Linux glibc, Temporal SDK 1.18.1, Pydantic 2.12.3,
AnyIO 4.11.0, with its own complete wheel hash lock. Other architectures require
a newly reviewed wheel closure; do not bypass hash checking.

Use an approved disposable execution environment. Acquire and scan source,
chart contents, all transitive wheels, tools/providers and image layers before
execution. Scan generated runnable output before running it. Do not build,
install, render, preview or test workloads on the workstation.

This private review draft is staged at
`pulumi-labs/pulumi-example-stack-aws-temporal-eks`. Cloning requires GitHub
access to the private repository:

```sh
git clone https://github.com/pulumi-labs/pulumi-example-stack-aws-temporal-eks.git
cd pulumi-example-stack-aws-temporal-eks
```

## Acquire exact inputs and build the worker

Download the official `temporal-1.8.0.tgz` release asset into `artifacts/`.
Verify SHA-256
`e65b454d620129f3d7da2c16611a7f754e2d89b20b7a135dc5f0916a062f3a9e`.
The program checks the local archive and bundled RDS CA bytes before creating
resources. The chart archive is an external acquired artifact, not a missing
generated source file. Source:
https://github.com/temporalio/helm-charts/releases/tag/temporal-1.8.0

Stage only the scanned Linux AMD64 wheels matching `worker/requirements.lock`
in `wheelhouse/`. The Dockerfile installs entirely from that directory, with
hash enforcement and no network dependency resolution. Pull the pinned
Python/uv images in `pins.json`, inspect and scan their complete content first.
In the approved VM, with an authorized private image registry:

```sh
docker build --network=none --platform linux/amd64 -f worker/Dockerfile \
  -t "${WORKER_IMAGE_TAG:?set an authorized private registry tag}" .
```

Scan the generated image, then push to that authorized registry. Capture its
actual immutable `registry/repository@sha256:...` reference. Configure that value
as `workerImage`; no prebuilt application image or fake digest is supplied.
Image-push permissions and EKS image-pull permissions remain operator-owned.

Stage the scanned ARM64 infrastructure wheel closure separately:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --no-index \
  --find-links /secure/infra-wheels --require-hashes --only-binary :all: \
  -r requirements.lock
```

Use a preinstalled reviewed Python interpreter. Do not allow implicit interpreter,
tool or provider downloads to bypass scanning.

## Configure private access and secrets

Use an encrypted state backend outside the source tree. Initialize a stack, then
set `resourcePrefix` to a unique lowercase DNS/RDS-safe prefix, at most 32
characters without consecutive/trailing hyphens. It defaults to
`temporal-<stack>`. For the coordinated trial use stack `ae4-temporal` and prefix
`ae4-temporal`.

```sh
pulumi stack init ae4-temporal
pulumi config set resourcePrefix ae4-temporal
pulumi config set workerImage "${WORKER_IMAGE_DIGEST:?use the actual scanned image digest}"
pulumi config set platform < /secure/platform.json
pulumi config set --secret kubeconfig < /secure/kubeconfig
pulumi config set --secret dbMasterPassword
pulumi config set --secret dbAppPassword
```

`platform.json` is operator-owned JSON with these fields. Replace the coordinate
variables with actual platform inventory before setting config:

```json
{
  "account_id": "your exact twelve-digit AWS account",
  "vpc_id": "your existing VPC ID",
  "private_subnet_ids": ["first private subnet ID", "second private subnet ID"],
  "database_subnet_cidrs": ["first exact subnet IPv4 CIDR", "second exact subnet IPv4 CIDR"],
  "node_security_group_id": "the source node or pod SG ID",
  "node_selector": {"eks.amazonaws.com/nodegroup": "your selected node group"}
}
```

The kubeconfig must identify this same account/cluster and contain only its
scoped guest credential or approved native authentication method. Do not
transfer a permanent admin credential. Both database passwords must be
independent 32-128-character random strings from `A-Z`, `a-z`, `0-9`, `_`, `-`.
Use the interactive secret prompts or standard input, never plaintext CLI
arguments or source-controlled config.

Issue certificates outside this repository from a dedicated private CA:

* Server certificate: SAN `DNS:temporal.internal`, EKUs `serverAuth,clientAuth`.
  All Temporal server services use this certificate, including internode clients.
* Separate application/operator client certificate: EKU `clientAuth`.
* PEM certificates/keys; CA certificate must verify both chains.

Supply the exact reviewed PEM files through stdin:

```sh
pulumi config set --secret tlsCaCertificate < /secure/tls/ca.crt
pulumi config set --secret tlsServerCertificate < /secure/tls/server.crt
pulumi config set --secret tlsServerPrivateKey < /secure/tls/server.key
pulumi config set --secret tlsClientCertificate < /secure/tls/client.crt
pulumi config set --secret tlsClientPrivateKey < /secure/tls/client.key
```

The stack never generates a CA, stores a CA signing key, exports secret values
or mounts the RDS master credential into server/application pods. SQL clients
use the real RDS hostname and verify it against the bundled AWS regional CA.

## Preview, deploy and run a useful workflow

Review cost, scoped identities, sandbox and exact artifact scan evidence first.
Then inspect the refreshed plan, especially network exposure, schema hooks,
RDS protection and ownership:

```sh
pulumi preview --refresh --diff --save-plan /secure/temporal-plan.json
pulumi up --plan /secure/temporal-plan.json
namespace=$(pulumi stack output namespace)
kubectl -n "$namespace" rollout status deployment/invoice-worker --timeout=180s
kubectl -n "$namespace" port-forward --address 127.0.0.1 \
  service/temporal-frontend 7233:7233
```

From another authorized guest session with the scanned worker environment,
set `TEMPORAL_ADDRESS=127.0.0.1:7233`, `TEMPORAL_NAMESPACE=billing`, and
`TEMPORAL_TLS_DIRECTORY=/secure/tls` where the client files are named
`ca.crt`, `tls.crt`, `tls.key`. The TLS server name remains `temporal.internal`.
Use a fresh workflow ID and write an invoice request outside the repository:

```json
{
  "invoice_id": "invoice-001",
  "items": [{"quantity": 2, "unit_price_cents": 1299}],
  "tax_basis_points": 800,
  "simulate_transient_failure": true
}
```

```sh
python -m worker.submit /secure/invoice.json
```

Expected result: 2598 subtotal, 208 tax, 2806 total cents, activity attempt 2.
With `simulate_transient_failure=false` normal calculation succeeds on attempt 1.
The activity has no external side effects and does not process payments.
Duplicate workflow IDs are rejected during the server's retention window.
The application exposes the typed `invoice_result` workflow query. SQL visibility
supports `WorkflowId = 'invoice-invoice-001' AND ExecutionStatus = 'Completed'`;
visibility is eventually consistent. Internal acceptance assets in the builder
tree drive result/query/history/visibility checks and the missing-certificate
denial; they are deliberately separate from this runtime export.

## Troubleshooting and limitations

Schema errors: inspect the failed Helm hook Job and actual mounted CA/secret
references in the approved environment. Both databases must be owned by the
application login. Do not blindly retry a failed migration or bypass TLS.
Keep logs private because they may contain operational identifiers.

TLS errors: verify CA chains, EKUs, certificate expiration and server SAN.
Namespace creation uses the server certificate as a client, so it needs both
EKUs. Missing client certificates must fail even through a working port-forward.
There is no plaintext frontend or internal frontend bypass.

Networking errors: verify private API access, selected pod/node SG, database
subnets and enforced CNI policies. NodeLocal DNS users must adapt the DNS policy
to their verified resolver path before deployment. No speculative proxy,
Tailscale operator, cluster runner or public exposure is part of the application.

The `billing` namespace retains closed workflows for three days. The official
namespace hook does not update retention for an existing namespace; an attended
native Temporal operator update is required for that future change. Never change
history shard count after initial database creation. Credential or schema
updates need a maintenance window; bootstrap input versions replace the Job,
and credential revisions roll server/worker pods. Rolling recovery, data
restore, performance and independent scaling are untested.

## Costs and complete cleanup

RDS instance/storage/backups and retained snapshots incur charges. Existing EKS,
nodes, NAT and registry storage also cost money. Obtain current `us-east-2`
pricing for your actual platform before deploying; no fixed cost estimate is
claimed. Budgets are alerts, not hard caps.

RDS and Pulumi deletion protection default on. To deliberately remove this
example, first stop/drain the application worker and confirm data disposition.
Leave the existing cluster intact. For a final snapshot, set a unique
`finalSnapshotIdentifier`. To delete a disposable trial without a final snapshot,
explicitly set `retainFinalSnapshot=false` as well:

```sh
kubectl -n "$namespace" scale deployment/invoice-worker --replicas=0
pulumi config set protectData false
# Optional, only after authorizing disposal of this example's data:
pulumi config set retainFinalSnapshot false
pulumi preview --refresh --diff
pulumi up
pulumi destroy
```

The final `pulumi up` clears RDS/Pulumi protection before destroy. Helm uninstall
removes chart resources; deleting the Kubernetes namespace removes its owned
Secrets and Jobs. Temporal namespace records/history remain in RDS until its
deletion or retained final snapshot. Independently inventory owned RDS resources,
snapshots/backups, security-group rule/group, subnet/parameter groups, namespace,
Helm resources, temporary registry images and port-forward processes. Resolve
retained billable objects before removing encrypted state. Never delete the
preexisting cluster, node group, VPC or operator credentials.

## Attribution, license and maintenance

Temporal Server, official Helm charts and Python SDK are from Temporal
Technologies under MIT. See `UPSTREAM-NOTICES.md` and `licenses/`.
AWS distributes the regional RDS trust bundle. Python/PostgreSQL/uv and wheel
dependencies retain their licenses in their upstream distributions/images.
No license has been selected for the authored example code; private review does
not grant a public license.

Intended maintenance owner: `pulumi-labs`, pending owner confirmation before
public release. Authorized reviewers can report source issues through the private
repository's Issues and propose changes through pull requests. Do not post
credentials, state or private logs. A private security reporting contact remains
to be confirmed before public release; do not put sensitive reports in Issues.
This draft creates no external support commitment.
