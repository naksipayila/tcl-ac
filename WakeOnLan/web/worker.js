const COMMAND_KEY = "command:current";
const RELAY_KEY = "relay:last_seen";

const HTML = String.raw`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wake-on-LAN Control</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1020;
      --card: #121a2b;
      --line: #263247;
      --text: #f4f7fb;
      --muted: #9aa7ba;
      --accent: #5eead4;
      --danger: #fb7185;
      --ok: #22c55e;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }

    body {
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      padding: 16px;
      color: var(--text);
      background: var(--bg);
    }

    button,
    input { font: inherit; }

    .shell { width: min(420px, 100%); }

    .card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--card);
      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
    }

    .panel { padding: 18px; }
    .hidden { display: none !important; }

    .login-title,
    .pc-name {
      margin: 0;
      font-size: 1.1rem;
      line-height: 1.25;
    }

    .subtle {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.85rem;
      line-height: 1.4;
    }

    .pin-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      margin-top: 14px;
    }

    input {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      color: var(--text);
      background: #0c1322;
      outline: none;
    }

    input:focus { border-color: var(--accent); }

    .button {
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      color: #061014;
      font-weight: 800;
      background: var(--accent);
      cursor: pointer;
    }

    .button:disabled {
      cursor: not-allowed;
      opacity: 0.45;
    }

    .wake-button {
      width: 100%;
      margin-top: 16px;
      padding: 14px 16px;
      font-size: 1.05rem;
    }

    .status-grid {
      display: grid;
      gap: 8px;
      margin-top: 14px;
    }

    .status-box {
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }

    .label {
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .value {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 700;
    }

    .dot-row {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--danger);
    }

    .dot.online { background: var(--ok); }

    .message {
      min-height: 20px;
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 0.85rem;
      line-height: 1.4;
    }

    .message.error { color: var(--danger); }

    .topbar {
      display: flex;
      gap: 12px;
      justify-content: space-between;
      align-items: center;
    }

    .ghost {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 10px;
      color: var(--muted);
      background: transparent;
      cursor: pointer;
      font-size: 0.78rem;
    }

    @media (max-width: 420px) {
      body { align-items: start; }
      .pin-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="card">
      <div id="login" class="panel">
        <h1 class="login-title">Wake-on-LAN</h1>
        <p class="subtle">Enter PIN to control the PC.</p>
        <form id="loginForm" class="pin-row">
          <input id="pinInput" type="password" inputmode="numeric" autocomplete="current-password" placeholder="PIN" required>
          <button class="button" type="submit">Unlock</button>
        </form>
        <p id="loginMessage" class="message"></p>
      </div>

      <div id="app" class="panel hidden">
        <div class="topbar">
          <div>
            <p class="label">PC</p>
            <h2 id="pcName" class="pc-name">Home PC</h2>
          </div>
          <button id="logoutButton" class="ghost" type="button">Logout</button>
        </div>

        <button id="wakeButton" class="button wake-button" type="button">Wake PC</button>

        <div class="status-grid">
          <div class="status-box">
            <p class="label">Relay</p>
            <div class="dot-row">
              <span id="relayDot" class="dot"></span>
              <p id="relayText" class="value">Checking...</p>
            </div>
            <p id="relayMeta" class="subtle">No heartbeat yet.</p>
          </div>
          <div class="status-box">
            <p class="label">Last command</p>
            <p id="commandText" class="value">No wake command yet.</p>
            <p id="commandMeta" class="subtle">Press the button when the relay is online.</p>
          </div>
        </div>

        <p id="appMessage" class="message"></p>
      </div>
    </section>
  </main>

  <script>
    const login = document.getElementById('login');
    const app = document.getElementById('app');
    const loginForm = document.getElementById('loginForm');
    const pinInput = document.getElementById('pinInput');
    const loginMessage = document.getElementById('loginMessage');
    const appMessage = document.getElementById('appMessage');
    const wakeButton = document.getElementById('wakeButton');
    const logoutButton = document.getElementById('logoutButton');
    const pcName = document.getElementById('pcName');
    const relayDot = document.getElementById('relayDot');
    const relayText = document.getElementById('relayText');
    const relayMeta = document.getElementById('relayMeta');
    const commandText = document.getElementById('commandText');
    const commandMeta = document.getElementById('commandMeta');

    let adminPin = localStorage.getItem('wolAdminPin') || '';

    function showLogin(message) {
      login.classList.remove('hidden');
      app.classList.add('hidden');
      loginMessage.textContent = message || '';
      loginMessage.className = message ? 'message error' : 'message';
      pinInput.focus();
    }

    function showApp() {
      login.classList.add('hidden');
      app.classList.remove('hidden');
      appMessage.textContent = '';
      appMessage.className = 'message';
    }

    function formatAge(timestamp, now) {
      if (!timestamp) return 'Never seen.';
      const seconds = Math.max(0, Math.round((now - timestamp) / 1000));
      if (seconds < 5) return 'Just now.';
      if (seconds < 60) return seconds + 's ago.';
      const minutes = Math.round(seconds / 60);
      if (minutes < 60) return minutes + 'm ago.';
      const hours = Math.round(minutes / 60);
      return hours + 'h ago.';
    }

    async function api(path, options) {
      const response = await fetch(path, {
        method: options && options.method ? options.method : 'GET',
        headers: Object.assign({ Authorization: 'Bearer ' + adminPin }, options && options.headers ? options.headers : {}),
        body: options && options.body ? options.body : undefined
      });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        throw new Error(data.error || 'Request failed with HTTP ' + response.status);
      }
      return data;
    }

    function renderStatus(data) {
      const now = data.serverTime || Date.now();
      pcName.textContent = data.pcName || 'Home PC';

      relayDot.classList.toggle('online', Boolean(data.relay && data.relay.online));
      relayText.textContent = data.relay && data.relay.online ? 'Online' : 'Offline';
      relayMeta.textContent = data.relay && data.relay.lastSeen ? 'Last seen ' + formatAge(data.relay.lastSeen, now) : 'No heartbeat yet.';
      wakeButton.disabled = !(data.relay && data.relay.online);

      if (!data.command) {
        commandText.textContent = 'No wake command yet.';
        commandMeta.textContent = 'Press the button when the relay is online.';
        return;
      }

      const command = data.command;
      commandText.textContent = command.status || 'unknown';
      if (command.reportedAt) {
        commandMeta.textContent = (command.message || 'Reported by relay.') + ' ' + formatAge(command.reportedAt, now);
      } else if (command.claimedAt) {
        commandMeta.textContent = 'Relay picked it up ' + formatAge(command.claimedAt, now);
      } else {
        commandMeta.textContent = 'Created ' + formatAge(command.createdAt, now);
      }
    }

    async function refresh() {
      if (!adminPin) {
        showLogin('');
        return;
      }

      try {
        const data = await api('/api/status');
        showApp();
        renderStatus(data);
      } catch (error) {
        if (String(error.message).toLowerCase().includes('pin') || String(error.message).includes('401')) {
          localStorage.removeItem('wolAdminPin');
          adminPin = '';
          showLogin(error.message);
          return;
        }
        if (app.classList.contains('hidden')) {
          showLogin(error.message);
          return;
        }
        appMessage.textContent = error.message;
        appMessage.className = 'message error';
      }
    }

    loginForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      adminPin = pinInput.value.trim();
      localStorage.setItem('wolAdminPin', adminPin);
      await refresh();
    });

    logoutButton.addEventListener('click', function () {
      localStorage.removeItem('wolAdminPin');
      adminPin = '';
      pinInput.value = '';
      showLogin('PIN removed from this browser.');
    });

    wakeButton.addEventListener('click', async function () {
      wakeButton.disabled = true;
      appMessage.textContent = 'Sending wake command...';
      appMessage.className = 'message';
      try {
        await api('/api/wake', { method: 'POST' });
        appMessage.textContent = 'Wake command queued. Waiting for the relay to pick it up.';
        await refresh();
      } catch (error) {
        appMessage.textContent = error.message;
        appMessage.className = 'message error';
      } finally {
        setTimeout(refresh, 1200);
      }
    });

    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>`;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);

      if (request.method === "OPTIONS") {
        return new Response(null, { headers: corsHeaders() });
      }

      if (url.pathname === "/" && request.method === "GET") {
        return new Response(HTML, { headers: htmlHeaders() });
      }

      if (url.pathname === "/api/status" && request.method === "GET") {
        requireAdmin(request, env);
        return json(await buildStatus(env));
      }

      if (url.pathname === "/api/wake" && request.method === "POST") {
        requireAdmin(request, env);
        const command = await createWakeCommand(env);
        return json({ ok: true, command });
      }

      if (url.pathname === "/api/relay/ping" && request.method === "POST") {
        requireRelay(request, env);
        await markRelaySeen(env);
        return json({ ok: true, serverTime: Date.now() });
      }

      if (url.pathname === "/api/relay/next" && request.method === "GET") {
        requireRelay(request, env);
        await markRelaySeen(env);
        return json(await nextRelayCommand(env));
      }

      if (url.pathname === "/api/relay/report" && request.method === "POST") {
        requireRelay(request, env);
        await markRelaySeen(env);
        const body = await readJson(request);
        await reportRelayResult(env, body);
        return json({ ok: true });
      }

      return json({ error: "Not found" }, 404);
    } catch (error) {
      if (error instanceof HttpError) {
        return json({ error: error.message }, error.status);
      }
      console.error(error);
      return json({ error: "Internal server error" }, 500);
    }
  }
};

function htmlHeaders() {
  return {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff"
  };
}

function jsonHeaders() {
  return {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...corsHeaders()
  };
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type"
  };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: jsonHeaders() });
}

function requireKv(env) {
  if (!env.WOL_STATE) {
    throw new HttpError(500, "WOL_STATE KV binding is not configured.");
  }
}

function getBearer(request) {
  const header = request.headers.get("Authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : "";
}

function requireAdmin(request, env) {
  requireKv(env);
  if (!env.ADMIN_PIN) {
    throw new HttpError(500, "ADMIN_PIN secret is not configured.");
  }
  if (getBearer(request) !== env.ADMIN_PIN) {
    throw new HttpError(401, "Invalid PIN.");
  }
}

function requireRelay(request, env) {
  requireKv(env);
  if (!env.RELAY_TOKEN) {
    throw new HttpError(500, "RELAY_TOKEN secret is not configured.");
  }
  if (getBearer(request) !== env.RELAY_TOKEN) {
    throw new HttpError(401, "Invalid relay token.");
  }
}

async function readJson(request) {
  try {
    return await request.json();
  } catch (_error) {
    throw new HttpError(400, "Invalid JSON body.");
  }
}

async function getJson(env, key) {
  requireKv(env);
  const value = await env.WOL_STATE.get(key, "json");
  return value || null;
}

async function putJson(env, key, value) {
  requireKv(env);
  await env.WOL_STATE.put(key, JSON.stringify(value));
}

function envNumber(env, key, fallback) {
  const raw = env[key];
  if (raw === undefined || raw === null || raw === "") return fallback;
  const number = Number(raw);
  return Number.isFinite(number) ? number : fallback;
}

async function markRelaySeen(env) {
  await putJson(env, RELAY_KEY, { lastSeen: Date.now() });
}

async function buildStatus(env) {
  const now = Date.now();
  const relay = await getJson(env, RELAY_KEY);
  const lastSeen = relay && relay.lastSeen ? relay.lastSeen : null;
  const offlineAfterMs = envNumber(env, "RELAY_OFFLINE_AFTER_SECONDS", 20) * 1000;
  const command = await getJson(env, COMMAND_KEY);

  return {
    ok: true,
    pcName: env.PC_NAME || "Home PC",
    serverTime: now,
    relay: {
      online: Boolean(lastSeen && now - lastSeen <= offlineAfterMs),
      lastSeen
    },
    command
  };
}

async function createWakeCommand(env) {
  const now = Date.now();
  const command = {
    id: crypto.randomUUID(),
    action: "wake",
    status: "pending",
    createdAt: now,
    claimedAt: null,
    reportedAt: null,
    message: "Waiting for relay."
  };
  await putJson(env, COMMAND_KEY, command);
  return command;
}

async function nextRelayCommand(env) {
  const now = Date.now();
  const command = await getJson(env, COMMAND_KEY);
  const pollAfter = envNumber(env, "RELAY_POLL_SECONDS", 3);
  if (!command) {
    return { ok: true, command: null, pollAfter, serverTime: now };
  }

  const claimTimeoutMs = envNumber(env, "CLAIM_TIMEOUT_SECONDS", 30) * 1000;
  const claimExpired = command.status === "claimed" && command.claimedAt && now - command.claimedAt > claimTimeoutMs;
  if (command.status === "pending" || claimExpired) {
    const claimed = {
      ...command,
      status: "claimed",
      claimedAt: now,
      message: "Relay picked up the command."
    };
    await putJson(env, COMMAND_KEY, claimed);
    return {
      ok: true,
      command: { id: claimed.id, action: claimed.action },
      pollAfter,
      serverTime: now
    };
  }

  return { ok: true, command: null, pollAfter, serverTime: now };
}

async function reportRelayResult(env, body) {
  if (!body || typeof body.id !== "string") {
    throw new HttpError(400, "Missing command id.");
  }

  const command = await getJson(env, COMMAND_KEY);
  if (!command || command.id !== body.id) {
    return;
  }

  const ok = Boolean(body.ok);
  const message = typeof body.message === "string" && body.message.trim()
    ? body.message.trim().slice(0, 280)
    : ok ? "WOL packet sent." : "Relay reported a failure.";

  await putJson(env, COMMAND_KEY, {
    ...command,
    status: ok ? "succeeded" : "failed",
    reportedAt: Date.now(),
    message
  });
}
