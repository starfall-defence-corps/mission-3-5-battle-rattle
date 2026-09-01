# Mission 3.5: Battle Rattle — Progress Tracker

**Rank**: Lieutenant Commander
**Module**: MOS 5 · Mission 1 (Specialization)

Check each item off as you complete it. Run `make test` after each phase —
it re-arms and re-scores against the live fleet and range every time. If a
phase is blocked, see `docs/HINTS.md`.

---

## Phase 0: Boots on the Ground

- [ ] `make doctor` — machine is mission-ready, including `ansible-core` on your own host
- [ ] `make setup` — fleet + range online, incident already live (attacker IP, evidence, compromised users, services)
- [ ] Explored the scaffolding — `workspace/runbooks/*.yml` are stubs with an `assert` task and a header comment describing "done"
- [ ] Confirmed a fresh `make test` fails every phase — that's expected, nothing is written yet

---

## Phase 1: Block the Indicator

**Deliverable**: `workspace/runbooks/block-ioc.yml` drops a given `-e ioc_ip` fleet-wide.

- [ ] Drops all traffic from `{{ ioc_ip }}` on every node (`ansible.builtin.iptables`, chain `INPUT`, `jump: DROP`)
- [ ] No blanket policy change — legitimate traffic and SSH still get through
- [ ] Idempotent — a second run against the same indicator reports zero changes
- [ ] Additive — blocking a second indicator doesn't undo the first block
- [ ] **ARIA checks**: both hidden attacker IPs blocked fleet-wide, on every node, with liveness preserved

---

## Phase 2: Collect the Evidence

**Deliverable**: `workspace/runbooks/collect-triage.yml` finds the top indicator in `-e evidence_log` and reports it per node at `-e report_path`.

- [ ] Discovers the most frequent `src=<ip>` in the log — never hardcoded
- [ ] Writes valid JSON on **every** node: `{"indicator_ip": "...", "hits": N}`
- [ ] `hits` is the count **on that node**, not a fleet-wide total
- [ ] Read-only — no `become`, nothing besides the report file changes on the host
- [ ] Deterministic — a re-run produces a byte-identical report
- [ ] **ARIA checks**: both hidden incidents' indicators + per-node counts correctly reported, host otherwise untouched

---

## Phase 3: Rotate the Credential

**Deliverable**: `workspace/runbooks/rotate-creds.yml` rotates `-e target_user` to `-e new_password` fleet-wide.

- [ ] Sets the new password on every node (`ansible.builtin.user`, `update_password: always`)
- [ ] Uses a **stable** salt (e.g. `(target_user | hash('md5'))[:16]`) — not a fresh random one each run
- [ ] Account remains usable — not locked, not disabled
- [ ] Idempotent — the **stored hash** is identical on a second run against the same scenario
- [ ] **ARIA checks**: both hidden compromised users rotated fleet-wide, old password revoked, account stays usable

---

## Phase 4: Restore the Service (Capstone)

**Deliverable**: `workspace/runbooks/restore-service.yml` reconciles `-e service_name` from `-e golden_root`.

- [ ] Copies the known-good unit into `/etc/systemd/system/{{ service_name }}.service` (`remote_src: true`)
- [ ] Reloads systemd **only when the unit changed**, and **before** the enable/start task runs
- [ ] Enables and starts the service (not just `restarted` — the unit may not have existed at all)
- [ ] Idempotent — a second run against an already-healthy service reports zero changes
- [ ] **ARIA checks**: both hidden services (one corrupted unit, one deleted unit) restored active + enabled + serving correct content, on every node, without disturbing each other

---

## Before You Submit

- [ ] All four runbooks live at `workspace/runbooks/`, parameterised entirely on their documented `-e` vars
- [ ] `grep -rn` for any literal IP, username, service name, or path you tested with returns nothing in `workspace/runbooks/` — everything comes from `-e` vars
- [ ] No secrets or credentials committed anywhere in the repo
- [ ] `workspace/inventory/`, `workspace/ansible.cfg`, the README, and the ARIA workflow are untouched
- [ ] `make test` — all four phases pass
- [ ] `make submit` — work submitted for ARIA review
