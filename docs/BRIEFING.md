---
CLASSIFICATION: LIEUTENANT COMMANDER EYES ONLY
MISSION: 3.5 — BATTLE RATTLE
THEATRE: Starfall Defence Corps Academy
AUTHORITY: SDC Cyber Command, 2187
---

# OPERATION ORDER — MISSION 3.5: BATTLE RATTLE

---

## 1. SITUATION

### 1a. Enemy Forces

Designation: **THE HYDRA**. Prior encounters with this adversary ended with
cadets writing a perfect, surgical response to the exact incident in front of
them — and getting overrun the moment the adversary came back wearing a
different face. Post-incident review across the Academy's exercise history
reached the same conclusion every time: an incident-response script that only
works on the indicator it was written for is not a response capability. It is
a souvenir from the last fight.

The Hydra's doctrine is simple. Sever one head — one IOC, one compromised
account, one downed service — and it regrows under a new one. It does not
matter how cleanly you cut. What matters is whether your response generalises
to the head that grows back. A runbook with an IP address typed into a
condition, a username baked into a task, a service name assumed in a path —
all of these sever the head you can see and leave you defenceless against the
one you can't.

### 1b. Friendly Forces

The **Starfall Defence Corps (SDC)** fleet — three nodes, `sdc-web`,
`sdc-db`, and `sdc-comms` — currently under live incident: an attacker
source IP hammering the fleet, evidence logs already contaminated, two local
accounts already compromised, two scored services already downed. Nothing
here is theoretical. The fleet needs a response, now, and it needs one that
still works the next time this happens with different numbers.

### 1c. Attachments / Support

**ARIA** (Automated Review & Intelligence Analyst) remains assigned. ARIA
does not grade your runbooks on the one incident you tested against. She
arms **two independent, randomised scenarios** for every verb — different
attacker IPs, different evidence, different compromised users, different
downed services — and runs your **same** runbook file against both, in one
lab pass. Your runbook never sees which scenario is live; it only sees the
`-e` variables it was handed. A hardcoded solution passes the one you
happened to test and fails the one you didn't.

### 1d. Operational Tool

All operations will be conducted using **ANSIBLE** — *Automated Network for
Secure Infrastructure, Baseline Lockdown & Enforcement*. This is a
**purely defensive engagement**: you are responding to an incident on
**your own** fleet, nothing more.

---

## 2. MISSION

Author four small, parameterised runbooks at `workspace/runbooks/`, each
taking its indicator as an `-e` variable, never as a literal in the file:

1. **`block-ioc.yml`** (`-e ioc_ip=<ip>`) — contain. Firewall-DROP all
   traffic from the given indicator, fleet-wide, without touching anyone
   else's access.
2. **`collect-triage.yml`** (`-e evidence_log=<path> -e report_path=<path>`)
   — investigate. Read-only recon: find the source IP that appears most in
   the evidence log and write a machine-readable report of it, per node.
3. **`rotate-creds.yml`** (`-e target_user=<user> -e new_password=<secret>`)
   — remediate. Rotate the compromised account's credential fleet-wide,
   revoking the old password while keeping the account usable.
4. **`restore-service.yml`** (`-e service_name=<svc> -e golden_root=<dir>`)
   — recover, the capstone. Reconcile a downed service back to its known-good
   definition and bring it back up.

**End state**: all four runbooks, run against **any** indicator, incident,
compromised user, or downed service — including two that ARIA arms without
telling you — succeed on every node, leave the fleet no worse off than
necessary, and converge (change nothing) when run again.

---

## 3. EXECUTION

### 3a. Commander's Intent

The skill under test is not "can you write a playbook that blocks an IP." It
is "did you write a playbook that blocks *the* IP, whichever one it turns out
to be." Every runbook in this mission will be run at least twice, against two
things you cannot see, and idempotently on top of that. Build for
reusability from the first task, not as an afterthought once the obvious
version works.

### 3b. Concept of Operations

Four phases, run in the realistic IR order — contain, investigate,
remediate, recover — and verified behaviourally against two hidden scenarios
apiece. Full procedural detail is in **EXERCISES.md**.

| Phase | Task | Objective |
|-------|------|-----------|
| 1 | Block the Indicator | `block-ioc.yml` drops a given attacker IP fleet-wide, idempotently, without collateral damage |
| 2 | Collect the Evidence | `collect-triage.yml` discovers the real indicator in a log and reports it, read-only, per node |
| 3 | Rotate the Credential | `rotate-creds.yml` rotates a compromised account fleet-wide, idempotently, without locking it |
| 4 | Restore the Service (capstone) | `restore-service.yml` declaratively reconciles a downed service from known-good state |

### 3c. Fleet Assets

All nodes are accessible via SSH. Credentials are uniform across the fleet.

| Designation | Role | SSH Port |
|-------------|------|----------|
| `sdc-web` | Fleet Web Node | 2221 |
| `sdc-db` | Fleet Database Node | 2222 |
| `sdc-comms` | Fleet Comms Node | 2223 |

**SSH User**: `cadet`
**Authentication**: SSH key located at `workspace/.ssh/cadet_key`

The range, `sdc-range`, is opaque infrastructure. It arms both scenarios per
verb and records ground truth in the gitignored `.lab/baseline.json`, which
ARIA reads to grade you — you never read it, and you never need to.

### 3d. Rules of Engagement

- This is a **defensive engagement only**. You are responding to an incident
  on your own fleet — you never touch range infrastructure directly.
- Do not modify anything under `.docker/` — that is range infrastructure.
  Your work lives entirely in `workspace/runbooks/`.
- **Every runbook must be reusable, not memorised.** Take the indicator,
  user, service, or path as an `-e` variable and act on the variable. A
  literal address, username, or service name anywhere in a runbook is a
  guarantee it fails the scenario you didn't test against.
- **`collect-triage.yml` is read-only.** Recon that mutates the host it's
  investigating is not recon — it's contamination of the evidence. Gather
  and report; touch nothing else.
- **`restore-service.yml` reconciles, it does not restart.** A
  `systemctl restart` cannot revive a service whose unit file was corrupted
  or deleted — there is nothing valid left to restart. You must copy the
  known-good unit back into place, tell systemd to notice it (`daemon_reload`
  — and only when the unit actually changed, or you'll reload before the new
  unit exists on a fresh deletion), and only then enable and start it.
- **Every runbook must be idempotent.** Incident response gets re-run under
  pressure — by a teammate, by a script, by you at 3 a.m. not remembering you
  already ran it. A runbook that adds a duplicate firewall rule, re-locks an
  account, or restarts a healthy service on every run is not safe to re-run,
  and a response you're afraid to re-run is a response you can't trust
  mid-incident. Idempotence here isn't a style preference — it's the safety
  margin.
- Coverage must be **complete on every node**. A fleet with two nodes
  contained and one still exposed is not contained — there is no partial
  credit.
- All findings are behavioural. If ARIA cannot observe the effect on the
  node — the block, the report, the rotated credential, the restored
  service — your work is not complete, regardless of how correct the
  runbook looks on disk.

---

## 4. SUPPORT

| Resource | Function | Command |
|----------|----------|---------|
| **ARIA** | Verifies each runbook against two hidden scenarios; reports pass/fail per phase | `make test` |
| **HINTS.md** | Operational guidance if the mission stalls | — |
| **Range Reset** | Rebuilds the fleet and range, re-arming fresh nonces | `make reset` |

`make test` is deterministic pytest — the pass/fail authority. It runs each
of your four runbooks against scenario A, verifies the effect and
idempotence on every node, then does the same against scenario B, all in a
single pass. The GitHub Action that reviews your pull request only
**narrates**; it never re-decides pass/fail.

Consulting **HINTS.md** is authorised at Lieutenant Commander rank. Using
available intelligence is not weakness — it is doctrine.

---

## 5. COMMAND AND SIGNAL

**Reporting**: ARIA is your automated reporting chain. Her output is your
after-action record.

**Commander's Final Order**: This mission does not end until all four
runbooks work against an indicator, incident, user, or service you have
never seen — not just the one you tested against. A response that only
survives contact with the scenario you rehearsed has not been built. It has
been guessed.

Proceed to **EXERCISES.md** for phase-by-phase operational instructions.

---

*SDC Cyber Command — 2187 — LIEUTENANT COMMANDER EYES ONLY*
