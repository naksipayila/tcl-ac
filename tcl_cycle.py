from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import hmac
import json
import logging
import os
import pathlib
import signal
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid
from typing import Any


CONFIG_DEFAULT = "config.json"
LOG_DIR = pathlib.Path("logs")


class ConfigError(Exception):
    pass


class BackendError(Exception):
    pass


def fahrenheit_to_celsius(value: float) -> float:
    return round((value - 32.0) * 5.0 / 9.0, 1)


def fahrenheit_to_tcl_celsius(value: float) -> int:
    return int((value - 32.0) * 5.0 / 9.0)


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


def require_text(config: dict[str, Any], key: str, path: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}.{key} is required")
    if value.startswith("${") or value.startswith("%"):
        raise ConfigError(f"{path}.{key} env var could not be resolved: {value}")
    return value.strip()


def load_config(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        try:
            config = json.load(file)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Config JSON error: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError("Config root value must be a JSON object")
    return expand_env(config)


def get_cycle_config(config: dict[str, Any]) -> dict[str, Any]:
    cycle = config.get("cycle")
    if not isinstance(cycle, dict):
        raise ConfigError("cycle section is required")

    required_numbers = [
        "cooling_setpoint_f",
        "resting_setpoint_f",
        "cooling_minutes",
        "resting_minutes",
    ]
    for key in required_numbers:
        if not isinstance(cycle.get(key), (int, float)):
            raise ConfigError(f"cycle.{key} must be a number")
        if float(cycle[key]) <= 0:
            raise ConfigError(f"cycle.{key} must be greater than zero")

    return cycle


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "tcl_cycle.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def read_json_response(response: Any) -> Any:
    raw_bytes = response.read()
    if response.headers.get("Content-Encoding", "").lower() == "gzip":
        raw_bytes = gzip.decompress(raw_bytes)
    raw = raw_bytes.decode("utf-8")
    if not raw:
        return None
    return json.loads(raw)


class ClimateBackend:
    def startup(self) -> None:
        return

    def apply_setpoint_f(self, setpoint_f: float, phase: str) -> None:
        raise NotImplementedError

    def set_power_switch(self, enabled: bool) -> None:
        raise NotImplementedError

    def set_swing_wind(self, enabled: bool) -> None:
        raise NotImplementedError

    def status(self) -> Any:
        return {"status": "This backend does not support status reads"}


class MockBackend(ClimateBackend):
    def __init__(self, config: dict[str, Any]):
        self.device_id = str(config.get("device_id", "unknown"))

    def apply_setpoint_f(self, setpoint_f: float, phase: str) -> None:
        logging.info(
            "MOCK: device=%s phase=%s setpoint=%.1fF / %.1fC",
            self.device_id,
            phase,
            setpoint_f,
            fahrenheit_to_celsius(setpoint_f),
        )

    def startup(self) -> None:
        logging.info("MOCK: device=%s startup", self.device_id)

    def set_power_switch(self, enabled: bool) -> None:
        logging.info("MOCK: device=%s power_switch=%d", self.device_id, 1 if enabled else 0)

    def set_swing_wind(self, enabled: bool) -> None:
        logging.info("MOCK: device=%s swing_wind=%d", self.device_id, 1 if enabled else 0)

    def status(self) -> Any:
        return {"backend": "mock", "device_id": self.device_id}


class TclHomeAwsBackend(ClimateBackend):
    def __init__(self, config: dict[str, Any]):
        backend_config = self._backend_config(config)
        self.api_base_url = require_text(
            backend_config,
            "api_base_url",
            "backends.tcl_home_aws",
        ).rstrip("/")
        self.iot_data_endpoint = require_text(
            backend_config,
            "iot_data_endpoint",
            "backends.tcl_home_aws",
        ).rstrip("/")
        self.device_id = require_text(backend_config, "device_id", "backends.tcl_home_aws")
        self.sso_token = require_text(backend_config, "sso_token", "backends.tcl_home_aws")
        self.app_id = str(backend_config.get("app_id", "wx6e1af3fa84fbe523"))
        self.region = str(backend_config.get("region", "eu-central-1"))
        self.timeout_seconds = float(backend_config.get("timeout_seconds", 20))
        self.login_providers = backend_config.get("login_providers", ["cognito-identity.amazonaws.com"])
        if not isinstance(self.login_providers, list) or not self.login_providers:
            raise ConfigError("backends.tcl_home_aws.login_providers must be a non-empty list")

        startup_desired = backend_config.get("startup_desired", {})
        if startup_desired is None:
            startup_desired = {}
        if not isinstance(startup_desired, dict):
            raise ConfigError("backends.tcl_home_aws.startup_desired must be an object")
        self.startup_desired = startup_desired

        self.aws_access_key: str | None = None
        self.aws_secret_key: str | None = None
        self.aws_session_token: str | None = None
        self.aws_credentials_expires_at = 0.0
        self.mqtt_endpoint: str | None = None

    @staticmethod
    def _backend_config(config: dict[str, Any]) -> dict[str, Any]:
        backends = config.get("backends")
        if not isinstance(backends, dict) or not isinstance(backends.get("tcl_home_aws"), dict):
            raise ConfigError("backends.tcl_home_aws section is required")
        return backends["tcl_home_aws"]

    def _request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
    ) -> Any:
        body_text = "" if body is None else json.dumps(body, separators=(",", ":"))
        data = None if body is None else body_text.encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return read_json_response(response)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise BackendError(f"HTTP {exc.code} for {url}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"Connection error for {url}: {exc}") from exc

    def _load_balance(self) -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            self.api_base_url + "/v1/auth/service/loadBalance",
            {
                "appid": self.app_id,
                "ssotoken": self.sso_token,
                "Accept-Encoding": "identity",
                "User-Agent": "Dart/3.4 (dart:io)",
            },
        )
        if not isinstance(payload, dict) or int(payload.get("code", 0)) != 200:
            raise BackendError(f"TCL loadBalance failed: {payload}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BackendError(f"TCL loadBalance returned no data: {payload}")
        return data

    def _cognito_credentials_for_provider(
        self,
        identity_id: str,
        cognito_token: str,
        login_provider: str,
    ) -> dict[str, Any]:
        url = f"https://cognito-identity.{self.region}.amazonaws.com/"
        return self._request_json(
            "POST",
            url,
            {
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
                "Accept-Encoding": "identity",
            },
            {
                "IdentityId": identity_id,
                "Logins": {login_provider: cognito_token},
            },
        )

    def _credential_expiration(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            expiration = float(value)
            if expiration > 10_000_000_000:
                expiration /= 1000.0
            return expiration
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.datetime.fromisoformat(normalized).timestamp()
            except ValueError:
                pass
        return time.time() + 3600.0

    def _ensure_aws_credentials(self) -> tuple[str, str, str]:
        if (
            self.aws_access_key
            and self.aws_secret_key
            and self.aws_session_token
            and time.time() < self.aws_credentials_expires_at - 300
        ):
            return self.aws_access_key, self.aws_secret_key, self.aws_session_token

        data = self._load_balance()
        if isinstance(data.get("mqttEndpoint"), str):
            self.mqtt_endpoint = str(data["mqttEndpoint"])
        identity_id = str(data.get("cognitoId", ""))
        cognito_token = str(data.get("cognitoToken", ""))
        if not identity_id or not cognito_token:
            raise BackendError("TCL loadBalance did not return cognitoId/cognitoToken")

        last_error: BackendError | None = None
        credential_payload: dict[str, Any] | None = None
        for provider in self.login_providers:
            try:
                credential_payload = self._cognito_credentials_for_provider(
                    identity_id,
                    cognito_token,
                    str(provider),
                )
                break
            except BackendError as exc:
                last_error = exc
        if credential_payload is None:
            raise BackendError(f"AWS Cognito credentials failed: {last_error}")

        credentials = credential_payload.get("Credentials") or credential_payload.get("credentials")
        if not isinstance(credentials, dict):
            raise BackendError(f"AWS Cognito returned no credentials: {credential_payload}")

        access_key = str(credentials.get("AccessKeyId", ""))
        secret_key = str(credentials.get("SecretKey") or credentials.get("SecretAccessKey") or "")
        session_token = str(credentials.get("SessionToken", ""))
        if not access_key or not secret_key or not session_token:
            raise BackendError("AWS Cognito credentials response is incomplete")

        self.aws_access_key = access_key
        self.aws_secret_key = secret_key
        self.aws_session_token = session_token
        self.aws_credentials_expires_at = self._credential_expiration(credentials.get("Expiration"))
        logging.info(
            "TCL Home AWS credentials refreshed, expires in %.0f min",
            max(0.0, (self.aws_credentials_expires_at - time.time()) / 60.0),
        )
        return access_key, secret_key, session_token

    @staticmethod
    def _aws_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
        k_date = hmac.new(("AWS4" + secret_key).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
        k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
        return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()

    def _aws_headers(
        self,
        method: str,
        canonical_uri: str,
        canonical_query: str,
        body_text: str,
    ) -> dict[str, str]:
        access_key, secret_key, session_token = self._ensure_aws_credentials()
        parsed_endpoint = urllib.parse.urlparse(self.iot_data_endpoint)
        host = parsed_endpoint.netloc
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body_text.encode("utf-8")).hexdigest()

        canonical_headers = (
            f"host:{host}\n"
            f"x-amz-date:{amz_date}\n"
            f"x-amz-security-token:{session_token}\n"
        )
        signed_headers = "host;x-amz-date;x-amz-security-token"
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self.region}/iotdata/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._aws_signature_key(secret_key, date_stamp, self.region, "iotdata")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "X-Amz-Date": amz_date,
            "x-amz-security-token": session_token,
            "Content-Type": "application/x-amz-json-1.0",
            "Accept-Encoding": "identity",
            "User-Agent": "tcl-cycle/1.0",
        }

    def _aws_presigned_mqtt_url(self) -> str:
        access_key, secret_key, session_token = self._ensure_aws_credentials()
        endpoint = self.mqtt_endpoint or self.iot_data_endpoint
        parsed = urllib.parse.urlparse(endpoint)
        host = parsed.hostname or parsed.netloc or endpoint
        host = host.split(":", 1)[0]
        canonical_host = host
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        credential_scope = f"{date_stamp}/{self.region}/iotdata/aws4_request"
        params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{access_key}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-SignedHeaders": "host",
        }
        url_params = dict(params)
        url_params["X-Amz-Security-Token"] = session_token
        canonical_query = "&".join(
            f"{urllib.parse.quote(key, safe='-_.~')}={urllib.parse.quote(str(params[key]), safe='-_.~')}"
            for key in sorted(params)
        )
        canonical_request = "\n".join(
            [
                "GET",
                "/mqtt",
                canonical_query,
                f"host:{canonical_host}\n",
                "host",
                hashlib.sha256(b"").hexdigest(),
            ]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._aws_signature_key(secret_key, date_stamp, self.region, "iotdata")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        url_query = "&".join(
            f"{urllib.parse.quote(key, safe='-_.~')}={urllib.parse.quote(str(url_params[key]), safe='-_.~')}"
            for key in sorted(url_params)
        )
        return f"wss://{host}/mqtt?{url_query}&X-Amz-Signature={signature}"

    @staticmethod
    def _mqtt_remaining_length(length: int) -> bytes:
        encoded = bytearray()
        while True:
            digit = length % 128
            length //= 128
            if length > 0:
                digit |= 128
            encoded.append(digit)
            if length == 0:
                return bytes(encoded)

    @staticmethod
    def _mqtt_string(value: str) -> bytes:
        raw = value.encode("utf-8")
        return len(raw).to_bytes(2, "big") + raw

    def _mqtt_connect_packet(self, client_id: str) -> bytes:
        variable_header = self._mqtt_string("MQTT") + bytes([4, 2]) + (60).to_bytes(2, "big")
        payload = self._mqtt_string(client_id)
        remaining = variable_header + payload
        return bytes([0x10]) + self._mqtt_remaining_length(len(remaining)) + remaining

    def _mqtt_publish_packet(self, topic: str, payload: dict[str, Any]) -> bytes:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        remaining = self._mqtt_string(topic) + body
        return bytes([0x30]) + self._mqtt_remaining_length(len(remaining)) + remaining

    def _mqtt_ws_publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            import websocket
        except ImportError as exc:
            raise BackendError("websocket-client package is required for mqtt_ws") from exc

        client_id = f"python_{uuid.uuid4().hex[:16]}"
        url = self._aws_presigned_mqtt_url()
        logging.info("TCL Home AWS: opening MQTT WebSocket client_id=%s", client_id)
        ws = websocket.create_connection(
            url,
            timeout=self.timeout_seconds,
            subprotocols=["mqtt"],
        )
        try:
            ws.send_binary(self._mqtt_connect_packet(client_id))
            connack = ws.recv()
            if isinstance(connack, str):
                connack_bytes = connack.encode("latin1")
            else:
                connack_bytes = bytes(connack)
            if len(connack_bytes) < 4 or connack_bytes[0] != 0x20 or connack_bytes[3] != 0:
                raise BackendError(f"MQTT CONNACK failed: {connack_bytes!r}")
            ws.send_binary(self._mqtt_publish_packet(topic, payload))
            time.sleep(0.5)
        finally:
            ws.close()

    def _iot_data(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: str = "",
    ) -> Any:
        canonical_uri = urllib.parse.quote(path, safe="/~")
        body_text = "" if body is None else json.dumps(body, separators=(",", ":"))
        url = self.iot_data_endpoint + canonical_uri
        if query:
            url += "?" + query
        headers = self._aws_headers(method, canonical_uri, query, body_text)
        return self._request_json(method, url, headers, body)

    def _build_desired_state(self, setpoint_f: float) -> dict[str, Any]:
        return {
            "targetCelsiusDegree": fahrenheit_to_tcl_celsius(setpoint_f),
            "targetFahrenheitDegree": int(round(setpoint_f)),
        }

    def _send_desired_state(self, desired: dict[str, Any], token_prefix: str) -> None:
        payload = {
            "state": {"desired": desired},
            "clientToken": f"{token_prefix}_{int(time.time() * 1000)}",
        }
        self._mqtt_ws_publish(f"$aws/things/{self.device_id}/shadow/update", payload)

    def startup(self) -> None:
        if not self.startup_desired:
            return
        logging.info("TCL Home AWS: sending startup desired state: %s", self.startup_desired)
        self._send_desired_state(self.startup_desired, "python_startup")

    def apply_setpoint_f(self, setpoint_f: float, phase: str) -> None:
        desired = self._build_desired_state(setpoint_f)
        logging.info(
            "TCL Home AWS: sending %s setpoint %sF / %sC",
            phase,
            desired["targetFahrenheitDegree"],
            desired["targetCelsiusDegree"],
        )
        self._send_desired_state(desired, "python")

    def set_power_switch(self, enabled: bool) -> None:
        desired = {"powerSwitch": 1 if enabled else 0}
        logging.info("TCL Home AWS: sending powerSwitch=%d", desired["powerSwitch"])
        self._send_desired_state(desired, "python_power")

    def set_swing_wind(self, enabled: bool) -> None:
        desired = {"swingWind": 1 if enabled else 0}
        logging.info("TCL Home AWS: sending swingWind=%d", desired["swingWind"])
        self._send_desired_state(desired, "python_swing")

    def status(self) -> Any:
        return self._iot_data("GET", f"/things/{self.device_id}/shadow")


def create_backend(config: dict[str, Any], cycle: dict[str, Any]) -> ClimateBackend:
    backend_name = str(config.get("backend", "mock")).lower()
    if backend_name == "mock":
        return MockBackend(config)
    if backend_name == "tcl_home_aws":
        return TclHomeAwsBackend(config)
    raise ConfigError(f"Unsupported backend: {backend_name}")


class CycleRunner:
    def __init__(self, backend: ClimateBackend, config: dict[str, Any], cycle: dict[str, Any]):
        self.backend = backend
        self.config = config
        self.cycle = cycle
        self.stop_event = threading.Event()
        safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
        self.min_seconds_between_commands = float(safety.get("min_seconds_between_commands", 30))
        self.status_log_seconds = float(safety.get("status_log_seconds", 60))
        self.last_command_at = 0.0

    def stop(self, signum: int | None = None, frame: Any | None = None) -> None:
        logging.info("Stop signal received")
        self.stop_event.set()

    def _safe_apply(self, setpoint_f: float, phase: str) -> None:
        elapsed = time.monotonic() - self.last_command_at
        if self.last_command_at and elapsed < self.min_seconds_between_commands:
            wait_seconds = self.min_seconds_between_commands - elapsed
            logging.info("Safety wait: %.0f seconds", wait_seconds)
            if self.stop_event.wait(wait_seconds):
                return
        self.backend.apply_setpoint_f(setpoint_f, phase)
        self.last_command_at = time.monotonic()

    def _wait_minutes(self, minutes: float, label: str) -> bool:
        total_seconds = minutes * 60.0
        end_at = time.monotonic() + total_seconds
        while not self.stop_event.is_set():
            remaining = end_at - time.monotonic()
            if remaining <= 0:
                return True
            logging.info("%s running, remaining %.1f min", label, remaining / 60.0)
            if self.stop_event.wait(min(self.status_log_seconds, remaining)):
                return False
        return False

    def apply_phase(self, phase: str) -> None:
        if phase == "cooling":
            self._safe_apply(float(self.cycle["cooling_setpoint_f"]), "cooling")
            return
        if phase == "resting":
            self._safe_apply(float(self.cycle["resting_setpoint_f"]), "resting")
            return
        raise ConfigError("phase must be cooling or resting")

    def run(self, max_cycles: int | None = None) -> None:
        cycle_number = 0
        self.backend.startup()
        while not self.stop_event.is_set():
            cycle_number += 1
            logging.info("Cycle %d started", cycle_number)

            self.apply_phase("cooling")
            if not self._wait_minutes(float(self.cycle["cooling_minutes"]), "70F cooling phase"):
                break

            self.apply_phase("resting")
            if not self._wait_minutes(float(self.cycle["resting_minutes"]), "80F resting phase"):
                break

            logging.info("Cycle %d finished", cycle_number)
            if max_cycles is not None and cycle_number >= max_cycles:
                break
        logging.info("Runner stopped")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=CONFIG_DEFAULT, help="Config file path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TCL portable AC 70F/80F cycle tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate config file")
    add_common_args(validate_parser)

    run_parser = subparsers.add_parser("run", help="Start cycle")
    add_common_args(run_parser)
    run_parser.add_argument("--cycles", type=int, default=None, help="Run only the given number of cycles")

    once_parser = subparsers.add_parser("once", help="Send one phase command")
    add_common_args(once_parser)
    once_parser.add_argument("phase", choices=["cooling", "resting"], help="Phase to send")

    startup_parser = subparsers.add_parser("startup", help="Send startup command")
    add_common_args(startup_parser)

    status_parser = subparsers.add_parser("status", help="Read backend status")
    add_common_args(status_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(pathlib.Path(args.config))
        cycle = get_cycle_config(config)
        backend = create_backend(config, cycle)
        runner = CycleRunner(backend, config, cycle)

        if args.command == "validate":
            logging.info("Config file is valid: %s", args.config)
            logging.info(
                "Cycle: %.1f min %.1fF, %.1f min %.1fF",
                float(cycle["cooling_minutes"]),
                float(cycle["cooling_setpoint_f"]),
                float(cycle["resting_minutes"]),
                float(cycle["resting_setpoint_f"]),
            )
            return 0

        if args.command == "status":
            print(json.dumps(backend.status(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "once":
            runner.apply_phase(args.phase)
            return 0

        if args.command == "startup":
            backend.startup()
            return 0

        if args.command == "run":
            signal.signal(signal.SIGINT, runner.stop)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, runner.stop)
            runner.run(max_cycles=args.cycles)
            return 0

        parser.print_help()
        return 2
    except (ConfigError, BackendError) as exc:
        logging.error("Error: %s", exc)
        return 1
    except KeyboardInterrupt:
        logging.info("Stopped by keyboard")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
