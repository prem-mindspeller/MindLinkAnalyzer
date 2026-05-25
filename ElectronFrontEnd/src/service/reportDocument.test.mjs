import assert from 'node:assert/strict';

import { buildNeuroprofileReportDocument } from './reportDocument.mjs';

const sample = {
  neuroprofile_feature_export: {
    feature_report_version: 'mindspeller_eeg_feature_report_v2',
    traceability_version: 'mindspeller_eeg_feature_traceability_v7',
    protocol_session_depth: 'session_1',
    feature_rows: [{ canonical_task_id: 'mental_math' }],
  },
};

const text = buildNeuroprofileReportDocument(sample);
const parsed = JSON.parse(text);

assert.equal(parsed.feature_report_version, 'mindspeller_eeg_feature_report_v2');
assert.equal(parsed.traceability_version, 'mindspeller_eeg_feature_traceability_v7');
assert.equal(parsed.protocol_session_depth, 'session_1');
assert.equal(parsed.feature_rows[0].canonical_task_id, 'mental_math');

assert.throws(
  () => buildNeuroprofileReportDocument({ neuroprofile_feature_export: { error: 'boom' } }),
  /Neuroprofile export unavailable/
);

assert.throws(
  () => buildNeuroprofileReportDocument({}),
  /Missing neuroprofile_feature_export/
);
