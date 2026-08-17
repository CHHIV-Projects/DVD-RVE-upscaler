# CODING_AGENT_RULES_v1.md — DVD RVE Upscaler

## Document Status

**Version:** v1  
**Project:** DVD RVE Upscaler / DVD Enhance Assistant  
**Project phase:** foundation and architecture reconnaissance  
**Authoritative repository:** `/home/chuck/projects/DVD-RVE-upscaler`  
**Authoritative host:** `henderson-server1`  
**Current workflow baseline:** `docs/context/project_workflow_v1.md`  
**Current project-plan baseline:** `docs/context/dvd_rve_upscaler_project_plan_v1.md`

---

# Purpose

This document defines standing rules for AI coding agents working on the DVD RVE Upscaler codebase.

Its purpose is to reduce repeated milestone-prompt boilerplate while preserving:

- safety;
- milestone scope;
- original-media integrity;
- controlled NAS writes;
- shared-host protection;
- simple architecture;
- clean Git history;
- consistent prompt/closeout naming;
- honest validation;
- explicit runtime authority;
- explicit environment labels;
- cost-aware investigation;
- browser-first operator experience;
- reliable escalation when the approved roadmap is insufficient.

Milestone prompts may reference this file instead of repeating every standing rule.

This file is not a replacement for:

- the active milestone prompt;
- approved prompt addenda;
- current repository code;
- feature-specific reconnaissance;
- approved reconnaissance closeouts;
- Product Owner decisions;
- validation evidence;
- milestone closeout documentation;
- current operator/runtime documentation.

Use repository files and the active prompt as the source of truth.

Do not rely on chat memory alone.

---

# 1. Rule Priority

Apply instructions in this order:

1. explicit current Product Owner direction;
2. active milestone prompt and approved prompt addenda;
3. this rules document;
4. current project plan/workflow/context documents;
5. approved reconnaissance closeout;
6. maintained operator/runtime documentation;
7. prior prompts and closeouts;
8. agent assumptions.

When two instructions conflict:

- follow the safer rule;
- stop and identify the conflict;
- ask for clarification before risky implementation;
- do not silently choose a new architecture;
- do not silently broaden scope;
- do not silently change media-integrity, NAS-write, runtime, persistence, security, or publication semantics.

A milestone prompt may explicitly override a standing rule.

The closeout must document any material override:

- what changed;
- why it was necessary;
- who approved it;
- how safety was preserved;
- whether original-media, NAS, runtime, persistence, or security behavior changed.

---

# 2. Authoritative Environment and Repository

## 2.1 Authoritative Repository

The authoritative editable repository is:

```text
/home/chuck/projects/DVD-RVE-upscaler
```

on:

```text
henderson-server1
```

Normal editing occurs through:

```text
VS Code Remote SSH from the Windows workstation
```

Normal Git and repository commands run in:

```text
VS Code Remote SSH / Linux terminal
```

Do not assume a Windows checkout is authoritative.

Do not create parallel working copies unless explicitly approved.

---

## 2.2 Machine Roles

### Windows workstation

Current roles:

- Product Owner workstation;
- browser;
- VS Code client;
- VS Code Remote SSH client;
- MakeMKV ripping host;
- administrative/recovery access;
- optional PowerShell/SCP troubleshooting.

Normal application operation should not require PowerShell, SSH, or Remote Desktop.

### Linux mini-server — `henderson-server1`

Current roles:

- authoritative repository;
- application runtime;
- FFmpeg processing;
- RVE/TensorRT execution;
- NVIDIA GPU compute;
- NVENC encoding;
- server-local working storage;
- system telemetry;
- Cockpit administration;
- NAS mount access;
- host for other unrelated services/workloads.

The helper does not own the server.

### Synology NAS

Current roles:

- durable original DVD-rip storage;
- durable final enhanced-media storage;
- Jellyfin movie repository;
- backup/storage infrastructure.

Do not treat these machine roles as interchangeable.

---

## 2.3 Command Environment Labels

Every operational command block must identify where it runs when the wrong environment could cause confusion or risk.

Use labels such as:

```text
VS Code Remote SSH / Linux terminal
Windows PowerShell
Windows browser
Xfce / Remote Desktop
Cockpit
Synology DSM
```

Do not provide or execute an unlabeled operational command when environment confusion could matter.

---

# 3. Standard Agent Workflow

For every task:

1. Read this file.
2. Read the active milestone prompt and approved addenda.
3. Read the approved reconnaissance closeout when the prompt identifies one.
4. Confirm the authoritative repository.
5. Perform Git preflight.
6. Confirm current branch and upstream state when applicable.
7. Determine the milestone mode.
8. Confirm target environment and command authority.
9. Inspect relevant current code/documentation/runtime within scope.
10. Confirm the milestone boundary.
11. Ask only genuinely blocking questions.
12. Escalate when the approved roadmap is materially insufficient.
13. Implement or validate only approved scope.
14. Run the most relevant validation.
15. Create exactly one closeout using the required filename.
16. Leave commit, push, merge, branch, tag, NAS mutation, firewall mutation, service mutation, package mutation, mount mutation, Docker mutation, RVE/TensorRT mutation, and destructive operations to the Product Owner unless explicitly authorized.

Do not assume conversational context is complete or current.

Do not implement from memory when current files or runtime evidence contradict it.

Do not infer live runtime state solely from tracked files.

Do not inspect or mutate live runtime state beyond the active prompt's authority.

---

# 4. Milestone Modes

The active prompt must identify the intended mode.

Supported modes include:

```text
reconnaissance-only
implementation-after-reconnaissance
direct low-risk implementation
validation-only
documentation-only
bug-fix follow-up
deployment / operational validation
```

Do not silently change milestone mode.

---

# 4.1 Reconnaissance-Only Mode

Reconnaissance is the higher-reasoning phase.

Its purpose is to:

- inspect the relevant repository/runtime;
- map current behavior;
- inspect RVE/FFmpeg/NVENC/TensorRT integration;
- identify hidden dependencies;
- identify authority boundaries;
- identify NAS read/write realities;
- compare realistic implementation options;
- resolve architecture questions;
- identify safety, recovery, persistence, process-supervision, environment, security, and media-integrity concerns;
- select one recommended implementation direction;
- produce a practical roadmap.

Reconnaissance may inspect broadly when the feature genuinely spans multiple systems.

Reconnaissance must not become speculative architecture work.

Prefer the simplest safe recommendation that reuses current tools and authorities.

When the prompt says reconnaissance-only:

- do not modify product implementation files;
- do not begin coding;
- do not change NAS contents;
- do not alter NAS mounts/credentials;
- do not change UFW/firewall;
- do not install/remove system packages;
- do not modify RVE/TensorRT installation;
- do not create/modify services;
- do not process production media unless explicitly authorized;
- create the required reconnaissance closeout;
- stop after approved deliverables are complete.

The closeout should be usable as the implementation roadmap.

---

# 4.2 Implementation-After-Reconnaissance Mode

Implementation normally follows an approved reconnaissance closeout.

The reconnaissance closeout is the primary roadmap.

Implementation should:

- verify reconnaissance assumptions against the current branch/runtime;
- inspect named files/services/modules/tests;
- make the smallest safe change satisfying the locked contract;
- expand inspection only when current evidence contradicts the roadmap;
- do not repeat broad reconnaissance;
- do not reopen settled decisions without evidence;
- stop when required behavior and validation pass.

Recommended reading order:

```text
1. coding_agent_rules_v1.md
2. active implementation prompt
3. approved reconnaissance closeout
4. named implementation files
5. directly related tests
6. broader documents only when necessary
```

Do not repeat repository-wide searching unless:

- the repository/runtime changed materially;
- reconnaissance omitted a required path;
- targeted code contradicts reconnaissance;
- tests expose an undocumented dependency;
- a media-integrity, persistence, security, process-ownership, NAS-write, or runtime boundary remains unresolved.

When escalating, identify the exact reconnaissance assumption that failed.

Do not create alternative architectures merely because they are possible.

---

# 4.3 Direct Low-Risk Implementation Mode

A separate reconnaissance milestone is not required for:

- text changes;
- labels;
- narrow styling;
- focused tests;
- documentation-only edits;
- mechanical fixes;
- minor non-destructive bugs with an obvious local cause.

Even for low-risk work:

- inspect the directly relevant code;
- preserve scope;
- avoid unrelated cleanup;
- run relevant validation;
- create the required closeout.

Do not classify work as low-risk merely to reduce effort when it touches:

- source/original media;
- NAS publication;
- deletion/cleanup;
- arbitrary filesystem paths;
- arbitrary shell execution;
- RVE/TensorRT integration;
- job persistence;
- cancellation/process ownership;
- service supervision;
- firewall/network exposure;
- package/driver changes.

---

# 4.4 Validation-Only Mode

Validation-only milestones establish evidence without changing implementation.

Examples include:

- interlace/progressive classification;
- output-stream preservation;
- short-clip preparation;
- RVE TensorRT invocation;
- NVENC final encoding;
- thermal baselines;
- cancellation;
- restart/recovery;
- NAS publication rehearsal;
- browser smoke testing.

In validation-only mode:

- confirm target environment;
- inspect approved test matrix;
- use only approved controlled media/data;
- run approved checks;
- collect evidence;
- document pass/fail results;
- do not modify implementation code;
- do not silently repair defects;
- do not mutate NAS/runtime beyond explicit authorization.

A validation milestone must not silently become a repair milestone.

When a defect is found:

1. preserve evidence;
2. classify severity;
3. continue or stop according to the prompt;
4. identify whether prior conclusions are affected;
5. do not repair unless explicitly authorized;
6. recommend the smallest follow-up milestone.

---

# 4.5 Documentation-Only Mode

Documentation-only work may update:

- project plan;
- workflow;
- coding-agent rules;
- README;
- operator guides;
- milestone/history documents;
- chat handoffs.

In documentation-only mode:

- do not modify application code;
- verify statements against current code/prompts/closeouts/runtime evidence;
- distinguish implemented behavior from future direction;
- preserve historical milestone documents;
- create only requested documents;
- report new/superseded files;
- use exact-file staging guidance;
- do not inspect/mutate live runtime state unless explicitly authorized.

---

# 4.6 Bug-Fix Follow-Up Mode

A bug-fix follow-up should remain limited to the documented defect.

Rules:

- reproduce/confirm defect;
- identify smallest safe repair;
- preserve existing architecture;
- avoid broad refactors;
- add targeted regression coverage;
- document whether prior validation is invalidated;
- document retained limitation;
- create one closeout.

Do not hide bug fixes inside unrelated later work.

---

# 4.7 Deployment / Operational Validation Mode

Deployment/runtime work may require reconnaissance, implementation, or validation-only behavior.

The prompt must identify which applies.

Explicitly consider:

- target host;
- listening address;
- LAN-only/public exposure;
- firewall;
- service supervision;
- startup/restart behavior;
- logs;
- health checks;
- permissions;
- NAS mounts;
- publication authority;
- working directory;
- RVE installation;
- CUDA/TensorRT/NVIDIA dependencies;
- secrets;
- backup/recovery of application state;
- shared-host impact.

Do not assume:

- existing Jellyfin exposure authorizes exposing this helper publicly;
- existing NAS read access grants write authority;
- the helper may change system packages/drivers;
- the helper may modify RVE/TensorRT;
- the helper owns unrelated containers/services.

Silence is not mutation authority.

---

# 5. Reasoning-Level Guidance

## 5.1 High Reasoning

Use for:

- architecture;
- reconnaissance;
- RVE backend integration;
- NAS publication;
- job persistence design;
- process supervision/cancellation;
- security boundary design;
- telecine/interlace policy;
- media-integrity-sensitive transformations;
- thermal policy;
- deployment architecture;
- backup/recovery;
- ambiguous cross-system behavior.

High reasoning should produce a concrete roadmap, not endless exploration.

## 5.2 Medium Reasoning

Use for:

- targeted implementation after approved reconnaissance;
- bounded backend work;
- bounded frontend work;
- tests;
- implementation debugging;
- closeouts;
- targeted validation automation.

## 5.3 Lower Reasoning

Use for:

- narrow documentation edits;
- copy changes;
- mechanical updates;
- small isolated tests;
- low-risk formatting corrections.

Do not use lower reasoning merely to reduce cost when architecture/runtime/media integrity is uncertain.

---

# 6. Escalation Protocol

Do not continue experimenting indefinitely when the roadmap is insufficient.

Stop and report:

```text
STATUS: ESCALATION REQUIRED
```

when:

- current code/runtime materially contradicts reconnaissance;
- two or more materially different architectures remain unresolved;
- safe implementation appears to require a new major framework;
- a new persistence model appears necessary and was not approved;
- the RVE backend cannot satisfy the approved integration contract;
- NAS publication requires unapproved credentials/mount/permissions;
- browser input would need arbitrary shell authority;
- browser input would need arbitrary filesystem authority;
- a media decision is ambiguous and the approved policy does not cover it;
- telecine/cadence handling requires a new decision;
- original media could be modified/overwritten;
- final media could be overwritten without explicit decision;
- cancellation cannot be scoped to job-owned processes;
- implementation would materially expand beyond milestone scope;
- required validation cannot be completed;
- shared-host effects are materially greater than expected;
- unrelated dirty files threaten commit isolation;
- firewall/service/package/Docker/RVE/TensorRT mutation is needed but not authorized;
- protected secrets would need to be exposed;
- a product decision is required;
- the only apparent solution is speculative or substantially more complex than the approved roadmap.

Required format:

```text
STATUS: ESCALATION REQUIRED

Observed conflict:
Approved assumption that does not match:
Files, systems, and environments inspected:
Evidence:
Media/data/runtime implications:
Why proceeding is unsafe or materially broader:
Smallest safe options:
Recommended decision:
Incomplete changes, if any:
```

Do not create speculative abstractions or partial workarounds merely to avoid escalation.

Stop at the escalation point.

---

# 7. Simplicity and Restraint

The application should remain small and understandable.

Prefer:

- direct control flow;
- explicit job states;
- thin wrappers around proven tools;
- small helpers;
- clear responsibilities;
- targeted changes;
- simple browser UI;
- minimal JavaScript;
- narrow API additions;
- maintainable code;
- obvious operator behavior.

Avoid unless clearly required:

- generic workflow engines;
- plugin systems;
- event buses;
- microservices;
- Kubernetes;
- large frontend frameworks;
- speculative abstraction layers;
- custom inference engines;
- duplicate media-processing pipelines;
- multiple wrapper layers;
- arbitrary command interfaces.

Before adding a major abstraction, answer:

1. What exact current problem requires it?
2. Why can the simple approach not satisfy the requirement?
3. What is the smallest alternative?
4. What maintenance burden will it add?
5. Does it alter media integrity, security, persistence, failure, or runtime authority?

Prefer the simpler safe implementation.

Do not overbuild merely because the agent can.

---

# 8. Context Reading Rules

## 8.1 Always Read

- `docs/context/coding_agent_rules_v1.md`;
- active milestone prompt;
- approved prompt addenda;
- immediately preceding reconnaissance closeout when implementing from reconnaissance.

## 8.2 Read as Needed

Use broader documents when relevant:

```text
docs/context/dvd_rve_upscaler_project_plan_v1.md
docs/context/dvd_rve_upscaler_coder_intro_v1.md
docs/context/project_workflow_v1.md
README.md
prior prompts/closeouts in the same feature area
operator/runtime guides when later created
```

## 8.3 Targeted Implementation Reading

For implementation after reconnaissance, begin with:

1. this rules document;
2. implementation prompt;
3. approved reconnaissance closeout;
4. named files/modules;
5. directly related tests.

Do not reread the entire repository unless required.

## 8.4 High-Risk Context

Read relevant architecture/workflow sections before changing:

- original-media handling;
- NAS publication;
- path validation;
- subprocess execution;
- RVE/TensorRT integration;
- job persistence;
- cancellation/process ownership;
- cleanup/deletion;
- firewall/network exposure;
- service supervision;
- runtime permissions;
- credentials/secrets;
- thermal guardrails;
- backup/recovery.

---

# 9. Cost-Aware Investigation and Stopping

Milestone prompts should be as long as needed, but no longer.

Use these principles:

- standing rules belong here;
- milestone prompts describe the current delta;
- reconnaissance carries architecture into implementation;
- implementation prompts should not restate the entire reconnaissance;
- start with likely relevant files;
- stop broad investigation when implementation path is stable;
- do not repeat repository-wide scans without reason.

Stop broad investigation when:

- authority boundary is confirmed;
- persistence/state impact is understood;
- media-integrity impact is understood;
- target environment is confirmed;
- shared-host impact is understood;
- required files are identified;
- implementation path is known;
- validation is defined;
- further searching is unlikely to change the plan.

Do not stop while unclear:

- original-media integrity;
- overwrite behavior;
- failure behavior;
- cleanup/deletion scope;
- arbitrary path/shell authority;
- persistence semantics;
- job process ownership;
- NAS publication authority;
- telecine/interlace policy;
- runtime permissions;
- network exposure;
- recovery behavior.

Longer execution time is not evidence of better work.

The objective is the smallest safe validated change.

---

# 10. Git and Working Tree Rules

## 10.1 Git Preflight

Before editing, from:

```text
VS Code Remote SSH / Linux terminal
```

run:

```bash
cd /home/chuck/projects/DVD-RVE-upscaler
git branch --show-current
git status --short
git log --oneline --decorate -5
```

When upstream state matters and exists:

```bash
git rev-parse HEAD
git rev-parse '@{upstream}'
```

If the repository is brand new and has no commit/upstream yet, report that state rather than treating it as a failure.

Expected normal state after initialization:

```text
correct branch
working tree clean
active prompt committed
branch synchronized with upstream when required
```

Allowed exception:

```text
only the active prompt contains expected Q&A/addenda
```

---

## 10.2 Branch Correctness

Substantial implementation should normally occur on the approved feature branch.

If:

- prompt expects a feature branch but repository is on `main`;
- repository is on an unrelated feature branch;
- new unrelated work is being started on a completed branch;

stop and report the mismatch.

Do not create or switch branches unless explicitly authorized.

Documentation-only work may occur on the current approved branch when Product Owner/prompt permits it.

---

## 10.3 Dirty-Tree Classification

Classify each unexpected dirty file as:

```text
A. required prior-milestone follow-up
B. unrelated work
C. accidental/generated noise
D. required current-milestone work
```

Report:

- classification;
- path;
- brief diff summary;
- recommended handling.

Do not edit, revert, stage, stash, commit, delete, move, or clean unexpected files without authorization.

---

## 10.4 Git Write Commands

Do not run these without explicit authorization:

```text
git commit
git push
git reset
git rebase
git merge
git tag
git checkout
git switch
git stash
git clean
git branch -d
git branch -D
git push --delete
```

Read-only Git commands are expected:

```text
git status
git diff
git diff --name-only
git diff --stat
git log
git branch
git ls-files
git rev-parse
```

---

## 10.5 Specific-File Staging

Do not use:

```bash
git add .
```

unless the Product Owner explicitly approves the full dirty tree.

Preferred sequence:

```bash
git status --short
git diff --name-only
git diff --stat

git add -- "<specific file>"
git add -- "<specific file>"

git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
```

The staged file list must match the expected milestone file list.

Do not commit unexplained files.

Do not mix unrelated work in one commit.

Normalize problematic Windows CRLF line endings to Linux LF when needed.

---

# 11. Prompt and Closeout File Names

The active milestone prompt is authoritative for:

- milestone number;
- title;
- prompt filename;
- closeout filename;
- deliverables.

Use:

```text
<milestone>_<exact_snake_case_name>_prompt.md
<milestone>_<exact_snake_case_name>_closeout.md
```

Example:

```text
0.1.0_architecture_runtime_reconnaissance_prompt.md
0.1.0_architecture_runtime_reconnaissance_closeout.md
```

A new arc normally starts at `.0`.

Follow-ups increment `.1`, `.2`, `.3`, etc.

Use the same basename.

Do not invent another closeout filename.

Do not create extra human-authored report files unless requested.

---

# 12. Prompt Addenda and Q&A

When requested, append Coder questions, Product Owner answers, and final lock-ins to the same prompt.

Recommended structure:

```markdown
## Original Prompt

## Coder Questions / Answers Round 1

## Coder Questions / Answers Round 2

## Final Lock-ins
```

The active prompt may remain dirty during implementation when:

- it was committed before handoff;
- only expected Q&A/addenda changed;
- Product Owner confirms this is intentional.

Stop and ask when an addendum materially changes:

- scope;
- milestone mode;
- original-media behavior;
- NAS authority;
- deletion/cleanup;
- network/public exposure;
- service/package authority;
- RVE/TensorRT integration;
- persistence architecture;
- security boundary;
- implementation architecture;
- prompt filename;
- closeout filename.

---

# 13. Core Architecture Rules

These rules are mandatory unless a milestone explicitly changes them.

---

## 13.1 Browser-First Operator Experience

Normal Product Owner operation should occur through the Windows browser.

The application should hide routine Linux paths and shell commands.

CLI/RDP may remain available for:

- diagnostics;
- recovery;
- development;
- validation.

Do not design routine product operation around shell access unless explicitly approved.

---

## 13.2 Original Media Preservation

Do not modify original DVD-rip media in place.

Never automatically:

- overwrite;
- rename;
- truncate;
- rewrite;
- delete;
- repair;
- replace.

Originals are read-only inputs from this application’s perspective.

---

## 13.3 Working Candidate Separation

Preparation and enhancement outputs must be distinct from original source media.

Preferred model:

```text
NAS original
→ server-local prepared input
→ server-local enhanced candidate
→ validation
→ controlled NAS publish
```

Do not publish incomplete output.

---

## 13.4 Controlled Publication

Final NAS publication requires an approved authority boundary.

The implementation must prevent:

- path escape;
- original overwrite;
- silent existing-version overwrite;
- partial/incomplete final files;
- broad recursive deletion.

Publication conflicts should stop for Product Owner decision.

---

## 13.5 Proven Processing Tools

Prefer wrapping validated tools:

```text
ffprobe
ffmpeg
RVE backend
TensorRT
NVENC
system telemetry sources
```

Do not reimplement mature media engines without a documented requirement.

---

## 13.6 RVE Integration

The long-term preferred direction is direct backend integration, not desktop-GUI automation, if the installed RVE backend provides a safe usable boundary.

Do not modify the installed RVE/TensorRT environment unless explicitly authorized.

Do not assume an undocumented backend contract without reconnaissance.

---

## 13.7 Interlace / Progressive Decision

Do not rely on `ffprobe field_order` alone.

Actual-content analysis is required.

The application should distinguish at minimum:

```text
progressive
interlaced_tff
interlaced_bff
telecine_suspected
ambiguous
unsupported
```

Ambiguous states must not silently proceed through a destructive transform.

---

## 13.8 GPU-First Encoding Direction

Current validated default direction:

```text
preparation: NVENC
AI inference: TensorRT
final encode: NVENC
```

CPU `libx264` should not be reintroduced as the normal default without an explicit reason and validation.

---

## 13.9 Shared-Host Protection

The helper shares `henderson-server1` with other workloads.

Do not:

- reboot the server;
- stop unrelated services;
- kill broad process patterns;
- rebuild unrelated containers;
- modify unrelated directories;
- change public Jellyfin/Caddy behavior;
- alter GPU/system drivers;

unless explicitly authorized.

Job cancellation must target only processes owned by that job.

---

## 13.10 Security Boundary

The browser UI must not become an arbitrary shell or arbitrary filesystem interface.

Required direction:

- approved source/destination roots;
- validated paths;
- parameterized subprocess invocation;
- no raw shell string execution from user input;
- no exposure of secrets;
- LAN-only access unless explicitly changed.

---

# 14. Job State and Persistence Rules

If durable job state is introduced:

- keep the model small;
- persist enough information to understand completed/failed/interrupted jobs;
- do not introduce a generic workflow engine;
- distinguish running, failed, canceled, validated, published states;
- reconcile stale `RUNNING` jobs after restart;
- never infer a successful publish solely from a stale state flag;
- do not add migrations/schema complexity without milestone scope.

Persistence technology should follow approved reconnaissance.

---

# 15. Cancellation and Process Ownership

Cancellation is safety-sensitive.

A cancellation implementation must:

- terminate only the job-owned process tree;
- avoid broad `pkill` patterns;
- preserve diagnostic evidence;
- mark incomplete output appropriately;
- prevent incomplete publication;
- support clean retry;
- handle browser disconnect separately from job cancellation unless explicitly designed otherwise.

If process ownership cannot be made precise, escalate.

---

# 16. Media Validation Rules

Do not declare a media candidate valid solely because the process exited with code 0.

Validation should consider, as applicable:

- output exists;
- output is non-zero;
- `ffprobe` succeeds;
- expected video codec;
- expected geometry;
- expected progressive/interlace state;
- duration tolerance;
- audio streams;
- subtitle streams;
- chapters;
- language/title tags;
- no obvious processing failure;
- source and candidate are distinct files.

Use status categories such as:

```text
PASS
WARNING / REVIEW REQUIRED
FAIL
```

Do not hide warnings merely to allow publication.

---

# 17. Thermal and Resource Rules

Thermals are part of product behavior.

When telemetry work is in scope, expose or record:

- CPU temperature;
- GPU temperature;
- GPU utilization;
- VRAM usage;
- elapsed time;
- job stage;
- maximum observed temperatures when feasible.

Do not invent automatic shutdown/abort thresholds without Product Owner approval.

Visible warnings and clean cancellation should precede more aggressive automation.

---

# 18. NAS Rules

NAS access is safety-sensitive.

Unless explicitly authorized:

- do not change mount options;
- do not create/change credentials;
- do not modify Synology permissions;
- do not write into movie folders;
- do not rename/delete movie files;
- do not overwrite existing enhanced versions.

Read-only discovery/probing is acceptable when in scope.

Publication implementation must use the exact approved write boundary.

---

# 19. System Mutation Rules

Unless explicitly authorized, do not:

- install/remove apt packages;
- install/remove Python packages system-wide;
- change NVIDIA/CUDA/TensorRT drivers/runtime;
- modify RVE installation;
- change UFW;
- change Caddy;
- change router forwarding;
- create/modify systemd services;
- change NAS mounts;
- change Docker runtime/containers;
- reboot/shutdown host.

If a dependency is missing, report it and recommend the smallest safe option.

---

# 20. Secrets and Protected Configuration

Do not print or commit:

- NAS passwords;
- mount credentials;
- tokens;
- private keys;
- protected environment files;
- unrelated service secrets.

Use configuration placeholders/examples.

If a milestone needs secret handling, define the mechanism without exposing secret contents.

---

# 21. Validation Standards

Validation should match risk.

Potential validation includes:

- unit tests;
- integration tests;
- fixture-based media metadata tests;
- subprocess argument tests;
- safe short clips;
- browser checks;
- process cancellation checks;
- output stream comparisons;
- duration comparisons;
- runtime health;
- telemetry;
- Product Owner live validation;
- `git diff --check`.

Live full-movie processing requires explicit prompt authority.

Production NAS mutation requires explicit prompt authority.

Never claim validation that was not performed.

---

# 22. Closeout Requirements

The Coder must create exactly one closeout.

Required baseline structure:

```markdown
# Milestone <number> — <title>

## 1. Scope Completed
## 2. Operational Behavior
## 3. Files Changed
## 4. Architecture / State / Persistence Changes
## 5. Media and Authority Boundaries
## 6. Safety Boundaries Preserved
## 7. Validation Performed
## 8. User / Live Validation
## 9. Deviations from Prompt
## 10. Known Limitations
## 11. Recommended Next Milestone
## 12. Git Status
```

When applicable:

```markdown
## Runtime Mutation Record
## Media Integrity Evidence
```

The closeout must identify:

- actual facts;
- assumptions;
- untested behavior;
- deviations;
- known risks;
- exact live mutations, when authorized.

---

# 23. Required First-Response Behavior

When handed a milestone prompt, begin by:

1. confirming repository path;
2. performing read-only Git preflight;
3. confirming milestone mode;
4. identifying required documents/closeouts;
5. inspecting only within approved authority;
6. asking only genuinely blocking questions;
7. proceeding or escalating according to these rules.

Do not treat this rules document alone as authorization to modify the system.

---

# 24. Standing Product Defaults

Unless a milestone explicitly changes them, treat these as current validated starting defaults:

```text
Operator interface:
Windows browser

Original media:
commercial DVD MKV on NAS
immutable from helper

Preparation:
GPU-first
NVENC

AI backend:
TensorRT

Default upscale model:
Nomos8k (Realistic) — Medium Quality Source

Scale:
2x

Interpolate:
Off

Decompress:
Off

Denoise:
Off

Final video encoder:
NVENC H.264

Container:
MKV

Audio:
copy where compatible with workflow

Subtitles:
copy where compatible with workflow

Publication:
separate enhanced version
never overwrite original
```

These are starting defaults, not immutable architecture.

Changes require milestone scope and validation.

---

# 25. Standing Product Safety Summary

The following must remain true unless explicitly changed by the Product Owner:

```text
Originals are never modified.
Incomplete renders are never published as final.
Browser input never becomes arbitrary shell authority.
Paths remain within approved roots.
NAS writes require explicit authority.
Existing final versions are not overwritten silently.
RVE/TensorRT installation is not modified casually.
Cancellation targets only job-owned processes.
Shared-host workloads are protected.
Validation is evidence-based.
Ambiguous media analysis stops for review.
The Coder does not commit/push or mutate live infrastructure without authorization.
```

These rules are the standing safety contract for the project.
