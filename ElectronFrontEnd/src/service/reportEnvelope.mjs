const DEFAULT_CONTENT_TYPE = 'text/plain';
const STORAGE_FORMAT = 'gzip+base64+utf8';
// Base64 of the gzip header bytes (1f 8b 08). Used to recognise compressed
// payloads from uploads written before the format flags existed.
const GZIP_BASE64_MAGIC = 'H4sI';

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

export function base64ToUint8Array(encoded) {
  if (typeof Buffer !== 'undefined') {
    return new Uint8Array(Buffer.from(encoded, 'base64'));
  }
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function gunzipBytes(bytes) {
  const nodeRequire = getNodeRequire();
  if (nodeRequire) {
    const { gunzipSync } = nodeRequire('zlib');
    return new Uint8Array(gunzipSync(Buffer.from(bytes)));
  }

  if (typeof DecompressionStream !== 'function') {
    throw new Error('This runtime does not support DecompressionStream for gzip report reading.');
  }

  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const expanded = await new Response(stream).arrayBuffer();
  return new Uint8Array(expanded);
}

/**
 * Reverse createCompressedReportEnvelope for a stored report_text value.
 *
 * Accepts the envelope JSON the seed endpoint writes, an already-plain report,
 * or a parsed envelope object. Older uploads stored only
 * `{"report_text": "H4sI..."}` with no format flags, so gzip is also detected
 * from the base64 magic prefix rather than trusted from the flags alone.
 *
 * The sha256 recorded at write time covers the *uncompressed* bytes, so it is
 * verified after expansion. A mismatch throws: a silently corrupt carried
 * report would land in a participant's profile as real evidence.
 */
export async function readCompressedReportEnvelope(stored) {
  if (stored == null) throw new Error('No stored report content to read.');

  let envelope = stored;
  if (typeof stored === 'string') {
    const trimmed = stored.trim();
    if (!trimmed.startsWith('{')) return trimmed;
    try {
      envelope = JSON.parse(trimmed);
    } catch {
      return trimmed;
    }
  }
  if (typeof envelope !== 'object' || envelope === null) {
    throw new Error('Stored report content is not a readable envelope.');
  }

  // A decoded feature report has no report_text field; it *is* the report.
  const inner = envelope.report_text;
  if (typeof inner !== 'string') return JSON.stringify(envelope);

  const looksGzipped = inner.trimStart().startsWith(GZIP_BASE64_MAGIC);
  const isCompressed = Boolean(envelope.is_compressed) || looksGzipped;
  const isBase64 = Boolean(envelope.is_base64) || isCompressed;

  if (!isBase64 && !isCompressed) return inner;

  const bytes = base64ToUint8Array(inner);
  const expanded = isCompressed ? await gunzipBytes(bytes) : bytes;
  const decodedText = new TextDecoder(envelope.encoding || 'utf-8').decode(expanded);

  const expectedSha = envelope.report_sha256 || envelope.sha256;
  if (expectedSha) {
    const actualSha = await sha256Hex(expanded);
    if (actualSha !== expectedSha) {
      throw new Error(
        `Stored report failed integrity check (expected ${expectedSha}, got ${actualSha}).`,
      );
    }
  }

  return decodedText;
}

/** Read a stored report_text straight into the parsed feature report object. */
export async function readStoredReportJson(stored) {
  const decodedText = await readCompressedReportEnvelope(stored);
  try {
    return JSON.parse(decodedText);
  } catch (error) {
    throw new Error(`Stored report is not valid JSON: ${error.message}`);
  }
}
