# Starfall Defence Corps Academy

> 🧭 [← Master Simulation](https://github.com/starfall-defence-corps/master-simulation) · **You are here: MOS 5 · Mission 1 — Battle Rattle** · [🏠 Academy Hub](https://github.com/starfall-defence-corps/sdc-academy)

> ☁️ **No Docker on your machine?** Create your own copy first (Use this template), then on **your** repo: **Code → Codespaces → Create codespace** — everything is preinstalled. First boot takes ~5 min (one-time); after that it starts fast.

## MOS 5 · Mission 1: Battle Rattle — Reusable Incident-Response Runbooks

> *"Sever one indicator and the Hydra regrows under a new one. Kill the head, not the Hydra."*

**Rank: Lieutenant Commander** — this is a **Module 3: Specialization** (MOS) mission. Completing two or more MOS missions earns **Commander**.

Real incident response never hands you the indicator you rehearsed against. This mission is not about handling *one* incident well — it's about building a **kit** you can pick up and use on any incident, because you never write bespoke playbooks under fire. You will author four small, parameterised Ansible runbooks — contain, investigate, remediate, recover — against a three-node fleet under live attack from an adversary who keeps changing shape. ARIA doesn't grade whether your runbook worked on the incident you tested it against. She arms **two independent, randomised scenarios you never see** for every runbook and runs your **same** file against both. A runbook that only works on the indicator you memorised is not a battle rattle.

This is purely defensive work: you are responding to an incident on **your own** fleet, nothing more.

## Prerequisites

- All of Module 1 and Module 2 (roles, variables, templates, handlers, firewalling, incident response).
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker Compose v2)
- [GNU Make](https://www.gnu.org/software/make/)
- [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/) (`ansible-core`) — **installed on your own machine**. Your runbooks run from your host, not from a lab-managed venv.
- Python 3.10+ (for the grading environment) — on Debian/Ubuntu: `sudo apt install python3-venv`
- Git

> **Windows users**: run everything inside [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install), with Docker Desktop on the WSL2 backend.

## Quick Start

```bash
# 1. Use this template on GitHub (green button, top right) to create YOUR OWN
#    copy. Set it Public, then clone it:
git clone https://github.com/YOUR-USERNAME/mission-3-5-battle-rattle.git
cd mission-3-5-battle-rattle

# 2. Check your machine is mission-ready
make doctor

# 3. Bring the fleet + range online — the Hydra strikes immediately
make setup

# 4. Write your four runbooks in workspace/runbooks/, then ask ARIA
make test

# 5. Ready? Submit
make submit
```

6. **Read your orders**: [Mission Briefing](docs/BRIEFING.md)
7. **Work the response**: [Exercises](docs/EXERCISES.md)
8. **Stuck?** [Hints & Troubleshooting](docs/HINTS.md)
9. **Track progress**: [Checklist](CHECKLIST.md)
10. **Ready?** `make submit`

## Your Battle Rattle

Four runbooks, canonically at `workspace/runbooks/<verb>.yml`, invoked with `-e` vars — the kit you carry into every incident, because you never know which indicator you'll be handed.

| Runbook | Phase | What it does | `-e` vars |
|---------|-------|---------------|-----------|
| `block-ioc.yml` | Contain | Firewall-DROP all traffic from an indicator, fleet-wide — without blocking anyone else | `-e ioc_ip=<ip>` |
| `collect-triage.yml` | Investigate | Read-only recon: finds the indicator that appears most in an evidence log and reports its per-node hit count | `-e evidence_log=<path> -e report_path=<path>` |
| `rotate-creds.yml` | Remediate | Rotates a compromised credential fleet-wide, idempotently, without locking the account | `-e target_user=<user> -e new_password=<secret>` |
| `restore-service.yml` | Recover (capstone) | Reconciles a downed systemd service back to its known-good state — a restart cannot fix a corrupted or missing unit | `-e service_name=<svc> -e golden_root=<dir>` |

Each one must work for **any** indicator, incident, user, or service — ARIA runs your exact runbook against two scenarios you cannot see, in one lab pass.

## Lab Architecture

```
 Your Machine
+---------------------------------------------------------------+
|  ansible-playbook runs HERE — not in a lab venv                |
|  workspace/           (the only place you write Ansible)       |
|    ansible.cfg                                                 |
|    inventory/hosts.yml         (the fleet, pre-registered)     |
|    runbooks/            (you build these four)                 |
|      block-ioc.yml                                              |
|      collect-triage.yml                                         |
|      rotate-creds.yml                                           |
|      restore-service.yml                                        |
|                                                               |
|  Docker Network: 172.30.0.0/24                                 |
|  +------------+  +------------+  +------------+   the fleet     |
|  | sdc-web    |  | sdc-db     |  | sdc-comms  |   under         |
|  | .11  :2221 |  | .12  :2222 |  | .13  :2223 |   incident      |
|  +------------+  +------------+  +------------+                 |
|                          |                                      |
|                          v                                      |
|  +-------------------------------+   opaque range / injector    |
|  | sdc-range                     |   arms two nonce scenarios   |
|  | attacker IPs, evidence logs,  |   per runbook — you never    |
|  | compromised users, downed     |   see them; ARIA reads       |
|  | services — .lab/baseline.json |   ground truth from it       |
|  +-------------------------------+                             |
+---------------------------------------------------------------+
```

The fleet comes up **online and already under incident**: an attacker IP hammering it, evidence logs planted, two users compromised, two services downed. Your four runbooks are the only fix — and each must be reusable, not written for the one scenario you happened to poke at.

Only one SDC lab at a time is supported — run `make destroy` in any other mission first.

## Available Commands

```
make help       Show available commands
make doctor     Check your machine is mission-ready (Docker, ports, tools)
make setup      Deploy the fleet + range and arm the incident scenarios
make test       Ask ARIA to verify your runbooks work against BOTH scenarios
make reset      Destroy and rebuild the fleet + range (re-arms fresh nonces)
make destroy    Tear down everything (containers, keys, venv, range state)
make ssh-web    SSH into sdc-web    (172.30.0.11, port 2221)
make ssh-db     SSH into sdc-db     (172.30.0.12, port 2222)
make ssh-comms  SSH into sdc-comms  (172.30.0.13, port 2223)
make submit     Submit your work for ARIA review (branch, commit, push, PR)
```

## Mission Files

| File | Purpose |
|------|---------|
| [BRIEFING.md](docs/BRIEFING.md) | Mission briefing — **read this first** |
| [EXERCISES.md](docs/EXERCISES.md) | Phase-by-phase operational instructions (4 phases) |
| [HINTS.md](docs/HINTS.md) | Troubleshooting and hints |
| [CHECKLIST.md](CHECKLIST.md) | Progress tracker |

## How ARIA scores this mission

`make test` is deterministic pytest — the pass/fail authority. For each of the four verbs, ARIA arms **two independent, randomised scenarios** (A/B) and runs your **same** `workspace/runbooks/<verb>.yml` against both, in one pass, checking effects independently of how you implemented them (firewall drops are tested by sourcing traffic from the range; credential/service/report state is read straight off the node). Both scenarios must succeed on **every** fleet node — there is no partial credit — and every verb must be idempotent on a second run. A runbook hardcoded to one scenario passes it and fails the other; that is the entire lesson.

- **A dead or unarmed range reads as skipped or INCONCLUSIVE**, never a false pass. If you see that, run `make reset` to re-arm the incident and re-run `make test`.
- The ARIA GitHub Action on your pull request only **narrates** — the pass/fail authority is always the local `make test`.

## ARIA Review (Pull Request Workflow)

**ARIA** (Automated Review & Intelligence Analyst) reviews your work two ways:

**Locally** — `make test` for instant pass/fail verification. No API key needed.

**On Pull Request** — push a branch, open a PR to `main`, and ARIA posts a
qualitative review as a PR comment. To enable it, add an `ANTHROPIC_API_KEY` repo
secret (**Settings → Secrets and variables → Actions**). Without a key, PR review is
skipped and `make test` still works locally.

## Troubleshooting

**Containers won't start**: Ensure Docker Desktop is running; check for port conflicts on 2221-2223. Only one SDC lab at a time is supported — run `make destroy` in any other mission first.

**`make test` reports everything skipped**: the range isn't up or the baseline is missing — run `make reset`.

**`ansible-playbook` fails with "command not found"**: `ansible-core` isn't on your machine's PATH — this mission runs Ansible from your host, not a lab venv. See Prerequisites.

**Need a clean slate**: `make reset` (rebuilds the fleet + range, re-arms fresh nonces) or `make destroy` (full teardown).

**Docker network conflict** ("Pool overlaps..."): another Docker network is using 172.30.0.0/24 — stop it, or edit `.docker/docker-compose.yml`.
