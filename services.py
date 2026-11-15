"""Official Temporal Helm services and independent invoice worker."""

from hashlib import sha256
from typing import Final

import pulumi
import pulumi_kubernetes as k8s

from foundation import (
    APPLICATION, BOOTSTRAP, CLIENT_TLS, CLIENT_TLS_DATA, CONFIG, DATABASE, KUBE, NS, SA,
    SERVER_TLS, SERVER_TLS_DATA,
)
from settings import APP_PASSWORD, CHART, NAMESPACE, PINS, PLATFORM, WORKER_IMAGE

TLS: Final = {
    "enabled": True, "secretName": "tls-server",
    "serverName": "temporal.internal", "requireClientAuth": True,
}
RELEASE: Final = k8s.helm.v3.Release(
    "temporal", name="temporal", namespace=NS.metadata.name,
    chart=str(CHART), version=PINS.chart_version, timeout=900,
    skip_await=False, wait_for_jobs=True, max_history=3,
    values={
        "fullnameOverride": "temporal",
        "serviceAccount": {"create": False, "name": SA.metadata.name},
        "server": {
            "replicaCount": 1,
            "image": {"repository": "temporalio/server",
                      "tag": PINS.images.server.removeprefix("temporalio/server:")},
            "nodeSelector": PLATFORM.node_selector,
            "podAnnotations": {"configuration/version": pulumi.Output.concat(
                APP_PASSWORD, ":", *SERVER_TLS_DATA.values(),
            ).apply(lambda content: sha256(content.encode("utf-8")).hexdigest())},
            "resources": {"requests": {"cpu": "100m", "memory": "256Mi"},
                          "limits": {"cpu": "1", "memory": "768Mi"}},
            "tls": {"internode": TLS, "frontend": TLS},
            "internal-frontend": {"enabled": False},
            "frontend": {"service": {"type": "ClusterIP"}},
            "additionalVolumes": [{"name": "database-ca",
                                   "configMap": {"name": CONFIG.metadata.name}}],
            "additionalVolumeMounts": [{"name": "database-ca", "mountPath": "/etc/rds",
                                       "readOnly": True}],
            "config": {
                "logLevel": "info",
                "namespaces": {"create": True, "useHelmHooks": True,
                               "namespace": [{"name": "billing", "retention": "3d"}]},
                "persistence": {
                    "defaultStore": "default", "visibilityStore": "visibility",
                    "numHistoryShards": 128,
                    "datastores": {
                        name: {"sql": {
                            "pluginName": "postgres12",
                            "databaseName": database,
                            "connectAddr": pulumi.Output.concat(DATABASE.address, ":5432"),
                            "connectProtocol": "tcp",
                            "user": "temporal", "existingSecret": APPLICATION.metadata.name,
                            "secretKey": "password", "createDatabase": False,
                            "manageSchema": True,
                            "maxConns": 5, "maxIdleConns": 5, "maxConnLifetime": "1h",
                            "tls": {"enabled": True, "enableHostVerification": True,
                                    "caFile": "/etc/rds/rds-ca.pem"},
                        }} for name, database in (
                            ("default", "temporal"), ("visibility", "temporal_visibility")
                        )
                    },
                },
            },
        },
        "admintools": {
            "enabled": False, "nodeSelector": PLATFORM.node_selector,
            "image": {"repository": "temporalio/admin-tools",
                      "tag": PINS.images.admin_tools.removeprefix("temporalio/admin-tools:")},
            "additionalVolumes": [{"name": "database-ca",
                                   "configMap": {"name": CONFIG.metadata.name}}],
            "additionalVolumeMounts": [{"name": "database-ca", "mountPath": "/etc/rds",
                                       "readOnly": True}],
        },
        "web": {"enabled": False},
        "schema": {
            "useHelmHooks": True, "backoffLimit": 0, "activeDeadlineSeconds": 600,
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                          "limits": {"cpu": "500m", "memory": "256Mi"}},
        },
    },
    opts=pulumi.ResourceOptions(provider=KUBE, depends_on=[
        BOOTSTRAP, SERVER_TLS, CLIENT_TLS,
    ]),
)
WORKER: Final = k8s.apps.v1.Deployment(
    "invoice-worker", metadata={"namespace": NS.metadata.name, "name": "invoice-worker"},
    spec={
        "replicas": 1, "selector": {"matchLabels": {"app": "invoice-worker"}},
        "template": {
            "metadata": {
                "labels": {"app": "invoice-worker"},
                "annotations": {"tls/version": pulumi.Output.concat(
                    *CLIENT_TLS_DATA.values(),
                ).apply(lambda content: sha256(content.encode("utf-8")).hexdigest())},
            },
            "spec": {
                "serviceAccountName": SA.metadata.name,
                "automountServiceAccountToken": False,
                "nodeSelector": PLATFORM.node_selector,
                "terminationGracePeriodSeconds": 45,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 1000,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{
                    "name": "worker", "image": WORKER_IMAGE,
                    "env": [
                        {"name": "TEMPORAL_ADDRESS",
                         "value": f"temporal-frontend.{NAMESPACE}.svc:7233"},
                        {"name": "TEMPORAL_NAMESPACE", "value": "billing"},
                    ],
                    "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                                  "limits": {"cpu": "500m", "memory": "384Mi"}},
                    "securityContext": {"allowPrivilegeEscalation": False,
                                        "readOnlyRootFilesystem": True,
                                        "capabilities": {"drop": ["ALL"]}},
                    "volumeMounts": [{"name": "tls", "mountPath": "/tls", "readOnly": True}],
                }],
                "volumes": [{"name": "tls", "secret": {"secretName": CLIENT_TLS.metadata.name}}],
            },
        },
    }, opts=pulumi.ResourceOptions(provider=KUBE, depends_on=[RELEASE]),
)
