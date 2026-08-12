import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const dutch = JSON.parse(await readFile(new URL('../../locales/nl.json', import.meta.url), 'utf8'));

test('Dutch task-runner labels cover the title, phase and eyes-closed cue', () => {
  const battery = dutch.optimizedBattery;
  assert.equal(battery.taskNames.dual_task_rule_switching, 'Dubbeltaakprestatie en regelwisseling');
  assert.equal(battery.phaseLabels.dual_task_rule_switching.before_switch, 'Voor de regelwisseling');
  assert.equal(battery.runner.eyesClosedCue, 'Luister en ga in stilte verder. Antwoord nog niet.');
});
