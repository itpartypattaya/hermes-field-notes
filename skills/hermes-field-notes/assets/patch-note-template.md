---
schema_version: 1
id: {{id}}
title: "{{title}}"
date: {{date}}
updated: {{date}}
type: patch
area: {{area}}
status: active
seen_on: "{{seen_on}}"
verified_identity: "{{identity}}"
verified_at: {{date}}
summary: "<one dense line: what the patch changes in the core and why>"
tags: []
patch_kind: bugfix
patch_short: "<short label, up to ~40 characters>"
patch_what: "<what the patch does, in plain words for the owner: shown on the dashboard>"
patch_script: ""
upstream: ""
upstream_none_reason: ""
---

# {{title}}

The checks live next to this file in `{{id}}.checks.json`: the signs that must be in each core
file after the patch, per core version. They are read, never executed.

## Context
Which core files, which Hermes version, what was wrong or missing.

## Symptom
What happens without the patch, verbatim.

## Root cause
The mechanism in the core: file, function, condition.

## What the patch changes
File by file. Keep the edit small and add a unique marker comment so the check can find it.

## Re-apply
The command that applies the patch again after `hermes update` (an idempotent script: see
`references/patch-scripts.md`). Run it only with the owner's consent.

## How to verify
Beyond the static check: the behaviour that proves the patch works.

## Why not upstream yet
Issue or PR link, or why this stays local (a customization, waiting for review, …).

## Caveats
Versions where the anchors differ, interactions with other patches.
