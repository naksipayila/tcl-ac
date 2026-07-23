import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSetpointDesired,
  confirmationIsFresh,
  confirmationMatches,
  extractActiveTemperature,
  mqttPublishPacket,
  normalizeTemperature,
} from "../src/worker.js";

test("builds the configured Celsius setpoints and matching Fahrenheit fields", () => {
  assert.deepEqual(buildSetpointDesired(20), {
    targetCelsiusDegree: 20,
    targetFahrenheitDegree: 68,
  });
  assert.deepEqual(buildSetpointDesired(30), {
    targetCelsiusDegree: 30,
    targetFahrenheitDegree: 86,
  });
});

test("normalizes Fahrenheit shadow values to Celsius", () => {
  assert.deepEqual(normalizeTemperature(68, "F"), { fahrenheit: 68, celsius: 20 });
});

test("prefers the reported Celsius target and supports Fahrenheit fallback", () => {
  assert.equal(extractActiveTemperature({ state: { reported: { targetCelsiusDegree: 20, targetFahrenheitDegree: 68 } } }).celsius, 20);
  assert.equal(extractActiveTemperature({ state: { reported: { targetFahrenheitDegree: 86 } } }).celsius, 30);
});

test("requires every command confirmation field", () => {
  const status = { state: { reported: { targetCelsiusDegree: 20, powerSwitch: 1, swingWind: 1 } } };
  assert.equal(confirmationMatches(status, [
    { type: "temperature", celsius: 20 },
    { type: "boolean", property: "powerSwitch", value: true },
    { type: "boolean", property: "swingWind", value: true },
  ]), true);
  assert.equal(confirmationMatches(status, [{ type: "boolean", property: "powerSwitch", value: false }]), false);
});

test("rejects a matching reported value when the shadow did not advance", () => {
  const checks = [{ type: "temperature", celsius: 30 }];
  const baseline = { version: 12, state: { reported: { targetCelsiusDegree: 20 } } };
  const stale = { version: 12, state: { reported: { targetCelsiusDegree: 30 } } };
  const fresh = { version: 13, state: { reported: { targetCelsiusDegree: 30 } } };
  assert.equal(confirmationIsFresh(stale, checks, baseline, 0), false);
  assert.equal(confirmationIsFresh(fresh, checks, baseline, 0), true);
});

test("publishes QoS 1 packets with a packet identifier", () => {
  const packet = mqttPublishPacket("topic", { ok: true }, 7);
  assert.equal(packet[0], 0x32);
  assert.equal(packet[10], 7);
});
