import assert from 'node:assert/strict';
import test from 'node:test';

import { TASK_IDS, taskFormForSession } from './optimizedBatteryConfig.mjs';
import { dutchCueAudioAssetCount, dutchCueAudioAssetsForForm } from './dutchCueAudioAssets.mjs';

test('generated Dutch cue audio covers every reachable localized cue', () => {
  assert.equal(dutchCueAudioAssetCount(), 44);
  for (const taskId of [TASK_IDS.NUMERICAL, TASK_IDS.WORKING_MEMORY, TASK_IDS.DUAL_TASK]) {
    for (const sessionDepth of ['session_1', 'session_2', 'session_3']) {
      const form = taskFormForSession(taskId, sessionDepth, undefined, 'nl');
      const assets = dutchCueAudioAssetsForForm(form);
      assert.equal(Object.keys(assets).length, form.spokenEvents.length, `${taskId}/${sessionDepth}`);
      for (const asset of Object.values(assets)) {
        assert.match(asset.uri, /dutch-cues\/cue-[a-f0-9]{16}\.mp3$/);
        assert.match(asset.sha256, /^[a-f0-9]{64}$/);
        assert.equal(asset.voiceLabel, 'Will - Dutch-accent European narrator');
        assert.equal(asset.playbackRate, 0.8);
      }
    }
  }
});
