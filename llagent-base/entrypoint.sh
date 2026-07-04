#!/bin/sh
# LLAgent entrypoint: decrypt credentials in-memory via sops exec-env, then
# start the server. Plaintext secrets never touch disk - `sops exec-env`
# decrypts keys.env and passes the values to the child process's environment
# only.
set -eu

export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-/var/run/secrets/llnate/age.key}"

CMD="uvicorn server:app --host 0.0.0.0 --port 8000"

if [ -f /app/keys.env ] && [ -f "$SOPS_AGE_KEY_FILE" ]; then
    echo "entrypoint: decrypting /app/keys.env with sops exec-env (age key: $SOPS_AGE_KEY_FILE)" >&2
    exec sops exec-env /app/keys.env "$CMD"
else
    echo "entrypoint: no keys.env or age key found; starting without sops (keys.env: $( [ -f /app/keys.env ] && echo present || echo missing ), age key: $( [ -f "$SOPS_AGE_KEY_FILE" ] && echo present || echo missing ))" >&2
    exec $CMD
fi
