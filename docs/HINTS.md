# Mission 3.5: Battle Rattle — Hints & Troubleshooting Guide

> 📚 Deeper reference: [FM-1 — Ansible Module Reference](https://github.com/starfall-defence-corps/sdc-academy/blob/main/field-manuals/FM-1-ansible-reference.md)

**Rank**: Lieutenant Commander (Minimal Scaffolding)

This guide escalates in three stages per phase: a **Nudge** (a question to
get you thinking in the right direction), **More** (the specific module and
shape to use), and a **Full Worked Solution** (the exact, verified runbook
task). Try the Nudge first. Consulting HINTS.md at this rank is doctrine, not
weakness — but reaching straight for the full solution every time will cost
you on the missions that don't provide one.

---

## Phase 1 — Block the Indicator (`block-ioc.yml`)

### Nudge

Which single Ansible module both inserts a firewall rule *and* recognises
when that exact rule already exists — so running it twice doesn't create a
duplicate?

### More

- `ansible.builtin.iptables`, `chain: INPUT`, `source: "{{ ioc_ip }}"`,
  `jump: DROP`. This module diffs against the live ruleset, so a second run
  with the same `ioc_ip` is naturally idempotent.
- The gotcha isn't the module — it's the temptation to also set a chain
  *policy* (`-P INPUT DROP`) "to be safe." Don't. A policy change blocks
  everyone, including the range's own legitimate control traffic and your
  SSH session. Block the **one** source, nothing else.
- Because each scenario adds its own DROP rule and doesn't touch or replace
  any existing rule, blocking a second indicator later doesn't undo the
  first block — that falls out of using `iptables` to *insert* a
  source-specific rule rather than rewriting the chain.

### Full Worked Solution

**`workspace/runbooks/block-ioc.yml`** (replacing the `TODO` task)
```yaml
- name: Drop all traffic from the indicator
  ansible.builtin.iptables:
    chain: INPUT
    source: "{{ ioc_ip }}"
    jump: DROP
    comment: "block-ioc: {{ ioc_ip }}"
```

**Why this is idempotent AND additive.** `ansible.builtin.iptables` checks
whether an equivalent rule already exists before inserting — so a second run
with the same `ioc_ip` reports `changed: false`. Because the task only ever
adds a rule scoped to `source: "{{ ioc_ip }}"`, it never touches a rule for
any other address, so running this playbook again with a *different*
`ioc_ip` adds a second, independent DROP rule rather than replacing the
first. That's the difference between "blocked this attacker" and "blocked
whichever attacker I last ran this against."

**Verifying by hand:**
```bash
make ssh-web
sudo iptables -L INPUT -n --line-numbers
exit
```

---

## Phase 2 — Collect the Evidence (`collect-triage.yml`)

### Nudge

You need two numbers per node: which source IP shows up most in the log,
and how many times. What's the simplest Unix pipeline that already answers
"which line appears most often, and how many times"? You don't need to
reinvent it in Jinja — a `shell`/`command` task with `changed_when: false`
keeps the read-only guarantee intact.

### More

- `grep -oE 'src=[0-9]{1,3}(\.[0-9]{1,3}){3}'` pulls every `src=<ip>` token
  out of the log; `cut -d= -f2 | sort | uniq -c | sort -rn | head -1` turns
  that into `"<count> <ip>"` for the winner. Wrap it in
  `ansible.builtin.shell` (you need the pipe) with
  `args: {executable: /bin/bash}` and `changed_when: false` — this task
  reads, it never changes anything, so it should never report `changed`.
- Parse that one line of output with `ansible.builtin.set_fact` and
  `.split()`.
- Write the report with `ansible.builtin.copy` and `content:
  "{{ {'indicator_ip': ..., 'hits': ...} | to_nice_json }}"` — `copy` with
  `content:` is idempotent on its own (it only writes if the rendered
  content differs from what's already on disk), which is exactly what you
  need for the fingerprint check.
- No `become:` anywhere in this file. If a task needs it to read the log,
  that's a sign something's off — this lab's evidence logs are readable by
  `cadet` without escalation, on purpose, because recon shouldn't require
  privilege it doesn't need.

### Full Worked Solution

**`workspace/runbooks/collect-triage.yml`** (replacing the `TODO` task)
```yaml
- name: Count indicator hits in the evidence log
  ansible.builtin.shell: >-
    set -o pipefail;
    grep -oE 'src=[0-9]{1,3}(\.[0-9]{1,3}){3}' {{ evidence_log }}
    | cut -d= -f2 | sort | uniq -c | sort -rn | head -1
  args:
    executable: /bin/bash
  register: top_line
  changed_when: false

- name: Parse the winning indicator and its count
  ansible.builtin.set_fact:
    top_hits: "{{ top_line.stdout.split()[0] | int }}"
    top_ip: "{{ top_line.stdout.split()[1] }}"

- name: Write the triage report
  ansible.builtin.copy:
    dest: "{{ report_path }}"
    content: "{{ {'indicator_ip': top_ip, 'hits': top_hits} | to_nice_json }}\n"
    mode: "0644"
```

**Why `changed_when: false` matters here.** Without it, the `shell` task
reports `changed` on every run just because a shell command executed — that
inflates your changed-count and muddies the read-only story this runbook is
supposed to tell, even though nothing on the host actually moved besides the
report file itself. `copy`'s own idempotence then does the rest: as long as
the log's contents don't change between runs, `top_ip`/`top_hits` are
recomputed identically, and `copy` sees the same content and reports no
change.

**Verifying by hand:**
```bash
make ssh-web
cat /tmp/my-report.json
sha256sum /etc/passwd   # run before and after — must be unchanged
exit
```

---

## Phase 3 — Rotate the Credential (`rotate-creds.yml`)

### Nudge

`ansible.builtin.user`'s `password:` field wants a hash, not the plaintext,
and `password_hash()` normally generates a fresh random salt every time
you call it — which is exactly what makes a naive rotation *not*
idempotent. What would you need to hold constant across runs to make the
hash itself deterministic?

### More

- `ansible.builtin.user`, `password: "{{ new_password | password_hash('sha512', salt) }}"`,
  where `salt` is a **stable** string, ≤16 characters, derived from
  something that doesn't change between runs — `target_user` itself is
  perfect:

  ```
  salt = (target_user | hash('md5'))[:16]
  ```

  Same `target_user`, same `new_password` in, same salt in, same stored
  hash out — every time.
- `update_password: always` — without it, `user` won't touch a password
  that's already set, which would leave the *old* (compromised) password in
  place.
- Do **not** set `password_lock: true` or `state: absent` — either locks or
  removes the account. The mission requires it to stay usable.

### Full Worked Solution

**`workspace/runbooks/rotate-creds.yml`** (replacing the `TODO` task)
```yaml
- name: Rotate the credential with a stable hash
  ansible.builtin.user:
    name: "{{ target_user }}"
    password: "{{ new_password | password_hash('sha512', (target_user | hash('md5'))[:16]) }}"
    update_password: always
```

**Why the stable salt is the whole phase.** `password_hash('sha512', salt)`
with no salt argument picks a new random salt on every call, so even
hashing the *exact same* password twice in a row produces two different
`$6$...` strings — which `ansible.builtin.user` sees as "the password
changed" and dutifully rewrites, forever, on every run. Deriving the salt
from `target_user` (or any other value that's fixed for the scenario) makes
`password_hash()` pure: same inputs, same hash, every time — so the second
run of an already-rotated account reports zero changes, exactly as ARIA's
fingerprint check requires.

**Verifying by hand:**
```bash
make ssh-web
sudo passwd -S cadet_test
sudo getent shadow cadet_test | cut -d: -f2
exit
```

---

## Phase 4 — Restore the Service (Read This Before You Guess)

### Nudge

If the unit file was *deleted*, systemd has never heard of your service —
no amount of `systemctl start` fixes that until systemd re-reads
`/etc/systemd/system/`. If you notify a handler to do that reload, when does
a notified handler actually run relative to the very next task in your
playbook?

### More

- By default, a `notify`-ed handler runs at the **end of the play**, not
  immediately after the task that notified it. If your "enable and start"
  task comes right after the "copy the unit" task in the same task list, a
  handler-based reload hasn't fired yet when "start" runs — and starting a
  service systemd has never heard of fails outright on the deleted-unit
  scenario.
- The fix used in this mission's reference approach: skip the handler
  mechanism entirely for this ordering-sensitive case. **Register** the copy
  task's result, then run the reload as a normal task **conditioned on that
  result** — `when: <copy_result>.changed` — so it happens in-line, in
  order, only when needed:

  ```yaml
  - name: Reconcile the unit
    ansible.builtin.copy: { ... }
    register: unit_copy

  - name: Reload systemd if the unit changed
    ansible.builtin.systemd:
      daemon_reload: true
    when: unit_copy.changed

  - name: Enable and start the service
    ansible.builtin.systemd: { name: ..., enabled: true, state: started }
  ```

  (If you'd rather use the commented-out `notify`/handler scaffold left in
  the file, you can — but you must add `meta: flush_handlers` right after
  the copy task, or you'll hit the exact ordering bug above.)
- `ansible.builtin.copy` with `remote_src: true` copies a file that's
  already on the node (the golden unit) to another path on the same node —
  you don't need `fetch`/`template`, the source and destination are both
  server-side.

### Full Worked Solution

**`workspace/runbooks/restore-service.yml`** (replacing the `TODO` task)
```yaml
- name: Reconcile the unit from the known-good store
  ansible.builtin.copy:
    remote_src: true
    src: "{{ golden_root }}/{{ service_name }}.service"
    dest: "/etc/systemd/system/{{ service_name }}.service"
  register: unit_copy

- name: Reload systemd if the unit changed
  ansible.builtin.systemd:
    daemon_reload: true
  when: unit_copy.changed

- name: Enable and start the service
  ansible.builtin.systemd:
    name: "{{ service_name }}"
    enabled: true
    state: started
```

**Why "declarative, not restart" is the whole capstone.** `systemctl
restart` asks systemd to stop-then-start whatever it currently believes the
unit to be. On the corrupted-unit scenario, that belief is garbage; on the
deleted-unit scenario, there's no belief at all. Neither restart has
anything valid to act on. Copying the golden unit back into place and
reloading (in the right order) rebuilds systemd's *truth* about the service
before you ever ask it to start anything — which is why this reconciles
both break modes with one runbook, instead of needing special-case logic
per failure type.

**Verifying by hand (only meaningful once `make test` has broken a
service for you, or you break one yourself for practice):**
```bash
make ssh-web
sudo systemctl status some-service
sudo systemctl is-enabled some-service
curl -s localhost:PORT   # should return the golden token
exit
```

---

## General Troubleshooting

**"`ansible-playbook: command not found`."**
This mission runs Ansible from your own machine, not a lab-provided venv —
install `ansible-core` (see README Prerequisites) and confirm `make doctor`
passes.

**"`make test` reports everything skipped."**
The range isn't answering, or the baseline is missing. Give `make setup` a
few more seconds, or run `make reset`.

**"My playbook runs clean but `make test` still fails."**
A green Ansible run only proves your tasks executed without error — it says
nothing about whether the *effect* actually landed the way ARIA checks it
(a missing `daemon_reload` before `start`, a random salt that silently
breaks idempotence, a report written to the wrong path). Grade your own work
the way ARIA does: trigger the effect by hand on the node and look for it,
rather than trusting "no errors" means "correct."

**"My runbook is not idempotent, and I can't tell which task is the
culprit."**
Run it twice and read the recap line for each host after the *second* run —
`changed=0` is what you want. If it's nonzero, re-run with `-v` and look at
which task reports `"changed": true` on the second pass. The usual suspects
in this mission: a missing `changed_when: false` on a `shell`/`command`
task, a `password_hash()` call without a stable salt, or a `systemd` reload
that isn't conditioned on the copy actually changing something.

**"make: *** No targets specified" or "make: *** No rule to make target".**
You are in the wrong directory. `make` commands must be run from the
**project root**, where the `Makefile` lives — not from `workspace/`. Run
`cd ..` to go back.

**Never edit anything under `.docker/`.**
That directory is the range itself — the fleet-node images, the range
image, and the compose file wiring it all together. Your entire mission is
written in `workspace/runbooks/`.

**Quick diagnostic sequence when something is not working:**
1. `docker ps` — are all three fleet containers and `sdc-range` running?
2. `make ssh-web` / `make ssh-db` / `make ssh-comms` — can you still reach
   each node with your key?
3. On the node, check the specific artifact for the phase you're on:
   `sudo iptables -L INPUT -n`, `cat <report_path>`,
   `sudo getent shadow <user>`, `systemctl status <service>`.
4. If nothing above explains it, `make reset` and re-apply from a
   known-clean fleet and range (this also re-arms fresh nonces, so old test
   values you used manually will no longer be valid).
