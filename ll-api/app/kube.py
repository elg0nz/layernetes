"""Kubernetes access: LLAgent CRs and Secrets, all in the platform namespace.

RBAC only grants llagents(+status) and secrets in PLATFORM_NAMESPACE, so
nothing here goes wider. age keypairs are generated with pyrage when
available, falling back to the age-keygen binary.
"""

import base64
import hashlib
import re
import subprocess
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

GROUP = "layernetes.learninglayer.ai"
VERSION = "v1alpha1"
PLURAL = "llagents"
PUBLIC_KEY_ANNOTATION = "layernetes.learninglayer.ai/public-key"
AGE_KEY_DATA_KEY = "age.key"

# RFC 1123 *label*: lowercase alphanumeric or '-', must start and end with an
# alphanumeric, at most 63 characters. We target the label form (not the more
# permissive subdomain, which allows dots and 253 chars) because the operator
# embeds the CR name in a namespace name -- `agent-<cr-name>` -- and namespace
# names are RFC 1123 labels: no dots, <= 63 chars.
_RFC1123_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?")
_K8S_NAME_INVALID = re.compile(r"[^a-z0-9-]+")
_MAX_LABEL_LEN = 63


def is_valid_k8s_name(value: str) -> bool:
    """Whether ``value`` is already a valid RFC 1123 label usable as a K8s name."""
    return (
        bool(value)
        and len(value) <= _MAX_LABEL_LEN
        and _RFC1123_LABEL.fullmatch(value) is not None
    )


def k8s_name(value: str) -> str:
    """Coerce an arbitrary identifier (e.g. a Gitea username) into a valid K8s name.

    Kubernetes object names must be lowercase RFC 1123 labels, which forbid
    ``_`` and every other non-``[a-z0-9-]`` character -- but Gitea usernames
    are far more permissive (``learninglayer_glo``, unicode, dots, ...). Any
    username that becomes part of a resource *name* (the per-user age-key
    Secret, the LLAgent CR, its derived Secrets, the agent namespace) is run
    through this. The raw username is still stored in the CR's ``spec.owner``
    for authorization and used verbatim for Gitea repo / OCI registry paths,
    which permit ``_``.

    The result is always a valid label:
    - every character outside ``[a-z0-9-]`` (after lowercasing) becomes ``-``;
    - runs of ``-`` collapse and leading/trailing ``-`` are trimmed;
    - names longer than 63 chars are truncated with an 8-char hash suffix;
    - a value that reduces to empty (all punctuation) gets a stable hash name.

    Truncation and character folding are lossy, so distinct usernames *can*
    collapse to one name; a hash suffix is appended on truncation to keep long
    names distinct. For the MVP's curated, admin-provisioned usernames this is
    not a concern, but callers minting names from untrusted input should be
    aware.
    """
    if is_valid_k8s_name(value):
        return value
    safe = _K8S_NAME_INVALID.sub("-", value.lower())
    safe = re.sub(r"-{2,}", "-", safe).strip("-")
    if len(safe) > _MAX_LABEL_LEN:
        digest = hashlib.sha256(value.encode()).hexdigest()[:8]
        safe = f"{safe[: _MAX_LABEL_LEN - 9].rstrip('-')}-{digest}"
    if not safe:
        safe = "u-" + hashlib.sha256(value.encode()).hexdigest()[:8]
    return safe


def generate_age_keypair() -> tuple[str, str]:
    """Return (public_key, age identity file content)."""
    try:
        from pyrage import x25519
    except ImportError:
        out = subprocess.run(["age-keygen"], capture_output=True, text=True, check=True)
        public = _public_key_from_identity_file(out.stdout)
        if not public:
            raise RuntimeError("age-keygen output had no '# public key:' line")
        return public, out.stdout
    identity = x25519.Identity.generate()
    public = str(identity.to_public())
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return public, f"# created: {created}\n# public key: {public}\n{identity}\n"


def _public_key_from_identity_file(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("# public key:"):
            return line.split(":", 1)[1].strip()
    return None


class Kube:
    def __init__(self, namespace: str, core=None, custom=None):
        if core is None or custom is None:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
        self.namespace = namespace
        self.core = core or client.CoreV1Api()
        self.custom = custom or client.CustomObjectsApi()

    # -- Secrets ---------------------------------------------------------------

    def get_secret(self, name: str):
        try:
            return self.core.read_namespaced_secret(name, self.namespace)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    @staticmethod
    def secret_value(secret, key: str) -> str | None:
        data = secret.data or {}
        if key not in data:
            return None
        return base64.b64decode(data[key]).decode()

    def create_secret(self, name: str, data: dict[str, str], annotations: dict | None = None) -> None:
        """Create a Secret; a 409 (already exists) is swallowed."""
        body = client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=name,
                annotations=annotations or None,
                labels={"app.kubernetes.io/managed-by": "ll-api"},
            ),
            string_data=data,
        )
        try:
            self.core.create_namespaced_secret(self.namespace, body)
        except ApiException as exc:
            if exc.status != 409:
                raise

    def delete_secret(self, name: str) -> None:
        try:
            self.core.delete_namespaced_secret(name, self.namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise

    # -- age keys ----------------------------------------------------------------

    def get_age_public_key(self, username: str) -> str | None:
        """Read-only lookup of the user's age public key; None if never provisioned."""
        secret = self.get_secret(f"age-key-{k8s_name(username)}")
        if secret is None:
            return None
        public = (secret.metadata.annotations or {}).get(PUBLIC_KEY_ANNOTATION)
        if public:
            return public
        # Older/hand-made Secrets: recover it from the identity file comments.
        return _public_key_from_identity_file(self.secret_value(secret, AGE_KEY_DATA_KEY) or "")

    def ensure_age_key(self, username: str) -> str:
        """Return the user's age public key, generating and storing a keypair if needed."""
        public = self.get_age_public_key(username)
        if public:
            return public
        secret_name = f"age-key-{k8s_name(username)}"
        if self.get_secret(secret_name) is not None:
            raise RuntimeError(f"secret {secret_name} exists but its public key is unrecoverable")
        public, identity_file = generate_age_keypair()
        self.create_secret(
            secret_name,
            {AGE_KEY_DATA_KEY: identity_file},
            annotations={PUBLIC_KEY_ANNOTATION: public},
        )
        return public

    # -- LLAgent CRs --------------------------------------------------------------

    def get_llagent(self, name: str) -> dict | None:
        try:
            return self.custom.get_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, name)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def create_llagent(self, name: str, spec: dict) -> None:
        """Create an LLAgent CR; a 409 (already exists) is swallowed."""
        body = {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "LLAgent",
            "metadata": {"name": name, "namespace": self.namespace},
            "spec": spec,
        }
        try:
            self.custom.create_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, body)
        except ApiException as exc:
            if exc.status != 409:
                raise

    def patch_llagent_spec(self, name: str, spec_patch: dict) -> None:
        self.custom.patch_namespaced_custom_object(
            GROUP, VERSION, self.namespace, PLURAL, name, {"spec": spec_patch}
        )

    def delete_llagent(self, name: str) -> None:
        try:
            self.custom.delete_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, name)
        except ApiException as exc:
            if exc.status != 404:
                raise
