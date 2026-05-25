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
