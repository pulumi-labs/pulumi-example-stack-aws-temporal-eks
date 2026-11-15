"""Export only nonsecret application coordinates."""

import pulumi

from foundation import DATABASE
from services import RELEASE, WORKER
from settings import NAMESPACE

pulumi.export("namespace", NAMESPACE)
pulumi.export("temporalNamespace", "billing")
pulumi.export("frontendService", f"temporal-frontend.{NAMESPACE}.svc:7233")
pulumi.export("databaseIdentifier", DATABASE.identifier)
pulumi.export("helmRelease", RELEASE.name)
pulumi.export("workerDeployment", WORKER.metadata.name)
