# Report Compression Contract

Session report uploads now keep the existing report content intact, but the
`report_text` payload field is gzip-compressed before base64 encoding.

## Payload Fields

```json
{
  "report_text": "<base64 gzip bytes>",
  "is_base64": true,
  "is_compressed": true,
  "compression": "gzip",
  "storage_format": "gzip+base64+utf8",
  "content_type": "text/plain",
  "encoding": "utf-8",
  "original_size_bytes": 5242880,
  "compressed_size_bytes": 400000,
  "report_sha256": "<sha256 of the original uncompressed UTF-8 report text>"
}
```

The backend should decompress `report_text` before passing it into the existing
report-processing flow. After decompression, the report text is the same format
that the backend already processes.

## Python Decompression

```python
import base64
import gzip
import hashlib


def decode_report_payload(payload: dict) -> str:
    data = payload["report_text"]

    if payload.get("is_compressed"):
        compressed = base64.b64decode(data)
        report_bytes = gzip.decompress(compressed)
    elif payload.get("is_base64"):
        report_bytes = base64.b64decode(data)
    else:
        report_bytes = data.encode(payload.get("encoding") or "utf-8")

    expected_sha = payload.get("report_sha256")
    if expected_sha:
        actual_sha = hashlib.sha256(report_bytes).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError("Report SHA-256 mismatch after decompression")

    return report_bytes.decode(payload.get("encoding") or "utf-8")
```

## Node.js Decompression

```js
const crypto = require('node:crypto');
const zlib = require('node:zlib');

function decodeReportPayload(payload) {
  let reportBuffer;

  if (payload.is_compressed) {
    const compressed = Buffer.from(payload.report_text, 'base64');
    reportBuffer = zlib.gunzipSync(compressed);
  } else if (payload.is_base64) {
    reportBuffer = Buffer.from(payload.report_text, 'base64');
  } else {
    reportBuffer = Buffer.from(payload.report_text, payload.encoding || 'utf8');
  }

  if (payload.report_sha256) {
    const actualSha = crypto.createHash('sha256').update(reportBuffer).digest('hex');
    if (actualSha !== payload.report_sha256) {
      throw new Error('Report SHA-256 mismatch after decompression');
    }
  }

  return reportBuffer.toString(payload.encoding || 'utf8');
}
```

## Backward Compatibility

Backends can support both old and new uploads with one branch:

- `is_compressed === true`: base64-decode, then gunzip, then parse/process.
- `is_compressed !== true && is_base64 === true`: old behavior, base64-decode only.
- no flags: treat `report_text` as plain text.
