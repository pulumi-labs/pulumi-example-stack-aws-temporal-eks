"""Typed deployment inputs and verified local artifact boundary."""

from dataclasses import dataclass
from hashlib import sha256
from ipaddress import IPv4Network
from pathlib import Path
from typing import Annotated, Final

import pulumi
from pydantic import BaseModel, ConfigDict, Field

ROOT: Final = Path(__file__).resolve().parent
CFG: Final = pulumi.Config()


class Platform(BaseModel):
    """Existing platform coordinates supplied by its owner."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: Annotated[str, Field(pattern=r"^\d{12}$")]
    vpc_id: Annotated[str, Field(pattern=r"^vpc-[0-9a-f]+$")]
    private_subnet_ids: tuple[str, str]
    database_subnet_cidrs: tuple[IPv4Network, IPv4Network]
    node_security_group_id: Annotated[str, Field(pattern=r"^sg-[0-9a-f]+$")]
    node_selector: dict[str, str]


class ImagePins(BaseModel):
    """Reviewed upstream image references."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    server: str
    admin_tools: str
    postgres: str
    python: str
    uv: str


class Pins(BaseModel):
    """Published archive and inherited CA content hashes."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    chart_version: str
    chart_sha256: str
    rds_ca_sha256: str
    images: ImagePins


class Deployment(BaseModel):
    """Names and generated image identity at the deployment boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_prefix: Annotated[
        str, Field(max_length=32, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
    ]
    worker_image: Annotated[
        str, Field(pattern=r"^[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}$")
    ]


class DatabasePassword(BaseModel):
    """A PostgreSQL password safe for RDS and native clients."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    value: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{32,128}$")]


def parse_password(value: str) -> str:
    """Parse either independent database credential without logging it."""
    return DatabasePassword(value=value).value


@dataclass(frozen=True, slots=True)
class ArtifactMismatch(Exception):
    """Refuse a local artifact different from its reviewed bytes."""

    path: Path

    def __str__(self) -> str:
        return f"Artifact does not match its SHA-256 pin: {self.path.name}"


PLATFORM: Final = Platform.model_validate_json(CFG.require("platform"))
PINS: Final = Pins.model_validate_json((ROOT / "pins.json").read_text())
DEPLOYMENT: Final = Deployment(
    resource_prefix=CFG.get("resourcePrefix") or f"temporal-{pulumi.get_stack()}",
    worker_image=CFG.require("workerImage"),
)
NAMESPACE: Final = DEPLOYMENT.resource_prefix
WORKER_IMAGE: Final = DEPLOYMENT.worker_image
CHART: Final = ROOT / "artifacts" / f"temporal-{PINS.chart_version}.tgz"
CA: Final = ROOT / "config" / "rds-ca.pem"
for artifact, expected in ((CHART, PINS.chart_sha256), (CA, PINS.rds_ca_sha256)):
    if sha256(artifact.read_bytes()).hexdigest() != expected:
        raise ArtifactMismatch(artifact)

MASTER_PASSWORD: Final = CFG.require_secret("dbMasterPassword").apply(
    parse_password
)
APP_PASSWORD: Final = CFG.require_secret("dbAppPassword").apply(
    parse_password
)
PROTECT_DATA: Final = CFG.get_bool("protectData") is not False
RETAIN_SNAPSHOT: Final = CFG.get_bool("retainFinalSnapshot") is not False
