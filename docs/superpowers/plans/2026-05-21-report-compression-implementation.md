# Report Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce uploaded session report payload size without changing the report content consumed by downstream O*NET role-mapping logic.

**Architecture:** The Electron frontend builds the same plain-text report, compresses its UTF-8 bytes with gzip, base64-encodes the compressed bytes, and sends the compressed value in the existing `report_text` field with explicit metadata. The receiving backend decompresses the field before handing it to its existing parser.

**Tech Stack:** Electron renderer, browser `CompressionStream`, Web Crypto SHA-256, Node smoke test, Python/Node backend decompression examples.

---

### Task 1: Report Envelope Helper

**Files:**
- Create: `ElectronFrontEnd/src/service/reportEnvelope.mjs`
- Test: `ElectronFrontEnd/src/service/reportEnvelope.test.mjs`

- [x] **Step 1: Write the failing test**

Create a Node-runnable test that imports `createCompressedReportEnvelope`, asserts gzip/base64 metadata, gunzips the payload, and confirms the original report text is restored.

- [x] **Step 2: Run test to verify it fails**

Run: `node ElectronFrontEnd/src/service/reportEnvelope.test.mjs`

Expected: failure because `reportEnvelope.mjs` does not exist.

- [x] **Step 3: Write minimal implementation**

Create `createCompressedReportEnvelope(reportText, options)` using `CompressionStream('gzip')`, base64 encoding, and SHA-256 hashing.

- [x] **Step 4: Run test to verify it passes**

Run: `node ElectronFrontEnd/src/service/reportEnvelope.test.mjs`

Expected: `reportEnvelope tests passed`.

### Task 2: Upload Payload Integration

**Files:**
- Modify: `ElectronFrontEnd/src/service/analysisService.js`

- [x] **Step 1: Replace expanded base64 report upload**

Change `seedReport()` so it compresses `buildReportText(analysisResults)` and sends the compressed blob in `report_text`.

- [x] **Step 2: Add metadata fields**

Include `is_compressed`, `compression`, `storage_format`, `content_type`, `encoding`, original/compressed byte sizes, and `report_sha256`.

### Task 3: Backend Contract Documentation

**Files:**
- Create: `docs/report_compression_contract.md`

- [x] **Step 1: Document payload fields**

List the compressed upload metadata and clarify that the decompressed report is the same format as before.

- [x] **Step 2: Add backend decompression snippets**

Provide Python and Node.js examples that support both compressed and old base64-only uploads.
