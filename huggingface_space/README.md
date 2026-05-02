---
title: Samil Auto-Flow Auditor
emoji: 🧾
colorFrom: orange
colorTo: gray
sdk: streamlit
sdk_version: "1.36.0"
app_file: app.py
pinned: false
license: mit
short_description: AI-powered IT audit walkthrough generator (Claude Vision + Mermaid)
---

# 🧾 Samil Auto-Flow Auditor

This is the Hugging Face Spaces deployment of the Samil Auto-Flow Auditor — an
AI-powered IT audit walkthrough generator for the revenue (Order-to-Cash) cycle.

## How to demo (no API key needed)

1. In the sidebar, keep **🎬 Demo Mode (API 키 불필요)** selected.
2. Pick one of the 10 industry scenarios (Platform / Manufacturing / Retail /
   E-commerce / Banking / Insurance / SaaS / Telecom / Construction / Pharma).
3. Click **🎬 데모 시나리오 로드**.
4. The dashboard renders:
   - 🚨 Three risk-axis cards (Completeness · SoD · Manual override)
   - 🗺️ A Swimlane Mermaid flowchart — **hover any node or arrow** to see the
     mapped control number and risk description from the RCM
   - 🔍 Per-image vision findings (when the scenario includes evidence images)
   - 🎯 Smart RCM mapping with confidence + explicit GAP flags

## Real Mode (optional)

Switch to **🔌 Real Mode** in the sidebar and paste your Anthropic API key to run
the live 4-stage Claude pipeline against your own narrative + screenshots + RCM.

## Source & docs

Full source and design notes:
<https://github.com/pin9u/ax-node-assignment/tree/claude/initial-setup-RQQMF>

Innovation statement (EN/KO) and architecture details are in the upstream
README.md.
