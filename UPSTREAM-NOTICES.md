# Upstream attribution

The Temporal Helm chart 1.8.0 is acquired unmodified from Temporal Technologies:
https://github.com/temporalio/helm-charts/tree/temporal-1.8.0

Temporal Server/admin-tools 1.32.2:
https://github.com/temporalio/temporal/tree/v1.32.2

Temporal Python SDK 1.18.1:
https://github.com/temporalio/sdk-python/tree/1.18.1

These projects use the MIT license. Their reviewed license texts are preserved
in `licenses/`. The chart archive and images retain their own notices.
No upstream application source or sample is copied into the authored worker.
Helm configuration uses the chart's documented keys and native schema paths.

`config/rds-ca.pem` is the AWS `us-east-2` RDS trust bundle, byte-identical to
the reviewed existing example's bundle. Canonical distribution:
https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem
SHA-256: `d46e1bdfda05c8e7644e50930806a19b139a222542bf0348082fb59ece2b5fa5`.
This public certificate bundle is trust material, not an application secret.

Python container base uses the Python Software Foundation license and bundled
Debian package licenses. PostgreSQL uses the PostgreSQL License. uv uses
Apache-2.0/MIT; its distributed image carries upstream notices. Pydantic,
AnyIO, annotated-types, typing-inspection, Temporal/Nexus SDK dependencies,
protobuf/type stubs, idna, sniffio and typing-extensions retain the licenses
within their exact wheel distributions. Full binary/package notice coverage
must be reconciled when primary acquires/scans these artifacts.

Authored infrastructure, application, acceptance and documentation files have
no selected license. Upstream MIT texts do not license those authored files.
Public release remains blocked on owner approval of licensing and maintenance.
