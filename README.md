# Temporal invoice workflows on Amazon EKS with PostgreSQL and Python Pulumi

This example runs a private Temporal server and a small Python invoice worker on
an EKS cluster you already have. The useful result: business logic that keeps
going when things fail. If a step hits a temporary error, Temporal retries it
automatically and remembers every step in a database, so a workflow finishes
correctly across retries.

The sample workflow calculates an invoice, survives a deliberately injected
temporary failure and then exposes the finished result through a workflow query
and SQL search (visibility).

## Key terms

- **Temporal**: an open source workflow engine. You write workflows as normal
  code; Temporal records each step and retries failed steps (activities).
- **Worker**: your own process that runs workflow and activity code. Here it's a
  Python container, deployed separately from the Temporal server.
- **EKS** (Amazon Elastic Kubernetes Service): AWS's managed Kubernetes. You
  bring an existing cluster; this stack doesn't create one.
- **RDS** (Amazon Relational Database Service): managed PostgreSQL. It stores
  Temporal's workflow history and the visibility data used for searches.
- **mTLS** (mutual TLS): both sides of a connection present certificates. Every
  client, including the worker and Temporal's own services, must show a
  certificate from your private CA, or the connection is refused.
- **Helm**: the Kubernetes package manager. The stack installs the official
  Temporal Helm chart.
- **Pulumi**: infrastructure as code. The Python program in this repository
  creates the database, Kubernetes objects and Helm release in the right order.

## What the stack creates

- One private RDS PostgreSQL 15.18 `db.t4g.micro` with 20 GiB of encrypted gp3
  storage and seven-day backups, plus its subnet, parameter and security groups
  and a node-to-RDS ingress rule.
- One Kubernetes namespace with a dedicated token-free service account, database
  and mTLS Secrets, the reviewed AWS CA and a SQL bootstrap ConfigMap and Job.
- The official Temporal chart 1.8.0 with Server and admin-tools 1.32.2, running
  separate frontend, history, matching and system-worker services. The chart's
  standard hooks create the schema and the `billing` namespace. The Web UI and
  the long-running admin-tools Deployment are turned off.
- One Python invoice worker, using a digest-pinned image you build from
  `worker/Dockerfile`. The worker gets no AWS identity.

Every application service is ClusterIP, so nothing is exposed publicly. All
clients need a certificate from the dedicated CA, and any accepted certificate
has full administrative trust in this server. There's no multi-tenant namespace
authorization. Kubernetes access and private networking don't replace mTLS.

## Prerequisites

### AWS and cluster

- An existing EKS cluster in `us-east-2` with AMD64 Linux nodes.
- A VPC with two private RDS subnets in different availability zones, and their
  exact IPv4 CIDRs (used for network-policy database egress).
- The security group that pod-to-RDS traffic actually comes from. That's
  usually the worker-node security group; if you use Security Groups for Pods,
  use the matching pod security group instead.
- A private route and DNS to the Kubernetes API.
- An operator kubeconfig scoped to this example.

Check that your CNI enforces network policies and that node metadata and
control channels are isolated. This stack doesn't change shared cluster, node,
IAM, CNI or routing infrastructure.

### Permissions

- AWS: RDS and EC2 lifecycle and tagging permissions in the chosen account.
- Kubernetes: namespace, Secret, ConfigMap, Job, Deployment, Service and Helm
  permissions. Anyone using port-forward also needs `pods/portforward`.

The AWS provider adds `pulumi-project` and `pulumi-stack` tags. `resourcePrefix`
sets database identifiers and AWS name prefixes, so you can scope permissions to
those names. The stack adds no IAM roles and requires no permissions boundary.

### Tools and versions

- Infrastructure runner: CPython 3.12 on ARM64 Linux glibc, Pulumi CLI and SDK
  3.273.0, AWS provider 7.52.1, Kubernetes provider 4.34.2, plus `uv`, `kubectl`
  and Docker. `requirements.lock` holds the reviewed provider set plus hashed
  Pydantic 2.12.3 for configuration parsing.
- Worker image: CPython 3.12.12 on AMD64 Linux glibc, Temporal SDK 1.18.1,
  Pydantic 2.12.3 and AnyIO 4.11.0, with its own complete wheel hash lock. Other
  architectures need a newly reviewed wheel set. Don't bypass hash checking.
- A private container registry you're authorized to push to, and that your EKS
  nodes can pull from.
- An encrypted Pulumi state backend outside the source tree.

### Safe execution environment

Run everything in an approved disposable execution environment. Acquire and scan
the source, chart contents, all transitive wheels, tools, providers and image
layers before running them, and scan generated output (like the worker image)
before its first run. Don't build, install, render, preview or test the workload
on your workstation.

## Setup

### 1. Get the code

```sh
git clone https://github.com/pulumi-labs/pulumi-example-stack-aws-temporal-eks.git
cd pulumi-example-stack-aws-temporal-eks
```

### 2. Download and verify the Temporal Helm chart

Download the official `temporal-1.8.0.tgz` release asset from
https://github.com/temporalio/helm-charts/releases/tag/temporal-1.8.0 into
`artifacts/`. Its SHA-256 must be:

```text
e65b454d620129f3d7da2c16611a7f754e2d89b20b7a135dc5f0916a062f3a9e
```

The chart is something you download, not a missing file. Before it creates any
resource, the program checks this archive and the bundled RDS CA bytes.

### 3. Build and push the worker image

Put only the scanned Linux AMD64 wheels that match `worker/requirements.lock`
into `wheelhouse/`. The Dockerfile installs only from that directory, enforces
hashes and resolves nothing from the network. Pull the pinned Python and uv
images listed in `pins.json`, then inspect and scan their full contents. In the
approved VM:

```sh
docker build --network=none --platform linux/amd64 -f worker/Dockerfile \
  -t "${WORKER_IMAGE_TAG:?set an authorized private registry tag}" .
```

Scan the new image, push it to your registry and note its immutable reference
in the form `registry/repository@sha256:...`. You'll set it as `workerImage`.
No prebuilt application image is provided. Image push and EKS image pull
permissions are yours to manage.

### 4. Install the infrastructure dependencies

Stage the scanned ARM64 infrastructure wheels separately, then install them:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --no-index \
  --find-links /secure/infra-wheels --require-hashes --only-binary :all: \
  -r requirements.lock
```

Use a preinstalled, reviewed Python interpreter. Don't let tools download
interpreters, tools or providers on their own, because that skips scanning.

### 5. Create a stack and set basic configuration

Choose a unique `resourcePrefix`: lowercase, DNS and RDS safe, at most 32
characters, with no consecutive or trailing hyphens. If you leave it out, it
defaults to `temporal-<stack>`. The commands below use stack and prefix
`ae4-temporal`; replace them with your own names.

```sh
pulumi stack init ae4-temporal
pulumi config set resourcePrefix ae4-temporal
pulumi config set workerImage "${WORKER_IMAGE_DIGEST:?use the actual scanned image digest}"
pulumi config set platform < /secure/platform.json
pulumi config set --secret kubeconfig < /secure/kubeconfig
pulumi config set --secret dbMasterPassword
pulumi config set --secret dbAppPassword
```

`platform.json` describes your existing platform. Fill in real values from
your AWS and cluster inventory:

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

The kubeconfig must point at the same account and cluster and hold only a
scoped credential or an approved native authentication method. Never use a
permanent admin credential.

The two database passwords must be independent random strings, 32 to 128
characters long, using only `A-Z`, `a-z`, `0-9`, `_` and `-`. Enter them at the
interactive secret prompt or through standard input, never as plaintext command
arguments or in committed config.

### 6. Provide mTLS certificates

Issue certificates from a dedicated private CA, outside this repository:

- **Server certificate**: SAN `DNS:temporal.internal`, with EKUs
  `serverAuth,clientAuth`. All Temporal server services use it, including
  when they connect to each other.
- **Client certificate**: a separate certificate for the application and
  operators, with EKU `clientAuth`.
- Everything in PEM format, and the CA must verify both chains.

Load them through standard input:

```sh
pulumi config set --secret tlsCaCertificate < /secure/tls/ca.crt
pulumi config set --secret tlsServerCertificate < /secure/tls/server.crt
pulumi config set --secret tlsServerPrivateKey < /secure/tls/server.key
pulumi config set --secret tlsClientCertificate < /secure/tls/client.crt
pulumi config set --secret tlsClientPrivateKey < /secure/tls/client.key
```

The stack never generates a CA, never stores a CA signing key, never exports
secret values and never mounts the RDS master credential into server or
application pods. SQL clients connect to the real RDS hostname and verify it
against the bundled AWS regional CA.

### 7. Preview and deploy

Before deploying, confirm cost, scoped identities, your sandbox and the scan
evidence for every artifact. Save the plan and read it, paying attention to
network exposure, schema hooks, RDS protection and resource ownership:

```sh
pulumi preview --refresh --diff --save-plan /secure/temporal-plan.json
pulumi up --plan /secure/temporal-plan.json
namespace=$(pulumi stack output namespace)
kubectl -n "$namespace" rollout status deployment/invoice-worker --timeout=180s
kubectl -n "$namespace" port-forward --address 127.0.0.1 \
  service/temporal-frontend 7233:7233
```

Leave the port-forward running.

### 8. Run an invoice workflow

Open another authorized session that has the scanned worker environment, and set:

- `TEMPORAL_ADDRESS=127.0.0.1:7233`
- `TEMPORAL_NAMESPACE=billing`
- `TEMPORAL_TLS_DIRECTORY=/secure/tls`, a directory holding the client files
  named `ca.crt`, `tls.crt` and `tls.key`

The TLS server name stays `temporal.internal`. Write an invoice request outside
the repository, using a fresh invoice ID each time:

```json
{
  "invoice_id": "invoice-001",
  "items": [{"quantity": 2, "unit_price_cents": 1299}],
  "tax_basis_points": 800,
  "simulate_transient_failure": true
}
```

Submit it:

```sh
python -m worker.submit /secure/invoice.json
```

### 9. Check the result

Success means 2598 subtotal, 208 tax and 2806 total cents, finishing on
activity attempt 2. The first attempt failed on purpose and Temporal retried it.
With `simulate_transient_failure` set to `false`, the calculation succeeds on
attempt 1.

You can also read the result in two other ways:

- The typed `invoice_result` workflow query.
- SQL visibility, with
  `WorkflowId = 'invoice-invoice-001' AND ExecutionStatus = 'Completed'`.
  Visibility is eventually consistent, so it can lag for a moment.

The activity has no external side effects and doesn't process payments.
Reusing a workflow ID is rejected while the server still retains the old run.

A client that connects with only the CA and no client certificate must fail,
even through a working port-forward.

## Troubleshooting

- **Schema errors**: in the approved environment, inspect the failed Helm hook
  Job and the CA and Secret references it actually mounted. The application
  login must own both databases. Don't blindly retry a failed migration or
  bypass TLS. Keep logs private, because they can contain operational
  identifiers.
- **TLS errors**: check CA chains, EKUs, expiry dates and the server SAN.
  Namespace creation uses the server certificate as a client, so it needs both
  EKUs. There's no plaintext frontend or internal-frontend bypass.
- **Networking errors**: check private API access, the selected pod or node
  security group, the database subnets and CNI policy enforcement. If you use
  NodeLocal DNS, adapt the DNS policy to your verified resolver path before
  deploying. A proxy, Tailscale operator, cluster runner or public exposure
  isn't part of this application.

## Limitations and maintenance

- The `billing` namespace keeps closed workflows for three days. The official
  namespace hook won't change retention on an existing namespace; that needs an
  attended native Temporal operator update.
- Never change the history shard count after the database is first created.
- Credential and schema updates need a maintenance window. Changing bootstrap
  inputs replaces the Job, and credential changes roll the server and worker pods.
- This walkthrough covers one invoice workflow. Plan rolling upgrades, backup,
  restore and capacity separately before using it for important workloads.

## Costs

The RDS instance, storage, backups and any retained snapshots cost money. So do
your existing EKS cluster, nodes, NAT and registry storage. Check current
`us-east-2` pricing for your platform before deploying; no fixed cost estimate
is given here. AWS Budgets send alerts but don't stop spending.

## Cleanup

RDS deletion protection and Pulumi protection are on by default. To remove the
example on purpose:

1. Stop the worker and decide what should happen to the data.
2. Leave the existing cluster alone.
3. For a final snapshot, set a unique `finalSnapshotIdentifier`. To delete a
   disposable install without a final snapshot, also set
   `retainFinalSnapshot=false` explicitly.

```sh
kubectl -n "$namespace" scale deployment/invoice-worker --replicas=0
pulumi config set protectData false
# Optional, only after authorizing disposal of this example's data:
pulumi config set retainFinalSnapshot false
pulumi preview --refresh --diff
pulumi up
pulumi destroy
```

The `pulumi up` before destroy clears RDS and Pulumi protection. Helm uninstall
removes the chart resources, and deleting the Kubernetes namespace removes its
Secrets and Jobs. Temporal namespace records and history stay in RDS until the
database is deleted, or inside a retained final snapshot.

Afterwards, check what's left yourself: RDS resources, snapshots and backups,
the security group and its rule, subnet and parameter groups, the namespace,
Helm resources, temporary registry images and any port-forward processes.
Clear retained billable objects before removing the encrypted state. Never
delete the existing cluster, node group, VPC or operator credentials.

## Attribution and license

Temporal Server, the official Helm charts and the Python SDK come from Temporal
Technologies under the MIT License. See `UPSTREAM-NOTICES.md` and `licenses/`.
AWS distributes the regional RDS trust bundle. Python, PostgreSQL, uv and the
wheel dependencies keep their licenses in their upstream distributions and
images.

This example's authored code is licensed under the [MIT License](LICENSE) and
is provided as-is, without warranty or a support commitment. Third-party
components keep their own licenses and notices.

## Contributing

Report problems through this repository's Issues and propose changes with pull
requests. Never post credentials, state or private logs. Report sensitive
security findings privately to the repository administrators.
