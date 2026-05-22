const DEFAULT_CONTENT_TYPE = 'text/plain';
const STORAGE_FORMAT = 'gzip+base64+utf8';

function textToUint8Array(text) {
  return new TextEncoder().encode(text);
}

export function uint8ArrayToBase64(bytes) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

async function gzipBytes(bytes) {
  if (typeof CompressionStream !== 'function') {
    throw new Error('This runtime does not support CompressionStream for gzip report packaging.');
  }

  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'));
  const compressed = await new Response(stream).arrayBuffer();
  return new Uint8Array(compressed);
}

async function sha256Hex(bytes) {
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
