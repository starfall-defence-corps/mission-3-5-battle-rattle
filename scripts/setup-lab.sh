#!/usr/bin/env bash
# =============================================================================
# setup-lab.sh — MOS 5 "Battle Rattle"
#
# Brings up 3 fleet nodes + an opaque range/injector (sdc-range) and ARMS two
# independent, randomised incident scenarios for EACH of the four IR verbs:
#
#   block-ioc      two attacker source IPs on the range (A/B)
#   collect-triage two evidence logs per node, disjoint indicator IPs (A/B)
#   rotate-creds   two compromised local users per node, known old secrets (A/B)
#   restore-service two scored systemd services per node + a known-good store (A/B)
#
# All nonces are random per run (see the reserved ranges below), so nothing is
# guessable or hardcodable. Ground truth lands in the gitignored .lab/baseline.json
# that the grader reads. The grader runs the cadet's SAME runbook against BOTH
# scenarios of a verb, in one lab pass — a hardcoded solution passes one, fails
# the other. See docs/BRIEFING.md.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$ROOT_DIR/.docker"
SSH_DIR="$DOCKER_DIR/ssh-keys"
LAB_DIR="$ROOT_DIR/.lab"

NODES=(sdc-web sdc-db sdc-comms)
RANGE="sdc-range"
CONTROL_IP="172.30.0.20"          # the range's own address — never an IOC

echo ""
echo "=============================================="
echo "  STARFALL DEFENCE CORPS ACADEMY"
echo "  MOS 5 — Battle Rattle"
echo "  Deploying fleet + range, arming scenarios..."
echo "=============================================="
echo ""

# -- helpers -----------------------------------------------------------------
rand_hex() { openssl rand -hex "${1:-4}" 2>/dev/null || head -c "${1:-4}" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
# distinct random octet in [200,250]
rand_octet() { echo $(( 200 + RANDOM % 51 )); }
rand_count() { echo $(( 3 + RANDOM % 7 )); }   # 3..9

# -- venv --------------------------------------------------------------------
if ! python3 -m venv --help &>/dev/null; then
    echo "  ERROR: python3-venv is not installed (apt install python3-venv)."; exit 1
fi
if [ ! -d "$ROOT_DIR/venv" ]; then
    echo "  Setting up Python environment..."
    python3 -m venv "$ROOT_DIR/venv"
    "$ROOT_DIR/venv/bin/pip" install -q -r "$ROOT_DIR/requirements.txt"
    echo "  Python environment ready."; echo ""
fi

# -- ssh keys ----------------------------------------------------------------
if [ ! -f "$SSH_DIR/cadet_key" ]; then
    echo "  Generating SSH credentials..."
    mkdir -p "$SSH_DIR"
    ssh-keygen -t ed25519 -f "$SSH_DIR/cadet_key" -N "" -C "cadet@starfall-academy" -q
    cp "$SSH_DIR/cadet_key.pub" "$SSH_DIR/authorized_keys"
    chmod 600 "$SSH_DIR/cadet_key"; chmod 644 "$SSH_DIR/authorized_keys"
fi
mkdir -p "$ROOT_DIR/workspace/.ssh"
cp "$SSH_DIR/cadet_key" "$ROOT_DIR/workspace/.ssh/cadet_key"
chmod 600 "$ROOT_DIR/workspace/.ssh/cadet_key"

mkdir -p "$LAB_DIR"; chmod 777 "$LAB_DIR" 2>/dev/null || true
rm -f "$LAB_DIR/baseline.json" 2>/dev/null || true

# -- bring up ----------------------------------------------------------------
echo "  Building fleet + range images..."
docker compose -f "$DOCKER_DIR/docker-compose.yml" up -d --build 2>&1 | sed 's/^/    /'

echo ""
echo "  Waiting for the fleet's SSH..."
for node in sdc-web:2221 sdc-db:2222 sdc-comms:2223; do
    name="${node%%:*}"; port="${node##*:}"
    for i in $(seq 1 40); do
        if ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=1 \
            -i "$SSH_DIR/cadet_key" cadet@localhost -p "$port" exit 2>/dev/null; then
            echo "    $name (port $port): ONLINE"; break
        fi
        [ "$i" -eq 40 ] && echo "    $name (port $port): TIMEOUT — 'docker compose logs $name'"
        sleep 1
    done
done

echo ""
echo "  Waiting for the range ($RANGE)..."
for i in $(seq 1 40); do
    if docker exec "$RANGE" true 2>/dev/null; then echo "    Range: ONLINE"; break; fi
    [ "$i" -eq 40 ] && { echo "    ERROR: range never came up — 'docker compose logs $RANGE'."; exit 1; }
    sleep 1
done

# ===========================================================================
#  Generate this run's nonces
# ===========================================================================
RUN_ID="$(rand_hex 3)"

# block-ioc: two distinct attacker source IPs on the range
OCT_A="$(rand_octet)"; OCT_B="$(rand_octet)"
while [ "$OCT_B" = "$OCT_A" ]; do OCT_B="$(rand_octet)"; done
IOC_A="172.30.0.${OCT_A}"; IOC_B="172.30.0.${OCT_B}"

# collect-triage: disjoint indicator IPs (TEST-NET blocks) + paths + per-host counts
TRI_A_IND="203.0.113.$(( 1 + RANDOM % 250 ))"
TRI_B_IND="198.51.100.$(( 1 + RANDOM % 250 ))"
TRI_A_LOG="/var/log/sdc/inc-$(rand_hex 3).log"; TRI_A_REPORT="/var/log/sdc/triage-$(rand_hex 3).json"
TRI_B_LOG="/var/log/sdc/inc-$(rand_hex 3).log"; TRI_B_REPORT="/var/log/sdc/triage-$(rand_hex 3).json"

# rotate-creds: two compromised users with known old secrets
RC_A_USER="svc_$(rand_hex 2)"; RC_A_OLD="Old-$(rand_hex 4)"; RC_A_NEW="New-$(rand_hex 6)"
RC_B_USER="svc_$(rand_hex 2)"; RC_B_OLD="Old-$(rand_hex 4)"; RC_B_NEW="New-$(rand_hex 6)"

# restore-service: two scored services + known-good store
RS_A_SVC="sdc-svc-$(rand_hex 2)"; RS_A_PORT=18081; RS_A_TOK="TOK-$(rand_hex 5)"
RS_B_SVC="sdc-svc-$(rand_hex 2)"; RS_B_PORT=18082; RS_B_TOK="TOK-$(rand_hex 5)"
GOLDEN_ROOT="/opt/sdc/known-good"

echo ""
echo "  Arming scenarios (run ${RUN_ID})..."

# ---------------------------------------------------------------------------
#  Stage shared artefacts locally, then docker cp (clean multi-line handling)
# ---------------------------------------------------------------------------
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT

cat > "$STAGE/serve.py" <<'PY'
# SDC scored service — returns its configured token. Range infra; do not edit.
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
TOKEN = os.environ.get("SDC_TOKEN", "")
PORT = int(os.environ.get("SDC_PORT", "8080"))
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(TOKEN.encode())
    def log_message(self, *a): pass
HTTPServer(("0.0.0.0", PORT), H).serve_forever()
PY

write_unit() {  # $1=svc $2=port $3=token -> $STAGE/$1.service
    cat > "$STAGE/$1.service" <<UNIT
[Unit]
Description=SDC scored service $1
After=network.target

[Service]
Environment=SDC_TOKEN=$3
Environment=SDC_PORT=$2
ExecStart=/usr/bin/python3 /opt/sdc/serve.py
Restart=no

[Install]
WantedBy=multi-user.target
UNIT
}
write_unit "$RS_A_SVC" "$RS_A_PORT" "$RS_A_TOK"
write_unit "$RS_B_SVC" "$RS_B_PORT" "$RS_B_TOK"

# Build a per-host evidence log: N alert lines naming the indicator + 2 decoys.
write_evlog() {  # $1=out $2=indicator $3=count
    : > "$1"
    for n in $(seq 1 "$3"); do
        echo "2026-09-01T0${n}:00:00 sdc ALERT sshd[$((1000+n))]: Failed password for invalid user root src=$2 port=54321" >> "$1"
    done
    echo "2026-09-01T00:00:01 sdc ALERT sshd[999]: Failed password for invalid user admin src=192.0.2.7 port=41000" >> "$1"
    echo "2026-09-01T00:00:02 sdc ALERT sshd[998]: Failed password for invalid user test src=192.0.2.9 port=41002" >> "$1"
}

# ---------------------------------------------------------------------------
#  Plant per-node state
# ---------------------------------------------------------------------------
declare -A TRI_A_HITS TRI_B_HITS
armed_ok=1
for node in "${NODES[@]}"; do
    # -- restore-service: golden store + installed units, healthy at setup ----
    docker exec "$node" mkdir -p /opt/sdc "$GOLDEN_ROOT" /etc/sdc
    docker cp "$STAGE/serve.py" "$node:/opt/sdc/serve.py"
    for svc in "$RS_A_SVC" "$RS_B_SVC"; do
        docker cp "$STAGE/$svc.service" "$node:$GOLDEN_ROOT/$svc.service"
        docker exec "$node" cp "$GOLDEN_ROOT/$svc.service" "/etc/systemd/system/$svc.service"
    done
    docker exec "$node" systemctl daemon-reload
    docker exec "$node" systemctl enable --now "$RS_A_SVC" "$RS_B_SVC" >/dev/null 2>&1 || armed_ok=0

    # -- rotate-creds: two compromised users with known old passwords ---------
    for pair in "$RC_A_USER:$RC_A_OLD" "$RC_B_USER:$RC_B_OLD"; do
        u="${pair%%:*}"; pw="${pair##*:}"
        docker exec "$node" bash -c "id $u >/dev/null 2>&1 || useradd -m -s /bin/bash $u"
        docker exec "$node" bash -c "echo '$u:$pw' | chpasswd"
    done

    # -- collect-triage: per-node evidence logs (disjoint counts) -------------
    docker exec "$node" mkdir -p /var/log/sdc
    ca="$(rand_count)"; cb="$(rand_count)"
    TRI_A_HITS[$node]="$ca"; TRI_B_HITS[$node]="$cb"
    write_evlog "$STAGE/evA_$node" "$TRI_A_IND" "$ca"; docker cp "$STAGE/evA_$node" "$node:$TRI_A_LOG"
    write_evlog "$STAGE/evB_$node" "$TRI_B_IND" "$cb"; docker cp "$STAGE/evB_$node" "$node:$TRI_B_LOG"
    # read-only canary — recon must not mutate the host
    docker exec "$node" bash -c "echo 'canary-$RUN_ID' > /etc/sdc/canary"

    echo "    ${node}: services up, users seeded, evidence planted (A:${ca} B:${cb} alerts)"
done

# -- block-ioc: add the two attacker source IPs on the range -----------------
IFACE="$(docker exec "$RANGE" sh -c "ip -o -4 route show to default | awk '{print \$5}' | head -1")"
[ -n "$IFACE" ] || IFACE="eth0"
docker exec "$RANGE" ip addr add "${IOC_A}/24" dev "$IFACE" 2>/dev/null || true
docker exec "$RANGE" ip addr add "${IOC_B}/24" dev "$IFACE" 2>/dev/null || true
docker cp "$STAGE/serve.py" "$RANGE:/opt/sdc-serve.py" 2>/dev/null || true
echo "    ${RANGE}: attacker source IPs armed (${IOC_A}, ${IOC_B}) on ${IFACE}"

[ "$armed_ok" -eq 1 ] || { echo "  ERROR: a scored service failed to start — 'make reset'."; exit 1; }

# ===========================================================================
#  Record baseline.json (grader ground truth — gitignored)
# ===========================================================================
python3 - > "$LAB_DIR/baseline.json" <<PY
import json
def hits(m):
    return {"sdc-web": ${TRI_A_HITS[sdc-web]:-0}, "sdc-db": ${TRI_A_HITS[sdc-db]:-0}, "sdc-comms": ${TRI_A_HITS[sdc-comms]:-0}} if m=="A" else \
           {"sdc-web": ${TRI_B_HITS[sdc-web]:-0}, "sdc-db": ${TRI_B_HITS[sdc-db]:-0}, "sdc-comms": ${TRI_B_HITS[sdc-comms]:-0}}
data = {
  "version": 1,
  "run_id": "${RUN_ID}",
  "fleet": ["sdc-web", "sdc-db", "sdc-comms"],
  "range": "${RANGE}",
  "iface": "${IFACE}",
  "verbs": {
    "block_ioc": {
      "control_ip": "${CONTROL_IP}",
      "probe_port": 22,
      "scenario_a": {"evars": {"ioc_ip": "${IOC_A}"}},
      "scenario_b": {"evars": {"ioc_ip": "${IOC_B}"}}
    },
    "collect_triage": {
      "scenario_a": {"evars": {"evidence_log": "${TRI_A_LOG}", "report_path": "${TRI_A_REPORT}"},
                     "indicator_ip": "${TRI_A_IND}", "hits": hits("A")},
      "scenario_b": {"evars": {"evidence_log": "${TRI_B_LOG}", "report_path": "${TRI_B_REPORT}"},
                     "indicator_ip": "${TRI_B_IND}", "hits": hits("B")}
    },
    "rotate_creds": {
      "scenario_a": {"evars": {"target_user": "${RC_A_USER}", "new_password": "${RC_A_NEW}"}, "old_password": "${RC_A_OLD}"},
      "scenario_b": {"evars": {"target_user": "${RC_B_USER}", "new_password": "${RC_B_NEW}"}, "old_password": "${RC_B_OLD}"}
    },
    "restore_service": {
      "golden_root": "${GOLDEN_ROOT}",
      "scenario_a": {"evars": {"service_name": "${RS_A_SVC}", "golden_root": "${GOLDEN_ROOT}"},
                     "port": ${RS_A_PORT}, "token": "${RS_A_TOK}", "break_mode": "corrupt-unit"},
      "scenario_b": {"evars": {"service_name": "${RS_B_SVC}", "golden_root": "${GOLDEN_ROOT}"},
                     "port": ${RS_B_PORT}, "token": "${RS_B_TOK}", "break_mode": "remove-unit"}
    }
  }
}
print(json.dumps(data, indent=2))
PY

echo "    Baseline recorded: .lab/baseline.json"

echo ""
echo "=============================================="
echo "  Fleet ONLINE — and under incident."
echo ""
echo "  The Hydra has struck. Write your battle rattle:"
echo "    workspace/runbooks/block-ioc.yml"
echo "    workspace/runbooks/collect-triage.yml"
echo "    workspace/runbooks/rotate-creds.yml"
echo "    workspace/runbooks/restore-service.yml"
echo ""
echo "  Each must work for ANY indicator — ARIA runs it"
echo "  against two scenarios you cannot see."
echo ""
echo "  Start:  docs/BRIEFING.md      Verify: make test"
echo "=============================================="
echo ""
