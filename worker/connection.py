"""Mandatory mutual TLS client configuration shared by worker and CLI."""

import os
from pathlib import Path

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import TLSConfig


async def connect() -> Client:
    """Connect to the configured private frontend with hostname verification."""
    tls = Path(os.environ.get("TEMPORAL_TLS_DIRECTORY", "/tls"))
    return await Client.connect(
        os.environ["TEMPORAL_ADDRESS"],
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "billing"),
        tls=TLSConfig(
            server_root_ca_cert=(tls / "ca.crt").read_bytes(),
            client_cert=(tls / "tls.crt").read_bytes(),
            client_private_key=(tls / "tls.key").read_bytes(),
            domain="temporal.internal",
        ),
        data_converter=pydantic_data_converter,
    )
