#!/usr/bin/env bash
#
# Generate an RS256 signing keypair for OpenG2P detached-JWS signing.
#
# Produces, for <name>:
#   <name>.p12       PKCS#12 keystore = private key + self-signed cert, password-protected.
#                    THE PRIVATE KEY. Mount via a Secret; never commit a real one.
#   <name>.crt       X.509 public certificate (PEM). PUBLIC — give to the counterparty
#                    to onboard into their partner_keys table (seed value / admin API).
#   <name>.key.pem   PEM private key. Only for tools that cannot read PKCS#12 (e.g. Postman).
#
# Algorithm is RS256 (RSA-2048) — the only algorithm the Bridge/SPAR accept.
#
# Usage: generate-signing-keypair.sh <name> <p12-password> [common-name] [days]
set -euo pipefail
NAME="${1:?usage: $0 <name> <p12-password> [common-name] [days]}"
PASS="${2:?p12 password required (store it in a Secret, not in source)}"
CN="${3:-$NAME}"; DAYS="${4:-3650}"
command -v openssl >/dev/null 2>&1 || { echo "openssl not found" >&2; exit 1; }
openssl req -x509 -newkey rsa:2048 -sha256 -keyout "${NAME}.key.pem" -out "${NAME}.crt" \
  -days "${DAYS}" -nodes -subj "/CN=${CN}" >/dev/null 2>&1
openssl pkcs12 -export -inkey "${NAME}.key.pem" -in "${NAME}.crt" \
  -out "${NAME}.p12" -passout "pass:${PASS}" -name "${CN}" >/dev/null 2>&1
chmod 600 "${NAME}.p12" "${NAME}.key.pem"
echo "Wrote ${NAME}.p12 (private), ${NAME}.crt (public cert), ${NAME}.key.pem (PEM private)."
