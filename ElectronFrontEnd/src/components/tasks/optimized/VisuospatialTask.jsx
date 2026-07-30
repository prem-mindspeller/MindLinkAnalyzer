import React from 'react';

import { TASK_IDS, visualRouteState } from '../optimizedBatteryConfig.mjs';
import { ResponseField } from './taskShared.jsx';

/**
 * Task 5 — Visuospatial Transformation and Orientation.
 *
 * A single arrow on a 5x5 grid. Every scheduled turn changes both the arrow's
 * heading and its cell, so the participant must track position and direction
 * together.
 */

function directionSymbol(orientation) {
  return { north: '↑', east: '→', south: '↓', west: '←' }[orientation] || '↑';
}

function scheduleEvents({ form }) {
  return form.moves.map((move, index) => ({
    key: `route:${index}`,
    at: move.at,
    type: 'route_turn',
    turn: move.turn,
  }));
}

function Stimulus({ form, elapsedSeconds }) {
  const route = visualRouteState(form, elapsedSeconds);
  if (!route) return null;
  return (
    <div className="optimized-route-wrap" aria-label="Five by five route grid">
      <div className="optimized-route-column-labels" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((column) => <span key={column}>{column}</span>)}
      </div>
      <div className="optimized-route-grid-row">
        <div className="optimized-route-row-labels" aria-hidden="true">
          {[1, 2, 3, 4, 5].map((rowNumber) => <span key={rowNumber}>{rowNumber}</span>)}
        </div>
        <div className="optimized-route-grid">
          {Array.from({ length: 25 }, (_, index) => {
            const x = index % 5;
            const y = Math.floor(index / 5);
            const active = x === route.x && y === route.y;
            return (
              <div
                key={index}
                aria-label={`Row ${y + 1}, column ${x + 1}${active ? `, facing ${route.orientation}` : ''}`}
                className={`optimized-route-cell${active ? ' active' : ''}`}
              >{active ? directionSymbol(route.orientation) : ''}</div>
            );
          })}
        </div>
      </div>
      <p>Track position and direction. Turns become denser after the phase boundary.</p>
    </div>
  );
}

function ResponseFields({ response, setResponse }) {
  return (
    <div className="optimized-response-grid">
      <ResponseField label="Final column (1–5)">
        <input
          type="number"
          min="1"
          max="5"
          required
          value={response.x == null ? '' : Number(response.x) + 1}
          onChange={(event) => setResponse({ ...response, x: Number(event.target.value) - 1 })}
        />
      </ResponseField>
      <ResponseField label="Final row (1–5)">
        <input
          type="number"
          min="1"
          max="5"
          required
          value={response.y == null ? '' : Number(response.y) + 1}
          onChange={(event) => setResponse({ ...response, y: Number(event.target.value) - 1 })}
        />
      </ResponseField>
      <ResponseField label="Final orientation">
        <select
          required
          value={response.orientation || ''}
          onChange={(event) => setResponse({ ...response, orientation: event.target.value })}
        >
          <option value="">Select…</option>
          {['north', 'east', 'south', 'west'].map((option) => <option key={option}>{option}</option>)}
        </select>
      </ResponseField>
    </div>
  );
}

export default {
  taskId: TASK_IDS.VISUOSPATIAL,
  scheduleEvents,
  Stimulus,
  ResponseFields,
};
