# PROJECT_WORKFLOW_v1.md — DVD RVE Upscaler

## Document Status

**Version:** v1  
**Project:** DVD RVE Upscaler / DVD Enhance Assistant  
**Project phase:** foundation and architecture reconnaissance  
**Authoritative repository:** `/home/chuck/projects/DVD-RVE-upscaler`  
**Authoritative host:** `henderson-server1`  
**Primary operator interface:** Windows workstation browser  
**Current architecture direction:** Windows operator/browser + Linux authoritative repository/runtime + Synology NAS original/final media storage  
**Current workflow emphasis:** milestone discipline, reconnaissance as implementation roadmap, simple architecture, evidence-based media validation, original-media protection, controlled NAS publication, GPU-first processing, thermal awareness, clean Git history, and low-CLI operator experience.

---

# 1. Purpose

This document defines the working collaboration model between:

- **User / Product Owner**
- **ChatGPT / Architect and Planner**
- **Coder / Implementation Agent**

The workflow exists to keep development:

- milestone-driven;
- safe;
- understandable;
- well documented;
- portable across chats and tools;
- resistant to scope drift;
- resistant to mixed commits;
- aligned with the validated manual DVD enhancement workflow;
- protective of original media;
- explicit about NAS write authority;
- explicit about server/runtime authority;
- explicit about which machine and terminal are involved;
- cost-aware when using AI coding agents;
- suitable for a small maintainable home-server application.

The Product Owner remains the final decision maker.

The desired product outcome is a browser-driven assistant that removes routine dependence on CLI commands while preserving transparent diagnostics when needed.

---

# 2. Working Principles

The project is governed by these principles:

```text
Validate architecture before implementation when risk is unclear.
Use reconnaissance before coding when runtime or integration reality is uncertain.
Build around the manually proven workflow.
Prefer the smallest safe architecture.
Protect original media.
Do not publish incomplete or unvalidated output.
Use GPU acceleration where validated and appropriate.
Treat thermals and shared-host impact as real product constraints.
Use browser concepts for normal operation and CLI detail for diagnostics.
Keep Git history clean and milestone-scoped.
Escalate rather than improvise through unresolved architecture or safety conflicts.
```

Additional principles:

- Product intent should be translated into explicit implementation outcomes.
- Existing proven tools should be wrapped rather than reimplemented.
- FFmpeg, RVE/TensorRT, NVENC, and system telemetry should remain processing authorities where appropriate.
- The web application should orchestrate; it should not duplicate mature media engines.
- A milestone must not silently broaden into a different milestone.
- Validation-only work must not silently become implementation work.
- Live NAS writes require explicit authority.
- Runtime/service/firewall/package changes require explicit authority.
- Original rips are immutable from the application’s perspective.
- The assistant should stop for review when media analysis is ambiguous.
- The Product Owner should not need to remember Linux paths or compose shell commands during normal use.
- Cost should be reduced through focused prompts and targeted reading, not by lowering safety or validation standards.

---

# Part I — Roles and Responsibilities

# 3. User / Product Owner

The User / Product Owner:

- defines product goals and priorities;
- decides intended user behavior;
- approves architecture and workflow decisions;
- approves milestone sequencing;
- saves milestone prompts into the repository;
- provides prompts to the Coder;
- brings Coder questions back to ChatGPT when desired;
- performs or authorizes live media validation;
- reports real-world behavior;
- provides screenshots, logs, and usability feedback;
- confirms milestone completion;
- normally controls Git commits and pushes;
- explicitly authorizes Coder Git write commands when desired;
- explicitly authorizes NAS writes and publication;
- explicitly authorizes firewall, package, service, mount, RVE-installation, Docker, or other live-system mutations;
- decides when a feature branch should merge to `main`;
- decides whether completed feature branches are retained or removed;
- maintains or approves project documentation organization;
- decides when a project chat should move to a new conversation.

The Product Owner is not expected to translate product intent into code-level instructions alone.

ChatGPT and the Coder should make technical implications understandable before asking for a product decision.

---

# 4. ChatGPT / Architect and Planner

ChatGPT:

- helps design architecture;
- helps sequence milestone arcs;
- identifies when reconnaissance is needed;
- identifies when direct implementation is safe;
- writes structured milestone prompts;
- names prompt and closeout files explicitly;
- defines scope and out-of-scope boundaries;
- defines runtime and NAS authority boundaries;
- defines validation evidence;
- identifies the correct command environment;
- anticipates likely Coder questions;
- answers Coder questions decisively;
- distinguishes intended behavior from observed runtime facts;
- interprets Coder closeouts;
- interprets Product Owner testing;
- determines whether a milestone is complete;
- recommends fixes or follow-up milestones;
- recommends Git staging and commit structure;
- recommends branch creation and merge strategy;
- proposes documentation updates;
- prepares continuation-chat handoffs;
- protects original media and shared-host boundaries;
- keeps implementation prompts delta-focused after reconnaissance.

ChatGPT should determine the appropriate milestone mode:

```text
reconnaissance-only
implementation-after-reconnaissance
direct low-risk implementation
validation-only
documentation-only
bug-fix follow-up
deployment / operational validation
```

ChatGPT should also determine the appropriate reasoning level when useful:

```text
high
medium
lower
```

ChatGPT should convert Product Owner intent into implementation-ready scope containing:

```text
strategy
intent
required outcome
current context
repository and environment
scope
out of scope
authority boundaries
media-integrity boundaries
runtime boundaries
validation evidence
stopping conditions
escalation conditions
definition of done
```

ChatGPT should not rely on chat memory alone when current repository documents, prompts, closeouts, code, or runtime evidence are available.

---

# 5. Coder / Implementation Agent

The Coder:

- reads the active milestone prompt;
- reads `docs/context/coding_agent_rules_v1.md`;
- reads the approved reconnaissance closeout when applicable;
- performs Git preflight;
- confirms repository and environment;
- inspects targeted implementation/runtime paths;
- asks clarification questions before implementing uncertain behavior;
- escalates when approved assumptions conflict with code/runtime reality;
- keeps changes tightly scoped;
- avoids speculative refactoring;
- avoids unrelated cleanup;
- preserves existing behavior unless change is explicitly approved;
- validates implementation honestly;
- creates exactly one closeout;
- reports deviations and limitations;
- reports Git state;
- stops before unsafe scope expansion;
- does not run unauthorized Git write commands;
- does not run unauthorized NAS, package, service, firewall, mount, Docker, or destructive runtime changes;
- does not read or print protected secrets without explicit scope and authorization.

The Coder should not:

- reinterpret Product Owner intent without approval;
- replace the validated workflow merely because another approach is technically possible;
- introduce a parallel media engine when existing tools can be wrapped;
- treat browser input as arbitrary shell authority;
- expose unrestricted filesystem access;
- silently change NAS write semantics;
- silently broaden deletion or cleanup behavior;
- silently overwrite original or final media;
- silently add a new persistence architecture;
- repeat broad reconnaissance after an approved roadmap exists;
- continue searching merely to appear thorough;
- modify the working RVE/TensorRT installation without explicit authorization;
- change server networking or public exposure without explicit authorization.

---

# Part II — Project Documentation

# 6. Core Project Documents

The project should remain understandable through:

```text
docs/context/dvd_rve_upscaler_project_plan_v1.md
docs/context/dvd_rve_upscaler_coder_intro_v1.md
docs/context/project_workflow_v1.md
docs/context/coding_agent_rules_v1.md
docs/milestones/<milestone prompt and closeout files>
README.md
current code
tests
operator documentation when later created
```

These documents support:

- transition between chats;
- onboarding a new Coder;
- reduction of reliance on chat history;
- architectural consistency;
- preservation of Product Owner decisions;
- implementation history;
- runtime continuity;
- recovery after long pauses.

Global context documents describe current project truth.

Milestone prompts and closeouts preserve historical milestone truth.

---

# 7. Documentation Authority

When current documents conflict with old chat recollection, prefer:

```text
explicit current Product Owner direction
+ active milestone prompt / approved addenda
+ current repository code
+ current project context documents
+ approved reconnaissance closeout
+ validated runtime evidence
```

over old conversational memory.

Documentation should distinguish:

- implemented behavior;
- validated runtime behavior;
- design direction;
- deferred work;
- assumptions;
- untested behavior.

Not every small milestone requires a global-document update.

Major architectural changes should update the appropriate current context documents.

Historical milestone prompts and closeouts should be preserved.

---

# 8. Milestone Documentation Location

Milestone documentation is stored under:

```text
docs/milestones/
```

A simple structure is preferred.

Example:

```text
docs/milestones/
├── 0.1.0_architecture_runtime_reconnaissance_prompt.md
├── 0.1.0_architecture_runtime_reconnaissance_closeout.md
├── 0.1.1_project_scaffold_and_workflow_prompt.md
└── 0.1.1_project_scaffold_and_workflow_closeout.md
```

Subfolders may be introduced later if the milestone count or arc structure makes them useful.

Do not add folder hierarchy merely for ceremony.

---

# Part III — Prompt and Closeout Standards

# 9. Prompt and Closeout Naming Standard

Every milestone prompt must explicitly state:

- milestone number;
- milestone title;
- exact prompt filename;
- exact closeout filename.

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

Rules:

- no spaces;
- lowercase snake case for the descriptive portion;
- prompt and closeout use the same basename;
- replace `_prompt.md` with `_closeout.md`;
- do not invent a different closeout filename;
- do not create separate human-authored report files unless explicitly requested.

A new milestone arc should normally begin at:

```text
x.x.0
```

Follow-up actions increment:

```text
x.x.1
x.x.2
x.x.3
```

The initial planned arc begins at `0.1.0`.

---

# 10. Prompt Composition Standard

A good milestone prompt should define:

```text
title
required filenames
reasoning level
milestone mode
goal
background/current context
authoritative repository
target environment
command execution location
required documents / closeouts to read
scope
out of scope
architecture boundaries
media-integrity boundaries
runtime/NAS authority
backend requirements if applicable
frontend requirements if applicable
persistence requirements if applicable
safety requirements
validation checklist
manual/live validation plan
stopping conditions
escalation conditions
deliverables
definition of done
required closeout structure
recommended next milestone
```

Prompts should describe required behavior and boundaries without unnecessary micromanagement.

Potential tools, libraries, services, or files may be mentioned when helpful.

Do not over-prescribe implementation mechanisms unless:

- the mechanism is part of a safety contract;
- reconnaissance established the exact path;
- a particular existing authority must be reused;
- alternatives would create material risk.

Prompts should be complete enough to execute, but no longer merely because more context exists.

---

# 11. Preferred Prompt Structure

Milestone prompts should generally use:

1. Title
2. Required file names
3. Reasoning level
4. Milestone mode
5. Goal
6. Background and current context
7. Authoritative repository and target environment
8. Required documents / closeouts to read
9. Scope
10. Out of scope
11. Architecture and authority boundaries
12. Media-integrity requirements
13. Backend requirements, if applicable
14. Frontend requirements, if applicable
15. Persistence/job-state requirements, if applicable
16. Runtime/NAS requirements, if applicable
17. Safety boundaries
18. Validation checklist
19. Manual/live validation plan
20. Escalation and stop conditions
21. Deliverables
22. Definition of done
23. Required closeout structure
24. Recommended next milestone

Standing instructions should include:

```text
Read and obey docs/context/coding_agent_rules_v1.md.
Create exactly one closeout document.
Use the exact closeout filename.
Do not run Git write commands unless explicitly authorized.
Do not mutate NAS, firewall, mounts, packages, services, Docker, or RVE/TensorRT state unless authorized.
Never modify original media.
Escalate before materially broadening scope.
```

Safety-sensitive prompts should repeat their most important safety rules directly.

---

# 12. Prompt Handoff Formatting

Coder handoff prompts should be delivered as one complete copyable block whenever practical.

Rules:

- commentary outside the block should be minimal;
- preserve all prompt headings together;
- answers intended for repasting should be self-contained;
- command blocks should identify the execution environment;
- Linux Git operations should be grouped when safe;
- Windows PowerShell should be used only for Windows-specific actions;
- do not scatter a single operation across many disconnected command blocks unless troubleshooting requires observation between steps.

---

# 13. Prompt File Lifecycle

## 13.1 Initial prompt commit

The initial prompt should normally be committed before Coder handoff.

Purpose:

- preserve the original instruction state;
- create a durable implementation baseline;
- reduce ambiguity between coding sessions;
- prevent the active prompt from existing only in chat.

Recommended commit message:

```text
Docs: add <milestone> <short name> prompt
```

## 13.2 Prompt addenda and Coder Q&A

Coder questions and approved answers should be appended to the same prompt.

Recommended headings:

```markdown
## Original Prompt

## Coder Questions / Answers Round 1

## Coder Questions / Answers Round 2

## Final Lock-ins
```

Minor clarifications do not require a separate commit each time.

It is acceptable for the active prompt to remain modified during implementation when:

- the initial prompt was committed before handoff;
- only expected Q&A/addenda changed;
- the Product Owner confirms this is intentional.

## 13.3 Material prompt changes

A prompt update should be committed before implementation continues when it materially changes:

- milestone scope;
- milestone mode;
- safety boundaries;
- original-media behavior;
- NAS write authority;
- publication behavior;
- deletion/cleanup behavior;
- runtime/service authority;
- firewall/network authority;
- package installation authority;
- RVE/TensorRT integration direction;
- job persistence architecture;
- implementation architecture;
- exact prompt/closeout filename.

## 13.4 Final prompt state

At milestone completion, the prompt should contain:

- original scope;
- material Q&A;
- final lock-ins;
- approved changes to safety or implementation direction.

The final milestone commit normally contains:

```text
implementation files
updated prompt if Q&A/addenda were added
one closeout file
```

---

# 14. Single Closeout File Standard

The Coder should create exactly one human-authored closeout per milestone.

Do not create separate:

```text
report.md
coder_response.md
implementation_notes.md
validation_notes.md
operations.md
```

unless explicitly requested.

Application-generated artifacts remain allowed, such as:

- logs;
- JSON job reports;
- screenshots;
- ffprobe output fixtures;
- media-analysis results;
- runtime diagnostics.

These artifacts should be referenced from the closeout when relevant.

They do not replace the closeout.

---

# 15. Required Closeout Structure

Use this structure unless the prompt explicitly modifies it:

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

For runtime-changing milestones also include:

```markdown
## Runtime Mutation Record
```

For media-processing milestones also include:

```markdown
## Media Integrity Evidence
```

The closeout must distinguish:

- confirmed facts;
- assumptions;
- inferences;
- reconstructed evidence;
- untested behavior.

Never claim validation that was not performed.

---

# Part IV — Milestone Modes

# 16. Reconnaissance-Only Milestone

Use reconnaissance-only when:

- code reality is uncertain;
- runtime integration is uncertain;
- RVE backend behavior needs inspection;
- NAS permissions/publication design is unresolved;
- telemetry sources need confirmation;
- job persistence shape is unresolved;
- architecture crosses several tools/systems;
- a broad UI/orchestration feature is proposed;
- destructive or durable-write implications are unclear.

Reconnaissance may inspect broadly enough to produce a roadmap.

When the prompt says reconnaissance-only:

- do not modify product implementation;
- do not begin coding;
- do not change NAS state;
- do not modify mounts;
- do not change firewall rules;
- do not install/remove system packages;
- do not alter RVE/TensorRT;
- do not create or modify services;
- do not process full production media unless explicitly authorized;
- create the required reconnaissance closeout;
- stop after the required deliverables.

Expected reconnaissance output:

```text
current repository/runtime map
relevant files and tools
RVE integration boundary
FFmpeg/NVENC/TensorRT capability evidence
NAS topology and permissions
authority boundaries
job-state/persistence recommendation
telemetry recommendation
web-stack recommendation
likely files/modules
validation plan
risks/blockers
implementation roadmap
```

Reconnaissance is not merely information gathering.

Its closeout should become the implementation roadmap.

---

# 17. Implementation-After-Reconnaissance Milestone

Use after an approved reconnaissance closeout.

The approved reconnaissance is the primary roadmap.

Recommended reading order:

```text
1. coding_agent_rules_v1.md
2. active implementation prompt
3. approved reconnaissance closeout
4. named implementation files
5. directly related tests
6. broader context only if needed
```

Implementation should:

- verify roadmap assumptions against current reality;
- inspect only the needed files/services;
- make the smallest safe change;
- reuse proven processing tools;
- avoid reopening settled decisions without evidence;
- stop once required behavior and validation pass.

Do not repeat repository-wide reconnaissance unless:

- repository/runtime state changed materially;
- reconnaissance omitted a required path;
- targeted code contradicts the roadmap;
- tests expose an undocumented dependency;
- a safety/runtime/media-integrity boundary remains unresolved.

When escalating, identify which reconnaissance assumption failed.

---

# 18. Direct Low-Risk Implementation Milestone

A separate reconnaissance milestone is not required for:

- copy-only changes;
- labels;
- narrow styling changes;
- small isolated tests;
- documentation-only edits;
- mechanical corrections;
- small non-destructive bugs with an obvious local cause.

Even for low-risk work:

- inspect the relevant code;
- preserve scope;
- avoid unrelated cleanup;
- run relevant validation;
- create the required closeout.

Do not classify work as low-risk merely because it seems small if it touches:

- NAS publication;
- media deletion;
- original files;
- RVE/TensorRT integration;
- subprocess execution authority;
- arbitrary path handling;
- firewall/network exposure;
- service supervision;
- durable job state;
- cancellation/process ownership;
- package or driver changes.

---

# 19. Validation-Only Milestone

Validation-only milestones establish evidence without changing implementation.

Examples:

- media-analysis validation;
- progressive/interlace classification;
- short-clip preparation validation;
- RVE model/encoder comparison;
- thermal baseline validation;
- cancellation behavior;
- output stream preservation;
- duration tolerance;
- NAS publish rehearsal using controlled test files;
- service restart/recovery;
- browser workflow validation.

In validation-only mode:

- define the target environment;
- define the test matrix;
- define controlled media;
- collect evidence;
- document pass/fail results;
- do not modify implementation code;
- do not silently repair defects;
- do not broaden live mutation authority.

When a defect is found:

1. preserve evidence;
2. classify severity;
3. continue or stop according to the prompt;
4. do not repair unless separately authorized;
5. recommend the smallest follow-up milestone.

A validation milestone must not silently become a repair milestone.

---

# 20. Documentation-Only Milestone

Documentation-only work may update:

- project plan;
- workflow;
- coding-agent rules;
- README;
- operator guides;
- milestone history if later introduced;
- chat handoff documents;
- architecture summaries.

In documentation-only mode:

- do not modify application code;
- verify statements against current code/closeouts/validated runtime evidence;
- distinguish implemented behavior from future direction;
- preserve historical milestone documents;
- create only requested documents;
- do not inspect or mutate live runtime state unless explicitly authorized.

---

# 21. Bug-Fix Follow-Up Milestone

A bug-fix follow-up should remain limited to the documented defect.

Rules:

- reproduce or confirm the defect;
- identify the smallest safe repair;
- preserve existing architecture;
- do not turn the repair into a broad refactor;
- add targeted regression coverage;
- document whether prior validation is affected;
- document retained limitations;
- create one closeout.

A bug fix should not be hidden inside unrelated later work.

---

# 22. Deployment / Operational Validation Milestone

Runtime/deployment work may include:

- application service setup;
- LAN binding;
- firewall rule changes;
- startup/restart behavior;
- logs;
- health checks;
- permissions;
- NAS mounts;
- controlled publication authority;
- runtime recovery;
- backup of application state;
- shared-host protection.

The prompt must define whether the milestone is reconnaissance, implementation, or validation-only.

Do not assume:

- a working shell command implies a safe service architecture;
- existing NAS read access implies write authority;
- existing Jellyfin public exposure means this helper should be public;
- the helper owns the whole server;
- the helper may modify RVE/TensorRT because it uses them.

Silence is not authorization for live mutation.

---

# Part V — Reasoning-Level Guidance

# 23. High Reasoning

Use high reasoning for:

- architecture;
- reconnaissance;
- RVE backend integration;
- NAS publication architecture;
- persistent job-state design;
- process supervision/cancellation;
- security boundary design;
- telecine/interlace policy;
- media-integrity-sensitive transformations;
- thermal safety policy;
- deployment architecture;
- backup/recovery;
- ambiguous cross-system behavior.

High reasoning should produce a concrete roadmap, not endless exploration.

---

# 24. Medium Reasoning

Use medium reasoning for:

- targeted implementation after reconnaissance;
- bounded backend changes;
- bounded frontend changes;
- job-state implementation after architecture is locked;
- test implementation;
- closeout creation;
- implementation debugging;
- targeted validation automation.

Medium reasoning is normally appropriate when:

- architecture is approved;
- authority boundaries are known;
- likely files are identified;
- scope is bounded.

---

# 25. Lower Reasoning

Use lower reasoning for:

- documentation formatting;
- simple copy changes;
- mechanical updates;
- small isolated tests;
- low-risk UI wording;
- simple lint/style fixes.

Do not use lower reasoning merely to reduce cost when runtime, media integrity, or architecture is uncertain.

---

# Part VI — Standard Workflow Cycle

# 26. Step 1 — Milestone Definition

ChatGPT drafts the milestone prompt.

The milestone should state:

- mode;
- reasoning level;
- exact filenames;
- goal;
- context;
- authoritative repository;
- target environment;
- command execution location;
- approved architecture;
- scope;
- out of scope;
- authority;
- safety;
- validation;
- escalation;
- definition of done.

The Product Owner reviews and approves the prompt.

---

# 27. Step 2 — Branch and Repository Preflight

Authoritative repository:

```text
/home/chuck/projects/DVD-RVE-upscaler
```

Normal Git/repository commands run in:

```text
VS Code Remote SSH / Linux terminal on henderson-server1
```

Before a substantial arc:

```bash
cd /home/chuck/projects/DVD-RVE-upscaler
git branch --show-current
git status --short
git log --oneline --decorate -5
```

When configured and needed:

```bash
git fetch origin
git rev-parse HEAD
git rev-parse '@{upstream}'
```

For a brand-new repository, missing history/upstream should be reported as initial state rather than treated as a defect.

Normal substantial feature lifecycle:

```text
main
→ new feature branch
→ milestone prompts and implementation
→ arc validation
→ documentation alignment
→ merge to main
→ validate merged main
→ optionally delete branch
```

Do not begin unrelated work on a completed feature branch merely because it exists.

The Coder must not create/switch branches without Product Owner authorization.

---

# 28. Step 3 — Save and Commit Prompt

The Product Owner saves the prompt under its exact filename.

Recommended sequence in the:

```text
VS Code Remote SSH / Linux terminal
```

is:

```bash
cd /home/chuck/projects/DVD-RVE-upscaler
git status --short

git add -- "docs/milestones/<exact prompt filename>"

git diff --cached --name-only
git diff --cached --stat
git diff --cached --check

git commit -m "Docs: add <milestone> <short name> prompt"
git push

git status --short
```

The staged file list should match the expected prompt file.

Do not use `git add .` unless the full dirty tree has been explicitly approved.

---

# 29. Step 4 — Handoff to Coder

The Product Owner provides the prompt to the Coder.

The Coder:

- reads `coding_agent_rules_v1.md`;
- reads the active prompt;
- reads approved reconnaissance when applicable;
- performs Git preflight;
- confirms repository/environment;
- inspects relevant paths;
- identifies conflicts;
- asks questions or escalates before coding when needed.

---

# 30. Step 5 — Coder Git Preflight

Before editing:

```bash
git branch --show-current
git status --short
git log --oneline --decorate -5
```

Expected state:

```text
correct branch
clean working tree
active prompt committed
```

Allowed exception:

```text
only the active prompt is modified with expected Q&A/addenda
```

Unexpected dirty files must be classified.

Suggested classification:

```text
A. required prior-milestone follow-up
B. unrelated work
C. generated/noise
D. required current-milestone work
```

The Coder must not revert, stage, commit, stash, discard, move, or delete unexpected files without authorization.

---

# 31. Step 6 — Reconnaissance or Targeted Inspection

For reconnaissance, inspect broadly enough to produce the roadmap.

For implementation after reconnaissance, inspect only enough to verify the roadmap and make the targeted change.

Stop broad exploration when:

- the implementation path is known;
- relevant authority is confirmed;
- affected persistence/state is understood;
- media-integrity impact is understood;
- target environment is confirmed;
- shared-host impact is understood;
- required files are identified;
- validation is defined;
- further searching is unlikely to change the plan.

Do not stop while any material uncertainty remains about:

- original-file protection;
- NAS publication;
- failure behavior;
- process ownership/cancellation;
- arbitrary path/shell authority;
- persistent job state;
- telecine/interlace handling;
- runtime/service effects;
- shared-host impact.

---

# 32. Step 7 — Clarification Loop

Coder asks targeted questions.

The Product Owner may bring them to ChatGPT.

ChatGPT responds with:

- direct product decisions;
- architecture lock-ins;
- explicit deferrals;
- stopping conditions;
- answers concise enough to paste back.

Material answers should be appended to the active prompt.

Questions revealing a material scope/architecture change should trigger a prompt update and possibly a new prompt commit.

---

# 33. Step 8 — Escalation Protocol

Escalation is required when:

- current code/runtime contradicts approved architecture;
- safe implementation requires a materially different framework;
- safe implementation requires new persistence not approved;
- RVE backend does not provide the assumed integration boundary;
- NAS publication requires an unapproved mount/credential/permission change;
- arbitrary browser input would gain shell/filesystem authority;
- original media could be modified or overwritten;
- a final output could overwrite an existing version without explicit Product Owner decision;
- telecine/ambiguous cadence requires a policy not yet approved;
- cancellation cannot be limited to job-owned processes;
- implementation is materially larger than represented;
- shared-host impact is materially larger than represented;
- live validation cannot be performed;
- unrelated dirty files threaten commit isolation;
- firewall/service/package/RVE/TensorRT mutation is needed without authorization;
- a product decision is required.

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

Stop at the escalation point.

Do not improvise around it.

---

# 34. Step 9 — Implementation

The Coder implements according to:

- active prompt;
- approved reconnaissance;
- Q&A;
- final lock-ins;
- standing rules.

The Coder should:

- change only required files;
- reuse proven processing tools;
- avoid speculative refactoring;
- avoid unrelated formatting;
- preserve behavior unless explicitly changed;
- add focused tests;
- document deviations;
- keep generated artifacts out of commits unless required;
- avoid Git write commands unless authorized;
- avoid runtime mutation unless authorized;
- preserve original media;
- preserve shared-host boundaries.

---

# 35. Step 10 — Coder Validation

Validation may include:

- targeted unit tests;
- integration tests around subprocess wrappers;
- ffprobe parsing fixtures;
- safe short-media fixtures;
- browser checks;
- API checks;
- subprocess exit-code tests;
- cancellation tests;
- output stream comparison;
- duration comparison;
- thermal telemetry checks;
- service health checks;
- `git diff --check`.

Validation should match milestone risk.

Examples:

- a label change does not require a full RVE render;
- media-analysis logic should be validated against representative samples;
- RVE integration should use short controlled clips before full movies;
- NAS publication should be validated with controlled files before production movie writes;
- destructive cleanup changes require explicit bounded tests.

---

# 36. Step 11 — Closeout Document

The Coder creates exactly one closeout using the exact filename.

The closeout records:

- actual implementation;
- actual files;
- actual validation;
- affected runtime;
- authorized live mutations;
- media-integrity evidence;
- deviations;
- limitations;
- unresolved questions;
- Git state.

Do not claim validation that did not occur.

---

# 37. Step 12 — Product Owner Testing

The Product Owner tests behavior in the approved target environment when required.

Examples:

- browser usability;
- movie discovery;
- analysis report clarity;
- interlace/progressive decision;
- preparation behavior;
- RVE enhancement;
- temperature observations;
- output quality;
- Jellyfin version presentation;
- publication workflow.

The Product Owner reports results to ChatGPT.

---

# 38. Step 13 — Review and Milestone Decision

ChatGPT reviews:

- Coder closeout;
- Product Owner test evidence;
- deviations;
- limitations;
- Git state.

Possible outcomes:

```text
complete
complete with deferred limitation
small follow-up required
validation failed
reconnaissance required
scope/architecture must be revised
```

Do not close a milestone merely because code was written.

---

# 39. Step 14 — Product Owner Git Commit / Push

After milestone acceptance, the Product Owner usually performs Git write commands.

Preferred exact-file staging:

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

Then commit/push after reviewing the staged set.

Do not mix unrelated files.

---

# 40. Step 15 — Documentation Updates

Potential updates:

- project plan;
- coder intro;
- project workflow;
- coding-agent rules;
- README;
- operator guide;
- milestone prompt/closeout;
- architecture summary;
- future milestone history / parking lot if introduced.

When replacing a versioned global document:

```text
create new version
review it
stage new version
stage superseded version removal if appropriate
verify exact paths
run whitespace check
commit together
```

Do not delete historical milestone prompts and closeouts.

---

# 41. Step 16 — Arc Completion and Merge

A substantial feature branch should merge only after:

- final milestone passes;
- closeout is complete;
- relevant context docs are aligned;
- working tree is clean;
- branch is pushed;
- Product Owner considers behavior acceptable.

Conceptual sequence:

```text
finish feature branch
→ update main
→ merge feature branch
→ inspect graph
→ push main
→ validate application from main
```

Do not begin the next unrelated arc before confirming the merge result.

---

# 42. Step 17 — Post-Merge Validation

Before declaring a major arc closed, confirm:

```text
authoritative repository path is correct
current branch is main
working tree is clean
main contains the merge
origin/main matches local main when remote exists
affected application/runtime is running the merged code
health checks pass
targeted browser workflow passes
media safety boundaries remain correct
```

Git correctness and runtime correctness are separate.

A correct merge does not prove the deployed application is using the merged code.

---

# 43. Step 18 — Branch Retention or Cleanup

Deleting a merged branch:

- does not remove merged commits from `main`;
- is optional;
- should occur after merged-main validation.

Recommended practice:

```text
retain briefly
validate main
delete when no longer useful
```

New unrelated work should start from a new branch based on current `main`.

---

# 44. Step 19 — Next Milestone

ChatGPT proposes the next milestone and identifies its category:

- architecture/reconnaissance;
- core feature;
- safety/guardrail;
- media validation;
- UX refinement;
- documentation;
- runtime/deployment;
- stabilization;
- deferred/Parking Lot.

The recommendation should explain why it is logically next.

---

# Part VII — Media Integrity and Runtime Workflow

# 45. Original Media Protection

Original DVD rips are immutable from the helper’s perspective.

A milestone touching source paths must explicitly confirm:

- selected original path;
- approved source root;
- write behavior;
- overwrite behavior;
- cleanup behavior.

Normal rule:

```text
read original
never modify original
write working file elsewhere
validate candidate
publish separate enhanced version
```

Any change to this rule requires explicit Product Owner approval.

---

# 46. Analysis Before Transformation

The application must not infer deinterlacing solely from metadata.

Media-analysis milestones should distinguish:

```text
progressive
interlaced_tff
interlaced_bff
telecine_suspected
ambiguous
unsupported
```

Ambiguous or unsupported states should stop for review.

Do not silently choose a destructive transform merely to keep the workflow moving.

---

# 47. Working Files Before Durable Publication

Preferred model:

```text
NAS original
→ server-local working/prepared file
→ server-local enhanced candidate
→ validation
→ controlled NAS publish
```

Incomplete renders should not appear in the durable movie library as completed versions.

Working-file cleanup should remain bounded and explicit.

---

# 48. Controlled NAS Publication

NAS publication is a durable write.

Before implementation, the approved architecture must define:

- allowed destination root;
- write credential/mount/service authority;
- conflict behavior;
- atomic or equivalent finalization;
- overwrite policy;
- failure behavior;
- cleanup behavior.

Normal rules:

- no original overwrite;
- no silent final-version overwrite;
- no broad recursive writes/deletes;
- no path escape from approved roots;
- incomplete candidates do not become final files.

---

# 49. RVE / FFmpeg Authority

The helper should normally orchestrate:

```text
ffprobe
ffmpeg
RVE backend
TensorRT
NVENC
system telemetry tools
```

instead of reimplementing their core functionality.

The helper owns:

- validated parameter selection;
- job state;
- safe process execution;
- progress/status;
- logging;
- validation;
- publication workflow.

The helper should not become an arbitrary command runner.

---

# 50. Thermal and Shared-Host Safety

The server hosts other workloads.

Thermal and resource behavior must be considered when implementing long-running jobs.

Current validated direction:

- NVENC for preparation;
- TensorRT for AI inference;
- NVENC for final encode;
- CPU temperature visible;
- GPU temperature visible;
- GPU utilization visible;
- VRAM visible;
- clean cancellation supported.

Automatic thermal abort behavior should not be introduced without an approved policy and validation.

---

# Part VIII — Cost-Aware Agent Use

# 51. Reconnaissance Carries Architecture Forward

Reconnaissance is the high-reasoning phase.

Its closeout should identify:

- architecture;
- authority;
- likely files;
- runtime implications;
- validation;
- risks;
- stopping conditions.

Implementation prompts should reference that roadmap instead of repeating it.

---

# 52. Stop Broad Investigation When the Path Is Stable

Stop broad investigation when:

- architecture is understood;
- media authority is understood;
- NAS authority is understood;
- runtime authority is understood;
- persistence needs are understood;
- files/modules are identified;
- validation is defined;
- further searching is unlikely to change the implementation.

Do not continue searching merely to consume more time/tokens.

The objective is the smallest safe and validated change.

---

# 53. Do Not Overbuild

Prefer:

- direct control flow;
- explicit states;
- small helpers;
- focused wrappers;
- simple web UI;
- minimal JavaScript;
- small persistence if needed;
- obvious operator behavior.

Avoid unless required:

- generic workflow engines;
- plugin systems;
- event buses;
- microservices;
- Kubernetes;
- large frontend frameworks;
- speculative abstraction layers;
- custom AI inference stack;
- arbitrary shell interfaces.

Before adding a major abstraction, answer:

1. What current requirement needs it?
2. Why can the simpler approach not satisfy it?
3. What maintenance burden does it add?
4. Does it alter security, media integrity, failure, or runtime authority?
5. Can a direct wrapper or explicit mapping solve the problem?

---

# 54. Workflow Summary

The standard development cycle is:

```text
Product Owner goal
→ ChatGPT milestone prompt
→ prompt saved/committed
→ Coder Git preflight
→ reconnaissance or targeted inspection
→ Coder questions / Product Owner lock-ins
→ implementation
→ Coder validation
→ one closeout
→ Product Owner live test
→ ChatGPT review
→ Product Owner commit/push
→ next milestone
```

For major arcs:

```text
main
→ feature branch
→ milestone sequence
→ arc validation
→ documentation alignment
→ merge
→ merged-main validation
```

The workflow is successful when it produces a browser-driven DVD enhancement assistant that is simple to operate, protects original media, uses the proven GPU-accelerated processing path, and remains understandable and maintainable over time.
