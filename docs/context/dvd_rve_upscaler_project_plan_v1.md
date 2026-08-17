# DVD RVE Upscaler — Project Plan v1

## Document Status

**Version:** v1  
**Project:** DVD RVE Upscaler / DVD Enhance Assistant  
**Authoritative repository:** `/home/chuck/projects/DVD-RVE-upscaler`  
**Authoritative host:** `henderson-server1`  
**Primary operator interface:** Windows workstation browser  
**Media source of truth:** original commercial-DVD MKV rips on Synology NAS  
**Final media repository:** Synology NAS / Jellyfin movie library  
**Project phase:** foundation and architecture planning before first implementation milestone

---

## 1. Purpose

The purpose of this project is to turn the manually validated DVD enhancement workflow into a safe, guided, browser-based assistant.

The User should not need to remember or type long `ffprobe`, `ffmpeg`, RVE backend, TensorRT, NVENC, file-copy, or naming commands during normal use.

The target experience is:

```text
Open browser
→ choose a DVD movie already ripped to NAS
→ Analyze
→ review a friendly media assessment
→ Prepare
→ Enhance
→ monitor progress / temperatures
→ validate output
→ publish the enhanced version to the movie's NAS folder
→ compare Original vs Enhanced in Jellyfin
```

The application should hide implementation-level CLI details while preserving the ability to inspect logs and exact commands when troubleshooting.

---

## 2. Product Owner Workflow Boundary

### User continues to handle

1. Insert commercial DVD.
2. Rip the main movie with MakeMKV.
3. For multi-disc or two-sided titles, combine parts when required before enhancement.
4. Place the original MKV into the appropriate movie folder on the NAS.
5. Use the browser-based DVD Enhance Assistant for analysis, preparation, enhancement, validation, and publication.
6. Review Original vs Enhanced in Jellyfin.
7. Decide whether to retain both versions.

### Assistant should eventually handle

- discovery of eligible MKV files;
- media analysis;
- actual-content interlace/progressive analysis;
- aspect-ratio normalization;
- required preparation encode;
- RVE/TensorRT invocation;
- output encoding through NVENC;
- progress reporting;
- thermal / GPU status;
- validation of duration, streams, geometry, and output integrity;
- Jellyfin-compatible output naming;
- controlled final publication to NAS;
- safe cleanup of approved temporary working files.

---

## 3. Established Environment

### Windows workstation

Primary role:

- Product Owner workstation;
- browser client for the application;
- VS Code client;
- VS Code Remote SSH client;
- administrative access when needed;
- MakeMKV host for ripping physical DVDs.

Normal application use should not require Windows PowerShell or SSH.

### Linux mini-server — `henderson-server1`

Primary role:

- authoritative Git repository;
- web application runtime;
- media analysis;
- FFmpeg preprocessing;
- NVIDIA GPU compute;
- TensorRT inference;
- NVENC encoding;
- local fast working storage;
- job monitoring;
- Cockpit-based host observation.

### Synology NAS

Primary role:

- durable storage of original DVD rips;
- durable storage of final enhanced versions;
- Jellyfin movie repository.

Original rips are source media and must never be overwritten by the helper.

---

## 4. Validated Manual Workflow and Technical Findings

The project begins with a manually validated workflow, not a hypothetical one.

### 4.1 Original media

Commercial DVDs are ripped to MKV with MakeMKV.

The original should remain intact and identifiable as the original version.

Recommended Jellyfin naming:

```text
Movie Name (Year)/
├── Movie Name (Year) - DVD Original.mkv
└── Movie Name (Year) - DVD RVE Medium 2x.mkv
```

The assistant should derive the enhanced filename from the movie folder / selected original when possible and allow confirmation before publication.

### 4.2 Metadata alone is not sufficient to decide deinterlacing

A key finding from manual testing:

- `ffprobe` may report an interlaced field-order flag such as `tt`;
- actual frame analysis can still show the content is progressive;
- therefore the helper must not automatically deinterlace solely because `ffprobe` reports an interlaced field order.

The application should use actual-content analysis, not metadata alone.

### 4.3 Progressive content

When content analysis indicates the movie is progressive:

- do not apply deinterlacing;
- normalize anamorphic DVD geometry to square pixels;
- for the validated NTSC widescreen case:
  - source: 720×480 anamorphic;
  - prepared input: 854×480;
  - SAR: 1:1;
  - approximately 16:9 DAR;
  - mark output frames progressive.

Validated filter shape:

```text
scale=854:480,setsar=1,setfield=prog
```

The exact transformation must be derived from the detected source geometry rather than hard-coded for every DVD.

### 4.4 Truly interlaced content

When content analysis establishes true interlacing:

- use a high-quality deinterlacing path;
- preserve the correct field order;
- produce progressive square-pixel output suitable for RVE.

`bwdif` is the currently validated deinterlacing family from manual testing.

The application must not assume all commercial DVDs require deinterlacing.

### 4.5 Telecine / ambiguous cadence

Film-origin NTSC DVD may require different handling from true interlacing.

The project must explicitly distinguish:

```text
progressive
true interlaced
telecined / cadence-based
ambiguous
```

Until automated telecine detection and inverse-telecine handling are validated, ambiguous or cadence-sensitive sources should stop for operator review rather than silently choosing a destructive conversion.

### 4.6 Preparation encode

CPU `libx264` preparation produced unnecessarily high CPU temperatures during manual testing.

GPU NVENC preparation was dramatically faster and materially reduced CPU load.

Therefore the preferred preparation encoder is:

```text
h264_nvenc
```

A validated starting quality shape is:

```text
preset p7
VBR
CQ 16
audio copy
subtitle copy
metadata / chapter preservation
```

Exact encoder settings should be documented and versioned in application configuration rather than scattered through UI code.

### 4.7 RVE enhancement baseline

The manually validated preferred baseline for commercial DVDs is:

```text
Backend: TensorRT
Upscale model: Nomos8k (Realistic) — Medium Quality Source
Scale: 2x
Interpolate: Off
Decompress: Off
Denoise: Off
```

Medium was visually preferred as the default for commercial DVD material.

Low Quality Source should remain available as an operator override for unusually poor transfers.

High Quality Source may be retained as an advanced option but should not be the normal default for DVD.

### 4.8 Final RVE output encoder

RVE was initially using CPU `libx264` after TensorRT inference.

That caused sustained CPU temperatures near the processor's thermal ceiling.

Changing the RVE final encoder to NVIDIA NVENC substantially reduced sustained CPU temperature.

Therefore the preferred output encoder is:

```text
h264_nvenc
```

Validated RVE encoder shape:

```text
-c:v h264_nvenc
-cq:v 18
-preset p4
-pix_fmt yuv420p
audio copy
subtitle copy
MKV container
```

These values are a validated baseline, not an immutable forever policy.

### 4.9 Output validation

Before final publication, the assistant should verify at minimum:

- output file exists and is non-zero;
- expected video codec;
- expected resolution;
- square-pixel SAR where intended;
- progressive output;
- expected frame rate;
- duration close to original;
- audio stream count and basic characteristics;
- subtitle stream count and basic characteristics;
- language/title tags when available;
- chapters preserved when applicable;
- output is probeable by FFmpeg;
- no obvious backend failure occurred.

The helper should clearly distinguish:

```text
PASS
WARNING / REVIEW REQUIRED
FAIL
```

---

## 5. User Experience Goal

The normal user should see product concepts, not shell concepts.

### Main browser workflow

#### Step 1 — Select Movie

Browser page presents eligible original MKV files from approved NAS roots.

Example:

```text
The Usual Suspects (1995)
Schindler's List (1993)
...
```

The user should not need to type Linux paths.

Useful display fields:

- movie folder;
- filename;
- size;
- runtime;
- current enhancement status;
- whether an enhanced version already exists.

#### Step 2 — Analyze

Click:

```text
Analyze
```

Friendly output example:

```text
Source: DVD MPEG-2
Resolution: 720×480 anamorphic
Display shape: 16:9
Frame rate: 29.97
Content analysis: Progressive
Audio: English AC-3 5.1
Subtitles: English
Chapters: 40

Recommended preparation:
Normalize to 854×480 square-pixel progressive video.
No deinterlacing required.
```

If truly interlaced:

```text
Content analysis: Interlaced — Top Field First
Recommended preparation:
Deinterlace with approved high-quality profile.
```

If ambiguous:

```text
Content analysis: Review required
Reason: metadata and frame analysis disagree / telecine cadence suspected
```

No enhancement should begin while status is Review Required.

#### Step 3 — Prepare

Click:

```text
Prepare for Enhancement
```

The program:

- chooses the validated preparation profile;
- writes to an approved working location;
- preserves media streams and chapters;
- uses NVENC by default;
- shows progress and status;
- validates the prepared file.

The user should not have to supply an FFmpeg command.

#### Step 4 — Enhance

Click:

```text
Enhance DVD
```

Default profile:

```text
Commercial DVD — Balanced
TensorRT
Nomos8k Medium
2x
NVENC H.264 output
```

Advanced settings may expose:

- Low / Medium / High source model;
- output quality;
- optional destination filename.

Advanced controls should be collapsed by default.

#### Step 5 — Monitor

Display:

```text
Stage: Enhancing
Progress: 43%
Elapsed: 48 min
Estimated remaining: 1 hr 04 min

CPU: 84°C
GPU: 67°C
GPU utilization: 82%
VRAM: 7.4 GB
```

Logs should be available through a secondary diagnostic panel.

#### Step 6 — Validate

On completion, show:

```text
Video: PASS
Runtime: PASS
Audio streams: PASS
Subtitle streams: PASS
Chapters: PASS
Geometry: PASS

Ready to publish.
```

Warnings should be explicit.

#### Step 7 — Publish

Display proposed final path and filename.

Example:

```text
Schindler's List (1993) - DVD RVE Medium 2x.mkv
```

Require explicit operator confirmation before writing the final version into the durable movie library.

#### Step 8 — Jellyfin Review

Provide a simple completion message:

```text
Published successfully.
Jellyfin can now present DVD Original and DVD RVE Medium 2x as versions.
```

Automatic Jellyfin library refresh may be a later milestone if desired.

---

## 6. Recommended Architecture

The architecture should remain deliberately small.

### 6.1 Browser UI

Recommended direction:

- LAN-only web application;
- opened from the Windows browser;
- no normal RDP requirement;
- no normal CLI requirement.

A lightweight server-rendered interface is preferred over a large SPA unless reconnaissance demonstrates a clear reason for a more complex frontend.

Candidate implementation:

```text
Python
FastAPI or similar small web framework
server-rendered templates
small amount of JavaScript / HTMX-style interaction
```

This is a recommendation for reconnaissance to confirm, not a mandate to add unnecessary frameworks.

### 6.2 Backend orchestration

The backend should wrap established command-line tools rather than reimplement media processing:

```text
ffprobe
ffmpeg
RVE backend / TensorRT
nvidia-smi or NVIDIA telemetry
lm-sensors / approved thermal source
```

The web application owns orchestration and state.

The actual media tools remain the processing authorities.

### 6.3 RVE integration

Long-term preferred direction:

```text
web application
→ invoke RVE backend directly
→ TensorRT
→ Nomos8k
→ NVENC
```

This is preferable to browser automation of the RVE desktop GUI.

The desktop RVE GUI remains a useful manual recovery / comparison tool.

The first reconnaissance milestone must inspect the installed RVE 2.4.1 backend and determine the cleanest supported invocation boundary before implementation commits to it.

### 6.4 Working storage

Preferred default:

```text
Original: NAS, immutable
Working / prepared input: server NVMe
RVE output before validation: server NVMe
Final validated output: NAS
```

This protects the NAS library from incomplete renders and avoids forcing RVE to write directly into the durable movie folder.

The browser can still present this as one guided workflow; the operator should not need to manage working paths.

### 6.5 NAS authority

The existing movie library should not be made broadly read/write merely for convenience.

The project should establish a controlled publication path.

Reconnaissance should decide among:

- a narrowly scoped NAS writer credential;
- a dedicated write-capable mount used only by the helper;
- a controlled publish subprocess/service;
- another simple mechanism that preserves read-only normal Jellyfin / source access.

Requirements:

- originals never overwritten;
- existing enhanced version never overwritten silently;
- final publish is atomic or equivalent where practical;
- partial output must not appear as a completed movie;
- deletion is never implicit;
- conflicts stop for operator decision.

---

## 7. Processing State Model

The application should make the job state understandable.

Suggested states:

```text
DISCOVERED
ANALYZING
REVIEW_REQUIRED
READY_TO_PREPARE
PREPARING
PREPARED
READY_TO_ENHANCE
ENHANCING
VALIDATING
VALIDATION_WARNING
READY_TO_PUBLISH
PUBLISHING
COMPLETE
FAILED
CANCELED
```

State transitions should be explicit.

A browser refresh or service restart should not make an active/completed job impossible to understand.

A small durable job-state store is likely appropriate.

SQLite is a reasonable candidate for v1 if persistence is needed, but reconnaissance should confirm the smallest safe option.

---

## 8. Media Analysis Requirements

The analyzer should gather and retain structured evidence.

### Metadata analysis

Use `ffprobe` to capture:

- container;
- codec;
- duration;
- width/height;
- sample aspect ratio;
- display aspect ratio;
- field order;
- frame rate;
- bit depth;
- audio streams;
- subtitle streams;
- chapters;
- language/title tags.

### Frame-content analysis

Use an approved content-analysis profile.

For interlace/progressive detection:

- sample multiple positions distributed across the movie;
- do not rely on only the first few seconds;
- do not trust field-order metadata alone;
- retain summarized evidence from each sample;
- if samples materially disagree, stop for review.

### Decision categories

```text
progressive
interlaced_tff
interlaced_bff
telecine_suspected
ambiguous
unsupported
```

Preparation may proceed automatically only for validated decision categories with an approved transform.

---

## 9. Thermal and Resource Safety

Thermal behavior is part of this project's product requirements.

### Established lesson

CPU-based x264 during preparation and RVE output encoding generated unnecessarily high CPU temperatures.

NVENC materially improved the thermal profile.

### V1 requirements

The application should:

- show CPU temperature;
- show GPU temperature;
- show GPU utilization;
- show VRAM usage;
- show job elapsed time;
- record observed maximum temperatures for the job.

### Guardrail policy

Do not invent an aggressive automatic shutdown threshold without reconnaissance and Product Owner approval.

Initial safe behavior should be:

- visible warning at configured threshold;
- clear job status;
- ability to cancel cleanly.

A later milestone may support automatic pause/abort if validated.

---

## 10. Cancellation and Recovery

The application must support:

```text
Cancel current stage
```

Cancellation should:

- stop only the job's own FFmpeg / RVE backend process tree;
- not kill unrelated server workloads;
- retain enough state/logging to diagnose the stop;
- mark incomplete output as incomplete;
- never publish an incomplete file.

After restart:

- completed jobs remain visible;
- failed jobs remain visible;
- stale RUNNING jobs are reconciled to interrupted/failed status;
- the user can retry safely.

---

## 11. Original and Output Integrity Rules

Mandatory:

1. Original DVD MKV is immutable from this application's perspective.
2. Never rename, replace, rewrite, truncate, or delete the original automatically.
3. Never overwrite an existing final enhanced version without explicit Product Owner action.
4. Working files must be distinct from source/final files.
5. Final publish occurs only after validation.
6. Failure must preserve evidence rather than silently retrying forever.
7. Cleanup of working files must be explicit and bounded.
8. No broad recursive NAS deletion.
9. No shell command may be constructed from unvalidated user input.
10. File selection must remain inside approved roots.

---

## 12. Security and Network Exposure

The helper is an administrative LAN application.

V1 should:

- bind only to an approved LAN interface/address;
- be allowed through UFW only from the home LAN if a firewall rule is required;
- not be exposed through the public Jellyfin/Caddy route;
- not expose RVE, shell, or arbitrary filesystem access to the browser;
- validate selected paths against approved media roots;
- avoid returning secrets or mount credentials through logs/UI.

Authentication requirements should be decided during reconnaissance.

---

## 13. Logging and Evidence

For every job retain:

- selected source;
- source probe summary;
- frame-analysis summary;
- chosen preparation decision;
- exact processing profile/version;
- RVE backend;
- model;
- scale;
- encoder;
- start/end time;
- exit status;
- validation summary;
- temperature maxima when available;
- final published path;
- failure message when applicable.

The UI may hide raw command syntax by default, but diagnostic logs should make the executed command reconstructable.

---

## 14. Configuration

Avoid scattering operational constants through code.

Use a project configuration layer for:

```text
approved NAS source roots
working directory
approved final destination root
RVE installation path
RVE backend path
TensorRT profile
default upscale model
default scale
preparation NVENC profile
final NVENC profile
thermal warning threshold
job-log location
```

Secrets and NAS credentials must not be committed to Git.

---

## 15. Proposed Repository Structure

Subject to reconnaissance:

```text
/home/chuck/projects/DVD-RVE-upscaler/
├── README.md
├── docs/
│   ├── context/
│   │   ├── dvd_rve_upscaler_project_plan_v1.md
│   │   ├── project_workflow_v1.md
│   │   └── coding_agent_rules_v1.md
│   └── milestones/
│       └── ...
├── app/
│   ├── web/
│   ├── media/
│   ├── jobs/
│   ├── rve/
│   └── system/
├── tests/
├── scripts/
├── config/
└── pyproject.toml
```

Do not create structure merely to match this sketch if reconnaissance identifies a simpler layout.

---

## 16. Milestone / Prompt → Closeout Workflow

This project should use the established disciplined workflow:

```text
ChatGPT / Architect drafts milestone prompt
→ Product Owner reviews
→ prompt saved and committed
→ Coder reads rules + prompt
→ Git preflight
→ Coder asks blocking questions
→ Product Owner / ChatGPT locks decisions
→ Coder implements only approved scope
→ Coder validates
→ Coder creates exactly one closeout
→ Product Owner performs real-world test when required
→ Product Owner authorizes/stages/commits/pushes
→ next milestone
```

### Suggested filename standard

```text
<milestone>_<snake_case_name>_prompt.md
<milestone>_<snake_case_name>_closeout.md
```

Example:

```text
0.1.0_architecture_runtime_reconnaissance_prompt.md
0.1.0_architecture_runtime_reconnaissance_closeout.md
```

Follow-ups:

```text
0.1.1
0.1.2
...
```

A new arc may begin at:

```text
0.2.0
0.3.0
...
```

### Coder authority

Unless a prompt explicitly authorizes it, the Coder must not:

- commit or push;
- create/switch/delete branches;
- mutate NAS content;
- change NAS mounts;
- change UFW/firewall;
- expose new public ports;
- install/remove system packages;
- modify the existing RVE/TensorRT installation;
- create/modify system services;
- delete media;
- overwrite original or final media.

Read-only inspection is normally acceptable when within prompt scope.

---

## 17. Proposed Milestone Roadmap

The milestone sequence should remain adaptable to reconnaissance.

### 0.1.0 — Architecture and Runtime Reconnaissance

Mode: reconnaissance-only.

Determine:

- repository starting state;
- installed RVE layout;
- exact supported RVE backend invocation;
- FFmpeg capabilities;
- TensorRT environment;
- NAS mount topology and permissions;
- safe write/publication design;
- browser application stack;
- job-state persistence needs;
- telemetry sources;
- service/runtime approach;
- test strategy;
- exact implementation roadmap.

No product implementation.

### 0.1.1 — Project Scaffold and Standing Workflow Documents

Create:

- minimal application scaffold;
- project-specific `coding_agent_rules_v1.md`;
- project-specific `project_workflow_v1.md`;
- configuration skeleton;
- baseline tests.

No media mutation.

### 0.2.0 — NAS Movie Discovery and Browser Selection

Implement:

- approved-root scanning;
- safe path model;
- browser movie list;
- original/enhanced recognition;
- read-only metadata display.

No media processing.

### 0.3.0 — Media Probe and Analysis

Implement:

- ffprobe wrapper;
- structured stream metadata;
- distributed `idet` sampling;
- decision classifications;
- browser analysis report;
- ambiguous/review-required behavior.

No preparation or enhancement.

### 0.4.0 — Safe Preparation Pipeline

Implement:

- progressive normalization;
- validated interlace path;
- NVENC preparation;
- stream/chapter preservation;
- local working files;
- preparation validation;
- cancel/retry.

Telecine handling only if reconnaissance/validation has locked a safe policy.

### 0.5.0 — RVE TensorRT Integration

Implement:

- direct RVE backend invocation;
- TensorRT backend;
- Nomos8k Medium 2x default;
- selectable model strength;
- NVENC final output;
- process supervision;
- capture backend errors cleanly.

### 0.6.0 — Job Dashboard and Telemetry

Implement:

- progress;
- elapsed / ETA when feasible;
- CPU temperature;
- GPU temperature;
- GPU utilization;
- VRAM;
- stage status;
- logs;
- cancellation.

### 0.7.0 — Output Validation and Jellyfin Naming

Implement:

- full validation;
- source/output stream comparison;
- duration tolerance;
- final filename proposal;
- conflict detection.

Still no automatic durable publish unless separately approved.

### 0.8.0 — Controlled NAS Publication

Implement:

- approved write authority;
- explicit Publish action;
- conflict-safe behavior;
- final path verification;
- no original overwrite;
- no incomplete publish.

### 0.9.0 — End-to-End Operational Validation

Validate multiple commercial DVDs covering:

- progressive metadata/content agreement;
- metadata/content disagreement;
- true interlaced content;
- different aspect ratios;
- subtitles;
- multi-audio;
- chapters;
- long movie;
- cancellation;
- restart/recovery;
- publish conflict;
- thermal behavior.

### 1.0.0 — Stable DVD Enhance Assistant

Definition:

```text
Rip externally
→ place original on NAS
→ browser chooses movie
→ Analyze
→ Prepare
→ Enhance
→ Validate
→ Publish
→ Jellyfin comparison
```

No routine shell interaction required.

---

## 18. V1 Definition of Done

V1 is complete when the Product Owner can take a normal commercial DVD already ripped to the NAS and, entirely through the browser:

1. find/select the original;
2. analyze its media characteristics;
3. receive a correct progressive/interlace decision or a clear review-required stop;
4. prepare it using the approved GPU-accelerated path;
5. run TensorRT + Nomos8k Medium 2x;
6. use NVENC for final encoding;
7. monitor job progress and temperatures;
8. validate the result;
9. publish under Jellyfin-compatible naming;
10. retain the original untouched;
11. recover meaningfully from errors/cancellation;
12. perform the workflow without manually composing CLI commands.

---

## 19. Explicitly Deferred / Later Possibilities

Not required for initial v1 unless promoted by the Product Owner:

- Blu-ray / UHD enhancement;
- 4K AI upscale;
- AV1 as default final codec;
- automatic MakeMKV control;
- optical-drive automation from Linux;
- automatic disc-side joining;
- remote internet exposure of the helper;
- multi-user access;
- scheduled bulk processing;
- automated deletion of originals;
- automated replacement of originals;
- automatic Jellyfin metadata management;
- advanced model benchmarking;
- batch queue across the entire library;
- arbitrary user-provided FFmpeg/RVE command editing.

---

## 20. First Recommended Action

Begin with:

```text
Milestone 0.1.0 — Architecture and Runtime Reconnaissance
```

The first Coder milestone should be read-only except for the required closeout/documentation.

Its purpose is to convert the manually established workflow and this project plan into an implementation roadmap grounded in the actual new repository, installed RVE backend, server runtime, and NAS access boundaries.
