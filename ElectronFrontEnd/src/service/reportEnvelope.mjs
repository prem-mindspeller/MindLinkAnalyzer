const DEFAULT_CONTENT_TYPE = 'text/plain';
const STORAGE_FORMAT = 'gzip+base64+utf8';

function getNodeRequire() {
  if (typeof globalThis.require === 'function') return globalThis.require;
  if (typeof globalThis.window?.require === 'function') return globalThis.window.require;
  return null;
}

function textToUint8Array(text) {
  return new TextEncoder().encode(text);
}

export function uint8ArrayToBase64(bytes) {
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(bytes).toString('base64');
  }
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

async function gzipBytes(bytes) {
  const nodeRequire = getNodeRequire();
  if (nodeRequire) {
    const { gzipSync } = nodeRequire('zlib');
    return new Uint8Array(gzipSync(Buffer.from(bytes)));
  }

  if (typeof CompressionStream !== 'function') {
    throw new Error('This runtime does not support CompressionStream for gzip report packaging.');
  }

  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'));
  const compressed = await new Response(stream).arrayBuffer();
  return new Uint8Array(compressed);
}

async function sha256Hex(bytes) {
  const nodeRequire = getNodeRequire();
  if (nodeRequire) {
    const { createHash } = nodeRequire('crypto');
    return createHash('sha256').update(Buffer.from(bytes)).digest('hex');
  }

  if (!globalThis.crypto?.subtle) {
    throw new Error('This runtime does not support crypto.subtle for report integrity hashing.');
  }

  const hash = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function createCompressedReportEnvelope(reportText, options = {}) {
  const sourceBytes = textToUint8Array(reportText);
  const compressedBytes = await gzipBytes(sourceBytes);

  return {
    report_blob: uint8ArrayToBase64(compressedBytes),
    storage_format: STORAGE_FORMAT,
    content_type: options.contentType || DEFAULT_CONTENT_TYPE,
    encoding: 'utf-8',
    compression: 'gzip',
    is_compressed: true,
    is_base64: true,
    original_size_bytes: sourceBytes.byteLength,
    compressed_size_bytes: compressedBytes.byteLength,
    sha256: await sha256Hex(sourceBytes),
    generated_at: (options.now ? options.now() : new Date()).toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Decode direction -- the inverse of createCompressedReportEnvelope() above,
// mirroring backend eeg_report.decode_report_text()'s envelope contract:
// a stored report is either the envelope JSON this function unwraps
// (is_compressed and/or is_base64 true, with the real payload nested under
// its own report_text key), or already-plain report text with neither flag.
// Used to read back a previously-seeded report (e.g. as a prior_attempt
// reference for repeat-status comparison) -- see priorAttemptService.mjs.
// ---------------------------------------------------------------------------

export function base64ToUint8Array(base64) {
  if (typeof Buffer !== 'undefined') {
    return new Uint8Array(Buffer.from(base64, 'base64'));
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function gunzipBytes(bytes) {
  const nodeRequire = getNodeRequire();
  if (nodeRequire) {
    const { gunzipSync } = nodeRequire('zlib');
    return new Uint8Array(gunzipSync(Buffer.from(bytes)));
  }

  if (typeof DecompressionStream !== 'function') {
    throw new Error('This runtime does not support DecompressionStream for gzip report unpackaging.');
  }

  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const decompressed = await new Response(stream).arrayBuffer();
  return new Uint8Array(decompressed);
}

function uint8ArrayToText(bytes, encoding = 'utf-8') {
  return new TextDecoder(encoding).decode(bytes);
}

/**
 * Decode a report_text value as read back from storage (e.g.
 * GET /api/cas/eeg-reports/<id>/latest) into plain report text.
 *
 * Returns null for falsy input. Throws if the envelope declares a
 * report_sha256 that doesn't match the decoded bytes, or if the payload is
 * malformed (invalid base64/gzip) -- callers reading a prior attempt as an
 * optional enhancement should catch and treat failure as "no prior data
 * available", not block on it.
 */
export async function decodeReportEnvelope(rawReportText) {
  if (!rawReportText) return null;

  let envelope;
  try {
    envelope = JSON.parse(rawReportText);
  } catch {
    // Not JSON at all -- already plain report text.
    return rawReportText;
  }
  if (!envelope || typeof envelope !== 'object' || typeof envelope.report_text !== 'string') {
    // Valid JSON but not our envelope shape (e.g. the report itself is a
    // JSON document) -- return the original text unchanged.
    return rawReportText;
  }

  const {
    report_text: innerText,
    is_compressed = false,
    is_base64 = false,
    report_sha256 = null,
    encoding = 'utf-8',
  } = envelope;

  if (!is_compressed && !is_base64) {
    return innerText;
  }

  let bytes = base64ToUint8Array(innerText);
  if (is_compressed) {
    bytes = await gunzipBytes(bytes);
  }

  if (report_sha256) {
    const actual = await sha256Hex(bytes);
    if (actual !== report_sha256) {
      throw new Error('Report SHA-256 mismatch after decoding.');
    }
  }

  return uint8ArrayToText(bytes, encoding);
}
