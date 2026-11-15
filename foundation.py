"""Owned AWS persistence and Kubernetes bootstrap resources."""

from hashlib import sha256
from typing import Final

import pulumi
import pulumi_aws as aws
import pulumi_kubernetes as k8s

from settings import (
    APP_PASSWORD, CA, CFG, MASTER_PASSWORD, NAMESPACE, PINS, PLATFORM,
    PROTECT_DATA, RETAIN_SNAPSHOT, ROOT,
)

AWS: Final = aws.Provider(
    "aws", region="us-east-2", allowed_account_ids=[PLATFORM.account_id],
    default_tags={"tags": {
        "pulumi-stack": pulumi.get_stack(), "pulumi-project": pulumi.get_project(),
    }},
)
AWS_OPTIONS: Final = pulumi.ResourceOptions(provider=AWS)
KUBE: Final = k8s.Provider("eks", kubeconfig=CFG.require_secret("kubeconfig"))
KUBE_OPTIONS: Final = pulumi.ResourceOptions(provider=KUBE)
NS: Final = k8s.core.v1.Namespace(
    "namespace", metadata={"name": NAMESPACE}, opts=KUBE_OPTIONS,
)
SA: Final = k8s.core.v1.ServiceAccount(
    "application", metadata={"namespace": NS.metadata.name, "name": "temporal"},
    automount_service_account_token=False, opts=KUBE_OPTIONS,
)
GROUP: Final = aws.ec2.SecurityGroup(
    "database", name_prefix=f"{NAMESPACE}-", vpc_id=PLATFORM.vpc_id,
    description="Temporal PostgreSQL from selected EKS node security group",
    opts=AWS_OPTIONS,
)
# Standalone ingress rule is the only rule owner; no inline rule collection.
RULE: Final = aws.vpc.SecurityGroupIngressRule(
    "database-from-nodes", security_group_id=GROUP.id,
    referenced_security_group_id=PLATFORM.node_security_group_id,
    ip_protocol="tcp", from_port=5432, to_port=5432, opts=AWS_OPTIONS,
)
SUBNETS: Final = aws.rds.SubnetGroup(
    "database", name_prefix=f"{NAMESPACE}-",
    subnet_ids=PLATFORM.private_subnet_ids, opts=AWS_OPTIONS,
)
PARAMETERS: Final = aws.rds.ParameterGroup(
    "database", name_prefix=f"{NAMESPACE}-", family="postgres15",
    parameters=[aws.rds.ParameterGroupParameterArgs(
        name="rds.force_ssl", value="1", apply_method="immediate",
    )],
    opts=AWS_OPTIONS,
)
DATABASE: Final = aws.rds.Instance(
    "database", identifier=f"{NAMESPACE}-db",
    engine="postgres", engine_version="15.18",
    instance_class="db.t4g.micro", allocated_storage=20, storage_type="gp3",
    storage_encrypted=True, username="temporal_admin", password=MASTER_PASSWORD,
    db_subnet_group_name=SUBNETS.name, vpc_security_group_ids=[GROUP.id],
    parameter_group_name=PARAMETERS.name, publicly_accessible=False,
    multi_az=False, backup_retention_period=7, auto_minor_version_upgrade=False,
    deletion_protection=PROTECT_DATA, skip_final_snapshot=not RETAIN_SNAPSHOT,
    final_snapshot_identifier=CFG.get("finalSnapshotIdentifier") or f"{NAMESPACE}-final",
    delete_automated_backups=True,
    opts=pulumi.ResourceOptions(provider=AWS, protect=PROTECT_DATA),
)
MASTER: Final = k8s.core.v1.Secret(
    "database-master", metadata={"name": "db-master", "namespace": NS.metadata.name},
    string_data={"password": MASTER_PASSWORD}, opts=KUBE_OPTIONS,
)
APPLICATION: Final = k8s.core.v1.Secret(
    "database-application", metadata={"name": "db-app", "namespace": NS.metadata.name},
    string_data={"password": APP_PASSWORD}, opts=KUBE_OPTIONS,
)
SERVER_TLS_DATA: Final = {
    "ca.crt": CFG.require_secret("tlsCaCertificate"),
    "tls.crt": CFG.require_secret("tlsServerCertificate"),
    "tls.key": CFG.require_secret("tlsServerPrivateKey"),
}
SERVER_TLS: Final = k8s.core.v1.Secret(
    "server-tls", metadata={"name": "tls-server", "namespace": NS.metadata.name},
    type="kubernetes.io/tls",
    string_data=SERVER_TLS_DATA, opts=KUBE_OPTIONS,
)
CLIENT_TLS_DATA: Final = {
    "ca.crt": CFG.require_secret("tlsCaCertificate"),
    "tls.crt": CFG.require_secret("tlsClientCertificate"),
    "tls.key": CFG.require_secret("tlsClientPrivateKey"),
}
CLIENT_TLS: Final = k8s.core.v1.Secret(
    "client-tls", metadata={"name": "tls-client", "namespace": NS.metadata.name},
    type="kubernetes.io/tls",
    string_data=CLIENT_TLS_DATA, opts=KUBE_OPTIONS,
)
CONFIG: Final = k8s.core.v1.ConfigMap(
    "database-bootstrap", metadata={"name": "db-bootstrap", "namespace": NS.metadata.name},
    data={"rds-ca.pem": CA.read_text(),
          "bootstrap.sql": (ROOT / "config" / "bootstrap.sql").read_text()},
    opts=KUBE_OPTIONS,
)
POLICY: Final = k8s.networking.v1.NetworkPolicy(
    "namespace-boundary", metadata={"namespace": NS.metadata.name},
    spec={
        "podSelector": {}, "policyTypes": ["Ingress", "Egress"],
        "ingress": [{"from": [{"podSelector": {}}]}],
        "egress": [
            {"to": [{"podSelector": {}}]},
            {"to": [{"namespaceSelector": {"matchLabels": {
                "kubernetes.io/metadata.name": "kube-system"}}}],
             "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
            {"to": [{"ipBlock": {"cidr": str(cidr)}}
                    for cidr in PLATFORM.database_subnet_cidrs],
             "ports": [{"protocol": "TCP", "port": 5432}]},
        ],
    }, opts=KUBE_OPTIONS,
)
BOOTSTRAP: Final = k8s.batch.v1.Job(
    "database-bootstrap",
    metadata={"namespace": NS.metadata.name, "name": "database-bootstrap"},
    spec={
        "backoffLimit": 0, "activeDeadlineSeconds": 300,
        "template": {"metadata": {
            "labels": {"app": "database-bootstrap"},
            "annotations": {"bootstrap/input-version": pulumi.Output.concat(
                MASTER_PASSWORD, ":", APP_PASSWORD, ":",
                (ROOT / "config" / "bootstrap.sql").read_text(encoding="utf-8"),
                ":", CA.read_text(encoding="utf-8"),
            ).apply(lambda content: sha256(content.encode("utf-8")).hexdigest())}},
            "spec": {
                "serviceAccountName": SA.metadata.name, "restartPolicy": "Never",
                "nodeSelector": PLATFORM.node_selector,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 1000,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{
                    "name": "bootstrap", "image": PINS.images.postgres,
                    "command": ["psql", "-X", "-v", "ON_ERROR_STOP=1",
                                "-f", "/config/bootstrap.sql"],
                    "env": [
                        {"name": "PGHOST", "value": DATABASE.address},
                        {"name": "PGPORT", "value": "5432"},
                        {"name": "PGDATABASE", "value": "postgres"},
                        {"name": "PGUSER", "value": "temporal_admin"},
                        {"name": "PGSSLMODE", "value": "verify-full"},
                        {"name": "PGSSLROOTCERT", "value": "/config/rds-ca.pem"},
                        {"name": "PGPASSWORD", "valueFrom": {"secretKeyRef": {
                            "name": MASTER.metadata.name, "key": "password"}}},
                        {"name": "TEMPORAL_DB_PASSWORD", "valueFrom": {"secretKeyRef": {
                            "name": APPLICATION.metadata.name, "key": "password"}}},
                    ],
                    "resources": {"requests": {"cpu": "50m", "memory": "64Mi"},
                                  "limits": {"cpu": "250m", "memory": "128Mi"}},
                    "securityContext": {"allowPrivilegeEscalation": False,
                                        "capabilities": {"drop": ["ALL"]}},
                    "volumeMounts": [{"name": "config", "mountPath": "/config", "readOnly": True}],
                }],
                "volumes": [{"name": "config", "configMap": {"name": CONFIG.metadata.name}}],
            }},
    }, opts=pulumi.ResourceOptions(
        provider=KUBE, depends_on=[RULE, POLICY], delete_before_replace=True,
        replace_on_changes=["spec.template"],
    ),
)
