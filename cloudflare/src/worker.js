const STATE_KEY = "controller";
const SESSION_COOKIE = "tcl_ac_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 30;

let credentialCache = null;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname.startsWith("/api/")) {
        return await handleApi(request, env, url);
      }
      if (env.ASSETS) {
        return env.ASSETS.fetch(request);
      }
      return new Response("Not found", { status: 404 });
    } catch (error) {
      return errorResponse(error);
    }
  },

  async scheduled(_event, env) {
    try {
      await runScheduledCycle(env);
    } catch (error) {
      console.error("Scheduled cycle failed", error && error.message ? error.message : error);
      try {
        const state = await loadState(env);
        state.last_error = safeErrorMessage(error);
        state.updated_at = nowSeconds();
        await saveState(env, state);
      } catch (saveError) {
        console.error("Could not persist scheduled error", saveError && saveError.message ? saveError.message : saveError);
      }
    }
  },
};

async function handleApi(request, env, url) {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: securityHeaders() });
  }

  if (url.pathname === "/api/session" && request.method === "GET") {
    return jsonResponse({ ok: true, authenticated: await isAuthenticated(request, env) });
  }

  if (url.pathname === "/api/login" && request.method === "POST") {
    return handleLogin(request, env);
  }

  if (url.pathname === "/api/logout" && request.method === "POST") {
    return jsonResponse(
      { ok: true },
      200,
      { "Set-Cookie": `${SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0` },
    );
  }

  await requireAuth(request, env);

  if (url.pathname === "/api/state" && request.method === "GET") {
    const state = await loadState(env);
    return jsonResponse({ ok: true, state: snapshot(state) });
  }

  if (url.pathname === "/api/device-status" && request.method === "GET") {
    const state = await loadState(env);
    const status = await readDeviceStatus(env);
    applyDeviceStatus(state, status);
    await saveState(env, state);
    return jsonResponse({ ok: true, status, state: snapshot(state) });
  }

  if (url.pathname === "/api/start" && request.method === "POST") {
    const result = await startCycle(env);
    return jsonResponse(result);
  }

  if (url.pathname === "/api/stop" && request.method === "POST") {
    const result = await stopCycle(env);
    return jsonResponse(result);
  }

  if (url.pathname === "/api/phase" && request.method === "POST") {
    const body = await readJsonBody(request);
    const result = await sendPhase(env, String(body.phase || ""));
    return jsonResponse(result);
  }

  if (url.pathname === "/api/power" && request.method === "POST") {
    const body = await readJsonBody(request);
    const result = await setPower(env, Boolean(body.enabled));
    return jsonResponse(result);
  }

  if (url.pathname === "/api/swing" && request.method === "POST") {
    const body = await readJsonBody(request);
    const result = await setSwing(env, Boolean(body.enabled));
    return jsonResponse(result);
  }

  throw new HttpError(404, "Not found");
}

async function handleLogin(request, env) {
  const body = await readJsonBody(request);
  const password = typeof body.password === "string" ? body.password : "";
  const expected = env.PANEL_PASSWORD || "";
  if (!expected || !safeEqual(password, expected)) {
    throw new HttpError(401, "Invalid password");
  }

  const issuedAt = nowSeconds();
  const expiresAt = issuedAt + SESSION_TTL_SECONDS;
  const payload = base64UrlEncodeText(JSON.stringify({ iat: issuedAt, exp: expiresAt }));
  const signature = await hmacBase64Url(env.PANEL_SESSION_SECRET, payload);
  const cookie = `${SESSION_COOKIE}=${payload}.${signature}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_TTL_SECONDS}`;
  return jsonResponse({ ok: true, authenticated: true }, 200, { "Set-Cookie": cookie });
}

async function requireAuth(request, env) {
  if (!(await isAuthenticated(request, env))) {
    throw new HttpError(401, "Login required");
  }
}

async function isAuthenticated(request, env) {
  if (!env.PANEL_SESSION_SECRET) return false;
  const cookies = parseCookies(request.headers.get("Cookie") || "");
  const raw = cookies[SESSION_COOKIE];
  if (!raw || !raw.includes(".")) return false;
  const [payload, signature] = raw.split(".", 2);
  const expected = await hmacBase64Url(env.PANEL_SESSION_SECRET, payload);
  if (!safeEqual(signature, expected)) return false;

  try {
    const data = JSON.parse(base64UrlDecodeText(payload));
    return typeof data.exp === "number" && data.exp > nowSeconds();
  } catch (_error) {
    return false;
  }
}

async function startCycle(env) {
  const state = await loadState(env);
  if (state.running) {
    return { ok: true, message: "Cycle is already running.", state: snapshot(state) };
  }

  const now = nowSeconds();
  const desired = buildSetpointDesired(config(env).cycle.cooling_setpoint_f);
  if (config(env).startup_swing) desired.swingWind = 1;
  await sendDesiredWithSafety(env, state, desired, "cf_start");

  state.running = true;
  state.phase = "cooling";
  state.cycle_number = Number(state.cycle_number || 0) + 1;
  state.phase_started_at = now;
  state.phase_end_at = now + config(env).cycle.cooling_minutes * 60;
  state.active_temperature = temperatureState(config(env).cycle.cooling_setpoint_f, "cycle.cooling");
  if (config(env).startup_swing) state.swing_wind = true;
  state.last_error = null;
  await saveState(env, state);
  return { ok: true, message: "Cycle started.", state: snapshot(state) };
}

async function stopCycle(env) {
  const state = await loadState(env);
  state.running = false;
  state.phase = "stopped";
  state.phase_started_at = null;
  state.phase_end_at = null;
  state.last_error = null;
  await saveState(env, state);
  return { ok: true, message: "Cycle stopped.", state: snapshot(state) };
}

async function sendPhase(env, phase) {
  const cfg = config(env);
  let setpoint;
  if (phase === "cooling") {
    setpoint = cfg.cycle.cooling_setpoint_f;
  } else if (phase === "resting") {
    setpoint = cfg.cycle.resting_setpoint_f;
  } else {
    throw new HttpError(400, "phase must be cooling or resting");
  }

  const state = await loadState(env);
  state.running = false;
  state.phase = "stopped";
  state.phase_started_at = null;
  state.phase_end_at = null;
  await sendDesiredWithSafety(env, state, buildSetpointDesired(setpoint), `cf_${phase}`);
  state.active_temperature = temperatureState(setpoint, `manual.${phase}`);
  state.last_error = null;
  await saveState(env, state);
  return { ok: true, message: `${setpoint}F command sent.`, state: snapshot(state) };
}

async function setPower(env, enabled) {
  const state = await loadState(env);
  if (!enabled) {
    state.running = false;
    state.phase = "stopped";
    state.phase_started_at = null;
    state.phase_end_at = null;
  }
  await sendDesiredWithSafety(env, state, { powerSwitch: enabled ? 1 : 0 }, "cf_power");
  state.power_switch = enabled;
  state.last_error = null;
  await saveState(env, state);
  return { ok: true, message: `AC power turned ${enabled ? "on" : "off"}.`, state: snapshot(state) };
}

async function setSwing(env, enabled) {
  const state = await loadState(env);
  await sendDesiredWithSafety(env, state, { swingWind: enabled ? 1 : 0 }, "cf_swing");
  state.swing_wind = enabled;
  state.last_error = null;
  await saveState(env, state);
  return { ok: true, message: `Swing turned ${enabled ? "on" : "off"}.`, state: snapshot(state) };
}

async function runScheduledCycle(env) {
  const state = await loadState(env);
  if (!state.running || !state.phase_end_at || nowSeconds() < Number(state.phase_end_at)) return;

  const cfg = config(env);
  const nextPhase = state.phase === "cooling" ? "resting" : "cooling";
  const setpoint = nextPhase === "cooling" ? cfg.cycle.cooling_setpoint_f : cfg.cycle.resting_setpoint_f;
  const minutes = nextPhase === "cooling" ? cfg.cycle.cooling_minutes : cfg.cycle.resting_minutes;
  const now = nowSeconds();

  await sendDesiredWithSafety(env, state, buildSetpointDesired(setpoint), `cf_cron_${nextPhase}`);
  state.phase = nextPhase;
  state.phase_started_at = now;
  state.phase_end_at = now + minutes * 60;
  state.active_temperature = temperatureState(setpoint, `cycle.${nextPhase}`);
  state.last_error = null;
  await saveState(env, state);
}

async function sendDesiredWithSafety(env, state, desired, tokenPrefix) {
  const elapsed = nowSeconds() - Number(state.last_command_at || 0);
  const wait = config(env).min_seconds_between_commands - elapsed;
  if (state.last_command_at && wait > 0) {
    throw new HttpError(429, `Safety wait: try again in ${Math.ceil(wait)} seconds.`);
  }
  await sendDesiredState(env, desired, tokenPrefix);
  state.last_command_at = nowSeconds();
}

async function sendDesiredState(env, desired, tokenPrefix) {
  const cfg = config(env);
  const payload = {
    state: { desired },
    clientToken: `${tokenPrefix}_${Date.now()}`,
  };
  const topic = `$aws/things/${cfg.device_id}/shadow/update`;
  return mqttWsPublish(env, topic, payload);
}

async function readDeviceStatus(env) {
  return iotData(env, "GET", `/things/${config(env).device_id}/shadow`);
}

async function mqttWsPublish(env, topic, payload) {
  const clientId = `cf_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
  const url = await awsPresignedMqttUrl(env);
  let response;
  try {
    response = await fetch(url, {
      headers: {
        Upgrade: "websocket",
        "Sec-WebSocket-Protocol": "mqtt",
      },
    });
  } catch (_error) {
    throw new HttpError(502, "MQTT WebSocket connect failed before handshake.");
  }
  if (response.status !== 101 || !response.webSocket) {
    const text = await response.text().catch(() => "");
    throw new HttpError(502, `MQTT WebSocket connect failed with HTTP ${response.status}: ${text.slice(0, 200)}`);
  }

  const ws = response.webSocket;
  ws.binaryType = "arraybuffer";
  ws.accept();
  try {
    ws.send(mqttConnectPacket(clientId));
    const connack = await waitForMessage(ws, 5000);
    const connackBytes = await messageBytes(connack);
    if (connackBytes.length < 4 || connackBytes[0] !== 0x20 || connackBytes[3] !== 0) {
      throw new HttpError(502, `MQTT CONNACK failed: ${hexFromBytes(connackBytes)}`);
    }
    ws.send(mqttPublishPacket(topic, payload));
    await delay(500);
  } finally {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close(1000, "done");
    }
  }
  return null;
}

async function awsPresignedMqttUrl(env) {
  const cfg = config(env);
  const credentials = await ensureAwsCredentials(env);
  const endpoint = credentials.mqttEndpoint || cfg.iot_data_endpoint;
  const host = mqttHostFromEndpoint(endpoint);
  const now = new Date();
  const amzDate = isoAmzDate(now);
  const dateStamp = amzDate.slice(0, 8);
  const credentialScope = `${dateStamp}/${cfg.region}/iotdata/aws4_request`;
  const params = {
    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
    "X-Amz-Credential": `${credentials.accessKey}/${credentialScope}`,
    "X-Amz-Date": amzDate,
    "X-Amz-SignedHeaders": "host",
  };
  const urlParams = { ...params, "X-Amz-Security-Token": credentials.sessionToken };
  const canonicalQuery = canonicalQueryString(params);
  const canonicalRequest = [
    "GET",
    "/mqtt",
    canonicalQuery,
    `host:${host}\n`,
    "host",
    await sha256Hex(""),
  ].join("\n");
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    credentialScope,
    await sha256Hex(canonicalRequest),
  ].join("\n");
  const signingKey = await awsSignatureKey(credentials.secretKey, dateStamp, cfg.region, "iotdata");
  const signature = hexFromBytes(await hmacBytes(signingKey, stringToSign));
  return `https://${host}/mqtt?${canonicalQueryString(urlParams)}&X-Amz-Signature=${signature}`;
}

function mqttConnectPacket(clientId) {
  const variableHeader = concatBytes(mqttString("MQTT"), new Uint8Array([4, 2]), uint16Bytes(60));
  const payload = mqttString(clientId);
  const remaining = concatBytes(variableHeader, payload);
  return concatBytes(new Uint8Array([0x10]), mqttRemainingLength(remaining.length), remaining);
}

function mqttPublishPacket(topic, payload) {
  const body = utf8(JSON.stringify(payload));
  const remaining = concatBytes(mqttString(topic), body);
  return concatBytes(new Uint8Array([0x30]), mqttRemainingLength(remaining.length), remaining);
}

function mqttRemainingLength(length) {
  const bytes = [];
  let remaining = length;
  do {
    let digit = remaining % 128;
    remaining = Math.floor(remaining / 128);
    if (remaining > 0) digit |= 128;
    bytes.push(digit);
  } while (remaining > 0);
  return new Uint8Array(bytes);
}

function mqttString(value) {
  const raw = utf8(value);
  return concatBytes(uint16Bytes(raw.length), raw);
}

function uint16Bytes(value) {
  return new Uint8Array([(value >> 8) & 0xff, value & 0xff]);
}

function concatBytes(...arrays) {
  const total = arrays.reduce((sum, array) => sum + array.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const array of arrays) {
    result.set(array, offset);
    offset += array.length;
  }
  return result;
}

function waitForMessage(ws, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      cleanup();
      reject(new HttpError(504, "MQTT WebSocket timed out waiting for CONNACK."));
    }, timeoutMs);
    const cleanup = () => {
      clearTimeout(timeout);
      ws.removeEventListener("message", onMessage);
      ws.removeEventListener("error", onError);
      ws.removeEventListener("close", onClose);
    };
    const onMessage = (event) => {
      cleanup();
      resolve(event.data);
    };
    const onError = () => {
      cleanup();
      reject(new HttpError(502, "MQTT WebSocket error."));
    };
    const onClose = (event) => {
      cleanup();
      reject(new HttpError(502, `MQTT WebSocket closed before CONNACK: ${event.code}`));
    };
    ws.addEventListener("message", onMessage);
    ws.addEventListener("error", onError);
    ws.addEventListener("close", onClose);
  });
}

async function messageBytes(data) {
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  if (data instanceof Blob) return new Uint8Array(await data.arrayBuffer());
  if (typeof data === "string") return Uint8Array.from(data, (char) => char.charCodeAt(0));
  return new Uint8Array(0);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function iotData(env, method, path, body = null, canonicalQuery = "") {
  const cfg = config(env);
  const canonicalUri = encodeCanonicalPath(path);
  const bodyText = body === null ? "" : JSON.stringify(body);
  const headers = await awsHeaders(env, method, canonicalUri, canonicalQuery, bodyText);
  const response = await fetch(`${cfg.iot_data_endpoint}${canonicalUri}${canonicalQuery ? `?${canonicalQuery}` : ""}`, {
    method,
    headers,
    body: body === null ? undefined : bodyText,
  });
  const text = await response.text();
  if (!response.ok) {
    throw new HttpError(502, `AWS IoT Data ${method} failed with HTTP ${response.status}: ${text.slice(0, 300)}`);
  }
  if (!text) return null;
  return JSON.parse(text);
}

async function awsHeaders(env, method, canonicalUri, canonicalQuery, bodyText) {
  const cfg = config(env);
  const credentials = await ensureAwsCredentials(env);
  const host = new URL(cfg.iot_data_endpoint).host;
  const now = new Date();
  const amzDate = isoAmzDate(now);
  const dateStamp = amzDate.slice(0, 8);
  const payloadHash = await sha256Hex(bodyText);
  const canonicalHeaders = `host:${host}\nx-amz-date:${amzDate}\nx-amz-security-token:${credentials.sessionToken}\n`;
  const signedHeaders = "host;x-amz-date;x-amz-security-token";
  const canonicalRequest = [
    method,
    canonicalUri,
    canonicalQuery,
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");
  const credentialScope = `${dateStamp}/${cfg.region}/iotdata/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    credentialScope,
    await sha256Hex(canonicalRequest),
  ].join("\n");
  const signingKey = await awsSignatureKey(credentials.secretKey, dateStamp, cfg.region, "iotdata");
  const signature = hexFromBytes(await hmacBytes(signingKey, stringToSign));
  return {
    Authorization: `AWS4-HMAC-SHA256 Credential=${credentials.accessKey}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`,
    "X-Amz-Date": amzDate,
    "X-Amz-Security-Token": credentials.sessionToken,
    "Content-Type": "application/x-amz-json-1.0",
    "User-Agent": "tcl-ac-cloudflare/1.0",
  };
}

async function ensureAwsCredentials(env) {
  if (credentialCache && credentialCache.expiresAt > nowSeconds() + 300) {
    return credentialCache;
  }

  const loadBalanceData = await loadBalance(env);
  const identityId = String(loadBalanceData.cognitoId || "");
  const cognitoToken = String(loadBalanceData.cognitoToken || "");
  if (!identityId || !cognitoToken) {
    throw new HttpError(502, "TCL loadBalance did not return Cognito credentials.");
  }

  const credentialsPayload = await cognitoCredentials(env, identityId, cognitoToken);
  const raw = credentialsPayload.Credentials || credentialsPayload.credentials;
  if (!raw) throw new HttpError(502, "AWS Cognito returned no credentials.");

  const accessKey = String(raw.AccessKeyId || "");
  const secretKey = String(raw.SecretKey || raw.SecretAccessKey || "");
  const sessionToken = String(raw.SessionToken || "");
  if (!accessKey || !secretKey || !sessionToken) {
    throw new HttpError(502, "AWS Cognito credentials response is incomplete.");
  }

  credentialCache = {
    accessKey,
    secretKey,
    sessionToken,
    mqttEndpoint: typeof loadBalanceData.mqttEndpoint === "string" ? loadBalanceData.mqttEndpoint : null,
    expiresAt: credentialExpiration(raw.Expiration),
  };
  return credentialCache;
}

async function loadBalance(env) {
  const cfg = config(env);
  if (!env.TCL_SSO_TOKEN) throw new HttpError(500, "TCL_SSO_TOKEN secret is not configured.");
  const response = await fetch(`${cfg.api_base_url}/v1/auth/service/loadBalance`, {
    headers: {
      appid: cfg.app_id,
      ssotoken: env.TCL_SSO_TOKEN,
      "Accept-Encoding": "identity",
      "User-Agent": "Dart/3.4 (dart:io)",
    },
  });
  const payload = await response.json();
  if (!response.ok || Number(payload.code || 0) !== 200 || !payload.data) {
    throw new HttpError(502, "TCL loadBalance failed.");
  }
  return payload.data;
}

async function cognitoCredentials(env, identityId, cognitoToken) {
  const cfg = config(env);
  const response = await fetch(`https://cognito-identity.${cfg.region}.amazonaws.com/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
      "Accept-Encoding": "identity",
    },
    body: JSON.stringify({
      IdentityId: identityId,
      Logins: { "cognito-identity.amazonaws.com": cognitoToken },
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new HttpError(502, `AWS Cognito failed with HTTP ${response.status}.`);
  }
  return payload;
}

async function loadState(env) {
  const defaults = defaultState(env);
  const row = await env.DB.prepare("SELECT value FROM state WHERE key = ?").bind(STATE_KEY).first();
  if (!row || typeof row.value !== "string") return defaults;
  try {
    const stored = JSON.parse(row.value);
    return normalizeState({ ...defaults, ...stored, cycle: defaults.cycle });
  } catch (_error) {
    return defaults;
  }
}

async function saveState(env, state) {
  const normalized = normalizeState({ ...state, cycle: config(env).cycle, updated_at: nowSeconds() });
  await env.DB.prepare("INSERT OR REPLACE INTO state (key, value, updated_at) VALUES (?, ?, ?)")
    .bind(STATE_KEY, JSON.stringify(normalized), nowSeconds())
    .run();
  Object.assign(state, normalized);
  return normalized;
}

function defaultState(env) {
  return normalizeState({
    running: false,
    phase: "stopped",
    cycle_number: 0,
    phase_started_at: null,
    phase_end_at: null,
    last_command_at: 0,
    power_switch: false,
    swing_wind: false,
    active_temperature: emptyTemperature(),
    cycle: config(env).cycle,
    last_error: null,
    updated_at: nowSeconds(),
  });
}

function normalizeState(state) {
  return {
    running: Boolean(state.running),
    phase: typeof state.phase === "string" ? state.phase : "stopped",
    cycle_number: Number(state.cycle_number || 0),
    phase_started_at: nullableNumber(state.phase_started_at),
    phase_end_at: nullableNumber(state.phase_end_at),
    last_command_at: Number(state.last_command_at || 0),
    power_switch: Boolean(state.power_switch),
    swing_wind: Boolean(state.swing_wind),
    active_temperature: state.active_temperature || emptyTemperature(),
    cycle: state.cycle,
    last_error: state.last_error || null,
    updated_at: Number(state.updated_at || nowSeconds()),
  };
}

function snapshot(state) {
  const remaining = state.running && state.phase_end_at ? Math.max(0, Number(state.phase_end_at) - nowSeconds()) : null;
  return {
    running: state.running,
    phase: state.running ? state.phase : "stopped",
    power_switch: state.power_switch,
    swing_wind: state.swing_wind,
    remaining_seconds: remaining,
    cycle: state.cycle,
    active_temperature: state.active_temperature || emptyTemperature(),
    cycle_number: state.cycle_number,
    last_error: state.last_error,
    updated_at: state.updated_at,
  };
}

function applyDeviceStatus(state, status) {
  state.active_temperature = extractActiveTemperature(status);
  const swingWind = extractBoolProperty(status, "swingWind");
  const powerSwitch = extractBoolProperty(status, "powerSwitch");
  if (swingWind !== null) state.swing_wind = swingWind;
  if (powerSwitch !== null) {
    state.power_switch = powerSwitch;
    if (!powerSwitch && state.running) {
      state.running = false;
      state.phase = "stopped";
      state.phase_started_at = null;
      state.phase_end_at = null;
    }
  }
}

function extractBoolProperty(status, propertyName) {
  const paths = [
    ["state", "reported", propertyName],
    ["state", "desired", propertyName],
    ["reported", propertyName],
    ["desired", propertyName],
  ];
  for (const path of paths) {
    const value = booleanValue(valueAtPath(status, path));
    if (value !== null) return value;
  }
  return null;
}

function extractActiveTemperature(status) {
  const paths = [
    [["state", "reported", "targetFahrenheitDegree"], "F"],
    [["state", "reported", "targetCelsiusDegree"], "C"],
    [["state", "desired", "targetFahrenheitDegree"], "F"],
    [["state", "desired", "targetCelsiusDegree"], "C"],
  ];
  for (const [path, unit] of paths) {
    const raw = numericValue(valueAtPath(status, path));
    if (raw === null || raw < -40 || raw > 140) continue;
    const normalized = normalizeTemperature(raw, unit);
    return {
      fahrenheit: normalized.fahrenheit,
      celsius: normalized.celsius,
      source: path.join("."),
      updated_at: nowSeconds(),
      error: null,
    };
  }
  return emptyTemperature();
}

function valueAtPath(value, path) {
  let current = value;
  for (const key of path) {
    if (!current || typeof current !== "object") return undefined;
    current = current[key];
  }
  return current;
}

function numericValue(value) {
  if (typeof value === "boolean") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function booleanValue(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "on", "yes"].includes(normalized)) return true;
    if (["0", "false", "off", "no"].includes(normalized)) return false;
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed !== 0 : null;
  }
  return null;
}

function emptyTemperature() {
  return { fahrenheit: null, celsius: null, source: null, updated_at: nowSeconds(), error: null };
}

function temperatureState(fahrenheit, source) {
  const normalized = normalizeTemperature(fahrenheit, "F");
  return { fahrenheit: normalized.fahrenheit, celsius: normalized.celsius, source, updated_at: nowSeconds(), error: null };
}

function normalizeTemperature(value, unit) {
  const fahrenheit = unit === "F" ? value : value * 9 / 5 + 32;
  const celsius = unit === "F" ? (value - 32) * 5 / 9 : value;
  return { fahrenheit: round1(fahrenheit), celsius: round1(celsius) };
}

function buildSetpointDesired(setpointF) {
  return {
    targetCelsiusDegree: Math.trunc((setpointF - 32) * 5 / 9),
    targetFahrenheitDegree: Math.round(setpointF),
  };
}

function config(env) {
  return {
    device_id: env.DEVICE_ID || "DWG42RFAAAE",
    api_base_url: trimTrailingSlash(env.API_BASE_URL || "https://eu-iot-api-prod.tcljd.com"),
    iot_data_endpoint: trimTrailingSlash(env.IOT_DATA_ENDPOINT || "https://data.iot.eu-central-1.amazonaws.com"),
    region: env.AWS_REGION || "eu-central-1",
    app_id: env.APP_ID || "wx6e1af3fa84fbe523",
    min_seconds_between_commands: numberEnv(env.MIN_SECONDS_BETWEEN_COMMANDS, 30),
    startup_swing: String(env.STARTUP_SWING || "1") !== "0",
    cycle: {
      cooling_setpoint_f: numberEnv(env.COOLING_SETPOINT_F, 70),
      resting_setpoint_f: numberEnv(env.RESTING_SETPOINT_F, 80),
      cooling_minutes: numberEnv(env.COOLING_MINUTES, 20),
      resting_minutes: numberEnv(env.RESTING_MINUTES, 20),
    },
  };
}

function numberEnv(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function credentialExpiration(value) {
  if (typeof value === "number") return value > 10_000_000_000 ? value / 1000 : value;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return parsed / 1000;
  }
  return nowSeconds() + 3600;
}

async function awsSignatureKey(secretKey, dateStamp, region, service) {
  const kDate = await hmacBytes(`AWS4${secretKey}`, dateStamp);
  const kRegion = await hmacBytes(kDate, region);
  const kService = await hmacBytes(kRegion, service);
  return hmacBytes(kService, "aws4_request");
}

async function hmacBase64Url(secret, data) {
  return base64UrlEncodeBytes(await hmacBytes(secret || "", data));
}

async function hmacBytes(keyData, data) {
  const keyBytes = typeof keyData === "string" ? utf8(keyData) : keyData;
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, utf8(data)));
}

async function sha256Hex(value) {
  return hexFromBytes(new Uint8Array(await crypto.subtle.digest("SHA-256", utf8(value))));
}

function encodeCanonicalPath(path) {
  return path.split("/").map((part) => encodeURIComponent(part).replace(/[!'()*]/g, pctEncode)).join("/");
}

function canonicalQueryString(params) {
  return Object.keys(params)
    .sort()
    .map((key) => `${uriEncode(key)}=${uriEncode(String(params[key]))}`)
    .join("&");
}

function uriEncode(value) {
  return encodeURIComponent(value).replace(/[!'()*]/g, pctEncode);
}

function mqttHostFromEndpoint(endpoint) {
  const value = String(endpoint || "").trim();
  if (!value) throw new HttpError(500, "MQTT endpoint is missing.");
  try {
    const parsed = new URL(value.includes("://") ? value : `https://${value}`);
    return parsed.hostname;
  } catch (_error) {
    return value.replace(/^[a-z]+:\/\//i, "").split("/")[0].split(":")[0];
  }
}

function pctEncode(char) {
  return `%${char.charCodeAt(0).toString(16).toUpperCase()}`;
}

function isoAmzDate(date) {
  return date.toISOString().replace(/[:-]|\.\d{3}/g, "");
}

function hexFromBytes(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function base64UrlEncodeText(text) {
  return base64UrlEncodeBytes(utf8(text));
}

function base64UrlDecodeText(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function base64UrlEncodeBytes(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function utf8(value) {
  return new TextEncoder().encode(String(value));
}

function parseCookies(header) {
  const cookies = {};
  for (const part of header.split(";")) {
    const index = part.indexOf("=");
    if (index === -1) continue;
    cookies[part.slice(0, index).trim()] = part.slice(index + 1).trim();
  }
  return cookies;
}

async function readJsonBody(request) {
  try {
    return await request.json();
  } catch (_error) {
    return {};
  }
}

function jsonResponse(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...securityHeaders(),
      "Content-Type": "application/json; charset=utf-8",
      ...headers,
    },
  });
}

function errorResponse(error) {
  const status = error instanceof HttpError ? error.status : 500;
  const message = sanitizeErrorMessage(error instanceof Error ? error.message : "Internal error");
  return jsonResponse({ ok: false, error: message }, status);
}

function securityHeaders() {
  return {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  };
}

function safeErrorMessage(error) {
  return sanitizeErrorMessage(error instanceof Error ? error.message : String(error || "Unknown error"));
}

function sanitizeErrorMessage(message) {
  return String(message)
    .replace(/https:\/\/[^\s"']*X-Amz-[^\s"']*/g, "[redacted-presigned-url]")
    .replace(/wss:\/\/[^\s"']*X-Amz-[^\s"']*/g, "[redacted-presigned-url]")
    .replace(/X-Amz-Credential=[^&\s"']+/g, "X-Amz-Credential=[redacted]")
    .replace(/X-Amz-Security-Token=[^&\s"']+/g, "X-Amz-Security-Token=[redacted]")
    .replace(/X-Amz-Signature=[^&\s"']+/g, "X-Amz-Signature=[redacted]");
}

function nullableNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function round1(value) {
  return Math.round(value * 10) / 10;
}

function trimTrailingSlash(value) {
  return String(value).replace(/\/+$/, "");
}

function safeEqual(a, b) {
  const left = String(a);
  const right = String(b);
  if (left.length !== right.length) return false;
  let result = 0;
  for (let index = 0; index < left.length; index += 1) {
    result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return result === 0;
}
