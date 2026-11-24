"""The node's secrets from AWS Secrets Manager, read by the node itself (#253's SEV-SNP kit, validator-kit/sevsnp).

The measured disk has no AWS CLI (it carries only the Docker engine, the node image and the test images), so the node
reads its own secrets at start-up: for each of SECRETS, `<NAME>_SECRET_ARN` names a secret whose string becomes
`<NAME>` in this process only, never written anywhere, never logged. The call is Secrets Manager's GetSecretValue,
signed with the instance role's credentials from IMDSv2 (oracle/models.py's SigV4 and InstanceRoleCredentials), in the
secret's own region. A variable already set is left as it is."""

from __future__ import annotations

import datetime
import json

from .models import InstanceRoleCredentials, credentials_from_env, http_request, sigv4

# ORACLE_RPC: the RPC URL itself, a provider's key in its path (#251 v3.1 polish VP10, VP20: ORACLE_RPC_SECRET_ARN)
SECRETS = ("ORACLE_PRIVATE_KEY", "RPC_API_KEY", "MODEL_API_KEY", "ORACLE_GIT_TOKEN", "ORACLE_RPC")


class SecretError(RuntimeError):
    """A secret the node was told to read couldn't be read (the message never holds its value)."""


def get_secret(arn: str, request=http_request, credentials=None, now=None) -> str:
    parts = arn.split(":")
    if len(parts) < 7 or parts[:3] != ["arn", "aws", "secretsmanager"] or not parts[3]:
        raise SecretError(f"not a Secrets Manager ARN: {arn!r}")
    region = parts[3]
    url = f"https://secretsmanager.{region}.amazonaws.com/"
    body = json.dumps({"SecretId": arn}).encode()
    headers = {"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "secretsmanager.GetSecretValue"}
    creds = credentials() if credentials is not None else InstanceRoleCredentials(request=request)()
    signed = sigv4("POST", url, headers, body, creds, region, "secretsmanager",
                   now or datetime.datetime.now(datetime.timezone.utc))
    try:
        reply = request("POST", url, signed, body, 15.0)
    except OSError as e:
        raise SecretError(f"Secrets Manager unreachable for {arn}: {type(e).__name__}") from None
    try:
        data = json.loads(reply.body.decode() or "{}")
    except ValueError:
        data = {}
    if reply.status != 200 or "SecretString" not in data:
        kind = str(data.get("__type", "")).split("#")[-1]
        raise SecretError(f"Secrets Manager refused {arn}: HTTP {reply.status} {kind}".rstrip())
    return data["SecretString"].strip()


def resolve(env: dict, request=http_request, credentials=None) -> list:
    """Sets each SECRETS name from its `_SECRET_ARN` in `env` (in place); returns the names it set."""
    done = []
    for name in SECRETS:
        arn = (env.get(f"{name}_SECRET_ARN") or "").strip()
        if arn and not env.get(name):
            if credentials is None:
                fixed = credentials_from_env(env)
                credentials = (lambda: fixed) if fixed else InstanceRoleCredentials(request=request)
            env[name] = get_secret(arn, request, credentials)
            done.append(name)
    return done
