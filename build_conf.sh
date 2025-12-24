#!/bin/sh
set -eu

DOCKER_DEMO_REPO="/Users/mca/Documents/work/projets/betagouv/repo/element-docker-demo"
SYNAPSE_DATA=$(pwd)
OUT="homeserver.yaml"
OUT2="log_config.yaml"

# 1/7 Copy the base homeserver.yaml
cp docs/sample_config.yaml "$OUT"
cp docs/sample_log_config.yaml "$OUT2"

# 2/7 Merge $DOCKER_DEMO_REPO configuration into the base (overlays)
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' "$OUT" "$DOCKER_DEMO_REPO/data/synapse/homeserver.yaml" -i

# 3/7 Force SQLite with a configurable path
yq eval -i ".database = {\"name\":\"sqlite3\",\"args\":{\"database\":\"${SYNAPSE_DATA}/data/sqlite3/homeserver.db\"}}" "$OUT"

# 4/7 Force paths relative to SYNAPSE_DATA
yq eval -i ".pid_file = \"${SYNAPSE_DATA}/data/homeserver.pid\"" "$OUT"
yq eval -i ".log_config = \"${SYNAPSE_DATA}/log_config.yaml\"" "$OUT"
yq eval -i ".media_store_path = \"${SYNAPSE_DATA}/data/media_store\"" "$OUT"
yq eval -i ".signing_key_path = \"${SYNAPSE_DATA}/data/tchapgouv.com.signing.key\"" "$OUT"

# 5/7 Add bind_addresses to the main listener
yq eval -i '.listeners[0].bind_addresses = ["::1","127.0.0.1"]' "$OUT"

# 6/7 Unused configuration
yq eval -i 'del(.instance_map)' "$OUT"
yq eval -i 'del(.redis)' "$OUT"
yq eval -i 'del(.background_updates)' "$OUT"
yq eval -i '.send_federation = false' "$OUT"
yq eval -i '.report_stats = false' "$OUT"
yq eval -i '.suppress_key_server_warning = true' "$OUT"

echo "==> homeserver.yaml generated!"

# 7/7 Build log_config.yaml
yq eval -i ".handlers.file.filename = \"${SYNAPSE_DATA}/data/homeserver.log\"" "$OUT2"

echo "==> log_config.yaml generated!"
