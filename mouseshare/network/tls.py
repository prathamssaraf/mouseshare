"""
TLS certificate management.

On first run, generates a self-signed RSA-2048 certificate and private key,
stored in ~/.mouseshare/certs/.  Both server and client load the same cert
(the server's cert is trusted by the client after fingerprint verification).

Fingerprint workflow:
  1. Server displays its cert fingerprint (SHA-256 hex) in the UI.
  2. User manually confirms the fingerprint matches on the client side
     (one-time, shown as a short 8-char prefix for readability).
  3. Fingerprint is saved to config and checked on every subsequent connection.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from mouseshare.constants import APP_NAME, CERT_DAYS_VALID, CERT_FILE, KEY_FILE

log = logging.getLogger(__name__)


def _cert_paths(cert_dir: Path) -> tuple[Path, Path]:
    return cert_dir / CERT_FILE, cert_dir / KEY_FILE


def generate_cert(cert_dir: Path) -> None:
    """Generate a self-signed TLS certificate + private key if not present."""
    cert_path, key_path = _cert_paths(cert_dir)
    if cert_path.exists() and key_path.exists():
        return

    log.info("Generating self-signed TLS certificate in %s", cert_dir)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    hostname = socket.gethostname()
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"{APP_NAME}-{hostname}"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, APP_NAME),
    ])

    now = datetime.now(timezone.utc)
    san_list: list[x509.GeneralName] = [x509.DNSName(hostname), x509.DNSName("localhost")]

    # Add local IP addresses to SAN so TLS validation works on LAN
    try:
        local_ip = socket.gethostbyname(hostname)
        san_list.append(x509.IPAddress(ipaddress.ip_address(local_ip)))
    except Exception:
        pass
    san_list.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=CERT_DAYS_VALID))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    # Restrict permissions on private key
    if sys.platform != "win32":
        key_path.chmod(0o600)

    log.info("TLS certificate generated: %s", cert_path)


def get_fingerprint(cert_dir: Path) -> str:
    """Return SHA-256 fingerprint (hex) of our certificate."""
    cert_path, _ = _cert_paths(cert_dir)
    der = ssl.PEM_cert_to_DER_cert(cert_path.read_text())
    return hashlib.sha256(der).hexdigest().upper()


def short_fingerprint(cert_dir: Path) -> str:
    """8-character prefix of fingerprint — shown in UI for quick verification."""
    return get_fingerprint(cert_dir)[:8]


def server_ssl_context(cert_dir: Path) -> ssl.SSLContext:
    """Return an SSLContext for the server (presents our certificate)."""
    cert_path, key_path = _cert_paths(cert_dir)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    # Do not require client cert — we do manual fingerprint verification
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def client_ssl_context() -> ssl.SSLContext:
    """Return an SSLContext for the client (does not verify server cert — we do fingerprint)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def verify_peer_fingerprint(writer: "asyncio.StreamWriter", expected: str) -> bool:
    """
    Verify the TLS peer's certificate fingerprint against the stored expected value.
    Returns True if it matches (or if no expected fingerprint is configured yet).
    """
    if not expected:
        return True  # first connection — trust on first use (TOFU)
    ssl_obj = writer.get_extra_info("ssl_object")
    if ssl_obj is None:
        return False
    der = ssl_obj.getpeercert(binary_form=True)
    if der is None:
        return False
    actual = hashlib.sha256(der).hexdigest().upper()
    return actual == expected.upper()
