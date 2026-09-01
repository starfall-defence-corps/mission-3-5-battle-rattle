---
CLASSIFICATION: LIEUTENANT COMMANDER EYES ONLY
MISSION: 3.5 — BATTLE RATTLE
DOCUMENT: EXERCISES — Phase-by-Phase Operational Instructions
---

# EXERCISES — MISSION 3.5: BATTLE RATTLE

Complete each phase in sequence. Run `make test` after each phase. Do not
advance until ARIA confirms compliance.

**Two directories, two purposes:**

- **Ansible commands** (`ansible-playbook`): Run from `workspace/` where `ansible.cfg` lives.
- **Make commands** (`make test`, `make reset`): Run from the **project root** (where the `Makefile` lives).

When a phase says "Run ARIA's Verification", return to the project root first:

```bash
cd ..        # from workspace/ back to project root
make test
cd workspace # return to workspace for the next phase
```

**A note on `make test`**: for each runbook, it arms two independent,
randomised scenarios (A and B) that you cannot see, runs your **same**
runbook against scenario A twice (once for effect, once for idempotence),
does the same against scenario B, and checks every node both times —
never trusting your inventory or your code as proof. Runbooks in this
mission are not automatically safe to re-run against a *live* fleet the way
MOS 4's telemetry role was — `block-ioc.yml` and `rotate-creds.yml` change
firewall and credential state — but `make test` re-arms and re-checks
correctly every time you run it, so re-running it as you iterate is always
safe. Use `make reset` if you want the fleet and range rebuilt from scratch
with fresh nonces.

There are exactly **four** runbooks you build in this mission, each a
standalone playbook at `workspace/runbooks/<verb>.yml`. Each already has a
`assert` task validating its required `-e` variables, and a header comment
describing exactly what "done" looks like — you replace the single `TODO`
task (or add tasks after it) with the real implementation.

---

## PHASE 0: Launch the Fleet, Confirm the Incident

> Before you write a single task, look at what the Hydra has already done.

### Step 0.1 — Preflight Check

From the **project root directory**, confirm your machine is mission-ready:

```bash
make doctor
```

This mission checks that `ansible-core` is installed **on your own
machine** — your runbooks run from your host, not from a lab-managed Python
environment.

### Step 0.2 — Start the Fleet and Arm the Incident

From the **project root directory** (not `workspace/`), run:

```bash
make setup
```

This builds the Docker containers, generates SSH credentials, starts all
three fleet nodes and the range (`sdc-range`), and arms **two** independent
scenarios for each of the four verbs — an attacker IP already reaching the
fleet, evidence logs already planted, two compromised accounts already
seeded, two services already running (ready to be broken at Phase 4). Ground
truth for grading lands in the gitignored `.lab/baseline.json` — you never
read it directly.

### Step 0.3 — Orient Yourself

Everything you write lives in `workspace/runbooks/`. Take a look at what's
already scaffolded for you:

```bash
cd workspace
cat ansible.cfg
cat inventory/hosts.yml
cat runbooks/block-ioc.yml
cat runbooks/collect-triage.yml
cat runbooks/rotate-creds.yml
cat runbooks/restore-service.yml
```

Each file is a complete, runnable playbook already — it just asserts its
`-e` variables and then leaves a single `debug` task in place of the real
work. Nothing else in `workspace/` needs to change; you never touch the
inventory or `ansible.cfg`.

### Step 0.4 — Confirm the Fleet Is Actually Under Incident

SSH into a node and see the Hydra's handiwork for yourself:

```bash
make ssh-web
sudo iptables -L INPUT -n     # no drop rule for the attacker yet
id svc_xxxx 2>/dev/null       # a compromised account exists (name varies per run)
exit
```

### Step 0.5 — If Things Go Wrong

If containers are in a bad state, or you need a clean start with fresh
nonces at any point:

```bash
make reset
```

This destroys and rebuilds the fleet and range. Your work in
`workspace/runbooks/` is preserved — only the lab state is reset.

---

## PHASE 1: Block the Indicator

> Contain first. The attacker is already reaching the fleet — every second
> you spend elsewhere is a second they keep working.

### What You Are Building

Fill in `workspace/runbooks/block-ioc.yml`.

### Step 1.1 — Understand the Objective

- Drop **all** traffic from `{{ ioc_ip }}` on every node.
- Do **not** block anyone else — a blanket policy change (a default-DROP
  chain policy, for instance) would also lock out legitimate traffic and
  your own SSH access.
- Make it **idempotent** — running it twice must not create a duplicate
  rule.
- Make it **additive** — a second run of this playbook with a *different*
  `ioc_ip` must not undo a previous indicator's block. Each invocation adds
  its own drop.

### Step 1.2 — Apply and Verify

Test manually first, with an address of your own choosing:

```bash
ansible-playbook runbooks/block-ioc.yml -e ioc_ip=198.51.100.7
```

```bash
cd ..
make test
cd workspace
```

### Step 1.3 — Acceptance

ARIA arms **two different attacker source IPs** on the range (you see
neither). She runs `block-ioc.yml` against each, confirming: the attacker
can no longer reach any node, a legitimate control source still can (no
collateral lockout), SSH still answers on every node, and a second run of
the same scenario reports zero changes. She also confirms that blocking the
second indicator didn't quietly undo the first's block. A hardcoded address
passes one scenario and lets the other attacker straight through.

---

## PHASE 2: Collect the Evidence

> You can't respond to an indicator you haven't found. This runbook finds it
> for you — and proves it did, in a format a human or a script can read.

### What You Are Building

Fill in `workspace/runbooks/collect-triage.yml`.

### Step 2.1 — Understand the Objective

- Read `{{ evidence_log }}` on each node and find the source IP
  (`src=<ip>`) that appears **most often** — that's the indicator. Never
  hardcode a value; discover it from the log.
- Write a JSON report to `{{ report_path }}`, **on each node**, in exactly
  this shape:

  ```json
  {"indicator_ip": "<top source IP>", "hits": <count on THIS node>}
  ```

  The count is per node — each node's log has its own hit count for the
  same indicator.
- This runbook is **read-only recon**. It must not modify anything on the
  host besides writing the report itself — no `become`, no touching
  `/etc/passwd` or any other file.
- It must be **deterministic** — the same evidence log must produce the
  same report on a re-run.

### Step 2.2 — Apply and Verify

You can plant your own test evidence on a node to check your logic before
trusting `make test`:

```bash
make ssh-web
echo '2026-01-01 sshd: Failed password src=203.0.113.5' | sudo tee -a /tmp/my-test.log
exit
ansible-playbook runbooks/collect-triage.yml \
  -e evidence_log=/tmp/my-test.log -e report_path=/tmp/my-report.json
```

```bash
cd ..
make test
cd workspace
```

### Step 2.3 — Acceptance

ARIA runs `collect-triage.yml` against **two different incidents** (you see
neither): different evidence logs, different top indicators, different
per-node hit counts. She checks the JSON report on every node names the
correct indicator with the correct count, that it's valid JSON, that
nothing else on the host changed (a canary file and the log itself are
hashed before and after), and that a re-run produces a byte-identical
report. Guessing or hardcoding an indicator passes neither incident; only
one lucky enough to overlap the count you happened to test.

---

## PHASE 3: Rotate the Credential

> The account is compromised — the attacker has its old password. Rotate it
> without taking the account, or the fleet, offline.

### What You Are Building

Fill in `workspace/runbooks/rotate-creds.yml`.

### Step 3.1 — Understand the Objective

- Set `{{ target_user }}`'s password to `{{ new_password }}` on every node.
- The account must stay **usable** — do not lock or disable it, only rotate
  its credential.
- Make it **idempotent** in the strict sense this mission cares about: a
  second run must produce the **identical stored hash**, not just "no
  errors." A fresh random salt each run changes the hash every time, which
  reads to ARIA as churn even though the password itself hasn't changed.

### Step 3.2 — Apply and Verify

```bash
ansible-playbook runbooks/rotate-creds.yml \
  -e target_user=cadet_test -e new_password='Some-New-Secret-1'
```

```bash
cd ..
make test
cd workspace
```

### Step 3.3 — Acceptance

ARIA runs `rotate-creds.yml` against **two different compromised accounts**
(you see neither). For each, she confirms: the new password works and the
old one no longer does, on every node; the account remains in a usable
password state (not locked); SSH still answers; and the stored password
hash is byte-identical across a second run of the same scenario. Hardcoding
a username fixes one account and leaves the other one compromised.

---

## PHASE 4: Restore the Service (Capstone)

> The Hydra didn't just crash these services — it broke their unit
> definitions two different ways. A restart has nothing valid left to
> restart. You have to rebuild the truth, not nudge the process.

### What You Are Building

Fill in `workspace/runbooks/restore-service.yml`.

### Step 4.1 — Understand the Objective

- Copy the known-good unit from
  `{{ golden_root }}/{{ service_name }}.service` to
  `/etc/systemd/system/{{ service_name }}.service` on every node.
- Tell systemd to notice the change — but **only if the unit file actually
  changed**. Reloading unconditionally on every run isn't wrong, exactly,
  but reloading in the wrong order is: if the daemon reload happens after
  you've already tried to enable/start the service, the enable/start can
  fail outright on a service whose unit was deleted, because systemd never
  knew the file existed until the reload ran.
- Enable and start the service.
- Make it **idempotent** — a second run against an already-healthy service
  must report zero changes.

### Step 4.2 — Apply and Verify

You won't have a broken service to restore until `make test` breaks one for
you (ARIA arms the outage right before grading this phase) — so this
phase's manual verification is limited to confirming the playbook itself
runs cleanly against a healthy service (which should report `changed=0`,
since nothing needs reconciling):

```bash
ansible-playbook runbooks/restore-service.yml \
  -e service_name=some-service -e golden_root=/opt/sdc/known-good
```

```bash
cd ..
make test
cd workspace
```

### Step 4.3 — Acceptance

ARIA breaks **two different services two different ways** — one with a
corrupted unit file, one with the unit file deleted entirely — then runs
`restore-service.yml` against each. Both must come back **active**,
**enabled**, and serving their known-good content, on every node. She also
checks that restoring one service didn't disturb the other, and that a
second run against an already-restored service reports zero changes. A bare
`systemctl restart` cannot pass this phase — there is nothing left to
restart until the unit is reconciled from the golden store.

---

## MISSION COMPLETE — DEBRIEF CHECKLIST

Before closing this mission, confirm the following:

- [ ] All four runbooks exist at `workspace/runbooks/` and take their
      indicator/user/service/path entirely from `-e` variables
- [ ] `block-ioc.yml` drops the given indicator fleet-wide, idempotently,
      without collateral lockout, and without undoing a previous block
- [ ] `collect-triage.yml` discovers the top indicator and per-node hit
      count from the log, writes valid JSON on every node, and changes
      nothing else
- [ ] `rotate-creds.yml` rotates the given account fleet-wide with a
      **stable** hash, leaving it usable
- [ ] `restore-service.yml` reconciles the given service from the golden
      store, reloads systemd only when the unit changed, then enables and
      starts it
- [ ] Every runbook re-run against the same scenario reports zero changes
      (or, for triage, a byte-identical report)
- [ ] `make test` reports all four phases passing

If any item is incomplete, return to the corresponding phase and complete it
before closing the mission record.

---

*SDC Cyber Command — 2187 — LIEUTENANT COMMANDER EYES ONLY*
