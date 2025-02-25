from typing import Dict, List, Optional
import requests
import json
import logging
import time
import uuid
from .exceptions import NetworkError, ValidationError


logger = logging.getLogger(__name__)


class RequestDebugger:
    """Wrapper for tracking HTTP request metrics and debugging information"""

    def __init__(self):
        self._request_history = {}
        self._request_counter = 0
        self._session_id = str(uuid.uuid4())[:8]
        self.logger = logging.getLogger("rosetta_client.http")
        self.direct_output = False  # Default to False to reduce verbosity

    def log(self, level, message, *args):
        """Log through both the logger and direct stdout if enabled"""
        formatted_message = message % args if args else message
        # Log through the Python logging system
        if level == "debug":
            self.logger.debug(message, *args)
        elif level == "info":
            self.logger.info(message, *args)
        elif level == "warning":
            self.logger.warning(message, *args)
        elif level == "error":
            self.logger.error(message, *args)

        # Also print directly to make sure it's visible in the test output
        if (
            self.direct_output and level != "debug"
        ):  # Skip debug messages for direct output
            print(formatted_message)

    def post(self, url, **kwargs):
        """Wrapper for requests.post with detailed metrics and logging"""
        request_id = f"{self._session_id}-{self._request_counter}"
        self._request_counter += 1

        # Capture request info
        debug_info = {
            "request_id": request_id,
            "method": "POST",
            "url": url,
            "timestamp": time.time(),
            "start_time": time.time(),
        }

        # Extract endpoint from URL for easier debugging
        endpoint = url.split("/")[-1] if "/" in url else url

        # Log the request - now using debug level
        self.logger.debug(
            "\n[REQUEST %s] %s %s", request_id, debug_info["method"], endpoint
        )

        # Capture request headers and payload if available
        headers = kwargs.get("headers", {})
        debug_info["headers"] = dict(headers)

        payload = kwargs.get("json")
        if payload:
            debug_info["payload"] = payload
            self.logger.debug(
                "[REQUEST %s] Headers: %s\nPayload: %s",
                request_id,
                json.dumps(headers, indent=2),
                json.dumps(payload, indent=2),
            )

        # Make the actual request with timing
        try:
            start_time = time.time()
            response = requests.post(url, **kwargs)
            end_time = time.time()

            # Calculate durations
            duration_ms = (end_time - start_time) * 1000
            debug_info["duration_ms"] = duration_ms
            debug_info["end_time"] = end_time

            # Log response info - using debug level
            status_color = "\033[92m" if response.status_code < 400 else "\033[91m"
            reset_color = "\033[0m"

            # For INFO level, use a much more compact logging format for requests
            if self.logger.level <= logging.INFO:
                self.logger.info(
                    "%s %s - %sStatus: %d%s (%.2f ms)",
                    debug_info["method"],
                    endpoint,
                    status_color,
                    response.status_code,
                    reset_color,
                    duration_ms,
                )

            # Detailed response info only at DEBUG level
            self.logger.debug(
                "\n[RESPONSE %s] %sStatus: %d%s - Duration: %.2f ms - Endpoint: %s",
                request_id,
                status_color,
                response.status_code,
                reset_color,
                duration_ms,
                endpoint,
            )

            # Try to parse and log response body - only at DEBUG level
            content_type = response.headers.get("Content-Type", "")
            debug_info["status_code"] = response.status_code
            debug_info["response_headers"] = dict(response.headers)
            debug_info["endpoint"] = endpoint

            if "application/json" in content_type:
                try:
                    response_json = response.json()
                    debug_info["response_body"] = response_json
                    self.logger.debug(
                        "[RESPONSE %s] Body: %s",
                        request_id,
                        json.dumps(response_json, indent=2),
                    )
                except Exception as e:
                    self.logger.debug(
                        "[RESPONSE %s] JSON parse error: %s", request_id, str(e)
                    )

            # Store request info
            self._request_history[request_id] = debug_info

            # Perform response validation
            response.raise_for_status()
            return response

        except Exception as e:
            # Log error - use warning level for errors as they're important
            if "response" in locals():
                debug_info["status_code"] = response.status_code
                debug_info["error"] = str(e)
                self.logger.warning(
                    "[ERROR %s] %s - Endpoint: %s", request_id, str(e), endpoint
                )
            else:
                debug_info["error"] = str(e)
                self.logger.warning(
                    "[ERROR %s] Connection error: %s - Endpoint: %s",
                    request_id,
                    str(e),
                    endpoint,
                )

            self._request_history[request_id] = debug_info
            raise  # Re-raise the exception

    def get_request_stats(self):
        """Get summary statistics about all requests in this session"""
        if not self._request_history:
            return {"count": 0, "total_duration_ms": 0, "avg_duration_ms": 0}

        count = len(self._request_history)
        durations = [
            r.get("duration_ms", 0)
            for r in self._request_history.values()
            if "duration_ms" in r
        ]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0

        status_counts = {}
        for req in self._request_history.values():
            status = req.get("status_code")
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "count": count,
            "total_duration_ms": total_duration,
            "avg_duration_ms": avg_duration,
            "status_codes": status_counts,
            "session_id": self._session_id,
        }

    def get_slowest_requests(self, limit=5):
        """Get the slowest requests in this session"""
        sorted_requests = sorted(
            [r for r in self._request_history.values() if "duration_ms" in r],
            key=lambda x: x["duration_ms"],
            reverse=True,
        )
        return sorted_requests[:limit]

    def print_summary_report(self):
        """Print a comprehensive summary of HTTP requests for this session"""
        stats = self.get_request_stats()

        if stats["count"] == 0:
            return  # Don't show anything if no requests were made

        # Define ANSI colors for the report
        BLUE = "\033[38;5;68m"  # Softer blue
        GREEN = "\033[38;5;71m"  # Muted green
        YELLOW = "\033[38;5;179m"  # Softer yellow
        RED = "\033[38;5;167m"  # Muted red
        GRAY = "\033[38;5;246m"  # Medium gray
        CYAN = "\033[38;5;109m"  # Muted cyan
        PURPLE = "\033[38;5;146m"  # Soft purple
        BOLD = "\033[1m"
        RESET = "\033[0m"

        # Print a single, elegant separator before the report begins
        self.log("info", f"\n{CYAN}{'═' * 80}{RESET}")

        # Header with precise spacing
        self.log(
            "info",
            f"{CYAN}HTTP SUMMARY{RESET}{GRAY} · Session {stats['session_id']}{RESET}",
        )

        # Core metrics presented with clarity and breathing room
        self.log(
            "info",
            f"{BLUE}●{RESET} {GRAY}Requests{RESET}    {BOLD}{stats['count']}{RESET}",
        )
        self.log(
            "info",
            f"{BLUE}●{RESET} {GRAY}Total time{RESET}  {BOLD}{stats['total_duration_ms']:.2f}ms{RESET}",
        )
        self.log(
            "info",
            f"{BLUE}●{RESET} {GRAY}Average{RESET}     {BOLD}{stats['avg_duration_ms']:.2f}ms{RESET}",
        )

        # Status codes in a clean, aligned format
        if stats.get("status_codes"):
            status_msg = f"{BLUE}●{RESET} {GRAY}Status{RESET}      "
            for code, count in stats["status_codes"].items():
                code_color = GREEN if code < 400 else RED
                status_msg += f"{code_color}{code}{RESET}{GRAY}×{count}{RESET}  "
            self.log("info", status_msg)

        # Slowest requests with perfect alignment (only at DEBUG level)
        if self.logger.level <= logging.DEBUG:
            slowest = self.get_slowest_requests(3)  # Just top 3 for cleaner output
            if slowest:
                self.log("debug", "")  # Subtle breathing space
                self.log("debug", f"{PURPLE}SLOWEST REQUESTS{RESET}")

                for i, req in enumerate(slowest):
                    endpoint = req.get(
                        "endpoint", req.get("url", "unknown").split("/")[-1]
                    )
                    duration = req.get("duration_ms", 0)

                    # Clean formatting with careful spacing
                    self.log("debug", f"{GRAY}{i+1}.{RESET} {endpoint}")
                    self.log(
                        "debug",
                        f"   {GRAY}Duration:{RESET} {BOLD}{duration:.2f}ms{RESET}",
                    )

                    # Show error if any - with subtle indentation
                    if "error" in req:
                        self.log(
                            "debug",
                            f"   {GRAY}Error:{RESET} {RED}{req['error']}{RESET}",
                        )

        # Elegant closing separator
        self.log("info", f"{CYAN}{'═' * 80}{RESET}\n")


class RosettaClient:
    """Client for interacting with Cardano Rosetta API"""

    def __init__(self, endpoint: str, network: str = "testnet"):
        self.endpoint = endpoint.rstrip("/")
        self.network = network
        self.headers = {"Content-Type": "application/json"}
        self.request_debugger = RequestDebugger()

    def _get_network_identifier(self) -> Dict:
        return {"blockchain": "cardano", "network": self.network}

    def _handle_request_error(self, err, context="API request"):
        """Centralized error handler for HTTP requests

        Args:
            err: The caught exception
            context: Description of the API context for error message

        Raises:
            ValidationError: For 4xx client errors
            NetworkError: For 5xx server errors and other network issues
        """
        if isinstance(err, requests.exceptions.HTTPError):
            status_code = err.response.status_code
            error_response = None
            try:
                error_response = err.response.json()
            except:
                pass

            logger.error(
                "HTTP Error %d: %s\nResponse: %s",
                status_code,
                str(err),
                (
                    json.dumps(error_response, indent=2)
                    if error_response
                    else "No response body"
                ),
            )

            if 400 <= status_code < 500:
                raise ValidationError(f"{context} validation error: {str(err)}")
            else:
                raise NetworkError(f"{context} server error: {str(err)}")
        else:
            logger.error("Request Error: %s", str(err))
            raise NetworkError(f"{context} network error: {str(err)}")

    def network_status(self) -> Dict:
        """Get current network status"""
        try:
            response = self.request_debugger.post(
                f"{self.endpoint}/network/status",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "metadata": {},
                },
                headers=self.headers,
            )
            return response.json()
        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Network status")

    def get_balance(self, address: str) -> Dict:
        """Get account balance"""
        try:
            response = self.request_debugger.post(
                f"{self.endpoint}/account/balance",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "account_identifier": {"address": address},
                },
                headers=self.headers,
            )
            return response.json()
        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Get balance")

    def get_utxos(self, address: str) -> List[Dict]:
        """Get UTXOs for an address"""
        try:
            response = self.request_debugger.post(
                f"{self.endpoint}/account/coins",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "account_identifier": {"address": address},
                    "include_mempool": True,
                },
                headers=self.headers,
            )
            data = response.json()
            return data.get("coins", [])
        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Get UTXOs")

    def _log_request(self, endpoint: str, payload: Dict) -> None:
        """Helper to log request details in a copy-pasteable format"""
        logger.debug(
            "\n=== %s Request ===\n"
            "curl -X POST %s \\\n"
            "-H 'Content-Type: application/json' \\\n"
            "-d '%s'\n"
            "%s",
            endpoint,
            f"{self.endpoint}{endpoint}",
            json.dumps(payload, indent=2),
            "=" * 80,
        )

    def construct_transaction(self, inputs: List[Dict], outputs: List[Dict]) -> Dict:
        """
        Construct a transaction using the Construction API.

        This method executes 3 steps as described in the Rosetta guide:
        1) /construction/preprocess - Generates metadata required for transaction construction
        2) /construction/metadata - Fetches network-specific metadata for transaction construction
        3) /construction/payloads - Creates an unsigned transaction and payloads to sign

        Args:
            inputs: List of UTXOs to spend. Each item must contain:
                   - address: str (sender address)
                   - value: int (amount in lovelace)
                   - coin_identifier: Dict (UTXO reference)
            outputs: List of outputs. Each item must contain:
                    - address: str (recipient address)
                    - value: int (amount in lovelace)

        Returns:
            Dict containing at minimum:
            {
                "unsigned_transaction": "<hex encoded CBOR>",
                "payloads": [
                    {
                        "hex_bytes": "...",
                        "signature_type": "..."
                    }
                ]
            }

        Raises:
            ValidationError: If request validation fails (HTTP 4xx)
            NetworkError: If server/network error occurs (HTTP 5xx, timeouts, etc)
        """
        try:
            # Step 1: /construction/preprocess
            # Generates options object required for metadata
            operations = self._build_operations(inputs, outputs)
            preprocess_payload = {
                "network_identifier": self._get_network_identifier(),
                "operations": operations,
                "metadata": {},
            }
            self._log_request("/construction/preprocess", preprocess_payload)

            preprocess_response = self.request_debugger.post(
                f"{self.endpoint}/construction/preprocess",
                json=preprocess_payload,
                headers=self.headers,
            )
            preprocess_data = preprocess_response.json()

            # Step 2: /construction/metadata
            # Fetches network-specific metadata (e.g. recent block hash, suggested fee)
            metadata_payload = {
                "network_identifier": self._get_network_identifier(),
                "options": preprocess_data["options"],
                "public_keys": [],  # Add if needed for multi-sig
            }
            self._log_request("/construction/metadata", metadata_payload)

            metadata_response = self.request_debugger.post(
                f"{self.endpoint}/construction/metadata",
                json=metadata_payload,
                headers=self.headers,
            )
            metadata = metadata_response.json()

            # Extract suggested fee if available and adjust outputs
            suggested_fee_info = metadata.get("suggested_fee", [])
            if suggested_fee_info:
                suggested_fee = int(suggested_fee_info[0]["value"])

                # Calculate total input value
                total_input = sum(int(input_data["value"]) for input_data in inputs)

                # Calculate total output value
                total_output = sum(int(output_data["value"]) for output_data in outputs)

                # Verify we have enough to cover the fee
                if suggested_fee > total_input:
                    error_msg = (
                        f"\nTransaction Fee Error:\n"
                        f"  Input amount:  {total_input:,} lovelace\n"
                        f"  Output amount: {total_output:,} lovelace\n"
                        f"  Required fee:  {suggested_fee:,} lovelace\n"
                        f"\nInsufficient funds to cover fee. Need {suggested_fee - total_input:,} more lovelace."
                    )
                    logger.error(error_msg)
                    raise ValidationError(error_msg)

                # Adjust the last output (assumed to be change) to account for the fee
                if outputs:
                    outputs[-1]["value"] = int(outputs[-1]["value"]) - suggested_fee

                # Rebuild operations with adjusted outputs
                operations = self._build_operations(inputs, outputs)

            # Step 3: /construction/payloads
            # Creates unsigned transaction and signing payloads
            payloads_payload = {
                "network_identifier": self._get_network_identifier(),
                "operations": operations,
                "metadata": metadata["metadata"],
            }
            self._log_request("/construction/payloads", payloads_payload)

            payloads_response = self.request_debugger.post(
                f"{self.endpoint}/construction/payloads",
                json=payloads_payload,
                headers=self.headers,
            )
            return payloads_response.json()

        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Construct transaction")

    def submit_transaction(self, signed_transaction: str) -> Dict:
        """Submit a signed transaction"""
        try:
            response = self.request_debugger.post(
                f"{self.endpoint}/construction/submit",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "signed_transaction": signed_transaction,
                },
                headers=self.headers,
            )
            return response.json()
        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Submit transaction")

    def parse_transaction(self, transaction_hex: str, signed: bool = False) -> Dict:
        """
        Parse a transaction to verify its operations (Step 5 in Rosetta guide).

        This method allows verification of transaction contents before or after signing
        by parsing the transaction and returning its operations.

        Args:
            transaction_hex: Hex-encoded transaction (signed or unsigned)
            signed: Boolean indicating if the transaction is signed

        Returns:
            Dict containing parsed transaction details including operations:
            {
                "operations": [...],
                "signers": [...],  # Only present if signed=True
                "metadata": {...}
            }

        Raises:
            ValidationError: If request validation fails (HTTP 4xx)
            NetworkError: If server/network error occurs (HTTP 5xx, timeouts, etc)
        """
        try:
            response = self.request_debugger.post(
                f"{self.endpoint}/construction/parse",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "signed": signed,
                    "transaction": transaction_hex,
                },
                headers=self.headers,
            )
            return response.json()
        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Parse transaction")

    def get_transaction_hash(self, signed_transaction: str) -> Dict:
        """
        Get the hash of a signed transaction (Step 8 in Rosetta guide).

        This method is useful for tracking the transaction status after submission
        or for verification purposes.

        Args:
            signed_transaction: Hex-encoded signed transaction

        Returns:
            Dict containing the transaction hash:
            {
                "transaction_identifier": {
                    "hash": "..."
                }
            }

        Raises:
            ValidationError: If request validation fails (HTTP 4xx)
            NetworkError: If server/network error occurs (HTTP 5xx, timeouts, etc)
        """
        try:
            response = self.request_debugger.post(
                f"{self.endpoint}/construction/hash",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "signed_transaction": signed_transaction,
                },
                headers=self.headers,
            )
            return response.json()
        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Get transaction hash")

    def _build_operations(self, inputs: List[Dict], outputs: List[Dict]) -> List[Dict]:
        """Helper method to build operations from inputs and outputs"""
        operations = []

        # Add input operations
        for idx, input_data in enumerate(inputs):
            operation = {
                "operation_identifier": {"index": idx},
                "type": "input",
                "status": "",  # Empty status as shown in the guide
                "account": {"address": input_data["address"]},
                "amount": {
                    "value": str(-input_data["value"]),  # Negative for inputs
                    "currency": {"symbol": "ADA", "decimals": 6},
                },
                "coin_change": {
                    "coin_identifier": {
                        "identifier": input_data["coin_change"]["coin_identifier"][
                            "identifier"
                        ]
                    },
                    "coin_action": "coin_spent",
                },
                "metadata": input_data.get(
                    "metadata", {}
                ),  # Always include metadata, empty dict if not provided
            }
            operations.append(operation)

        # Add output operations
        offset = len(inputs)
        for idx, output_data in enumerate(outputs):
            operation = {
                "operation_identifier": {"index": idx + offset},
                "type": "output",
                "status": "",  # Empty status as shown in the guide
                "account": {"address": output_data["address"]},
                "amount": {
                    "value": str(output_data["value"]),  # Positive for outputs
                    "currency": {"symbol": "ADA", "decimals": 6},
                },
                "metadata": output_data.get(
                    "metadata", {}
                ),  # Always include metadata, empty dict if not provided
            }
            operations.append(operation)

        return operations

    def combine_transaction(
        self, unsigned_transaction: str, signatures: List[Dict]
    ) -> Dict:
        """
        Combine an unsigned transaction with signatures using the /construction/combine endpoint

        Args:
            unsigned_transaction: The unsigned transaction string
            signatures: List of signatures from sign_transaction

        Returns:
            Response from the /construction/combine endpoint containing the signed transaction
        """
        try:
            response = self.request_debugger.post(
                f"{self.endpoint}/construction/combine",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "unsigned_transaction": unsigned_transaction,
                    "signatures": signatures,
                },
                headers=self.headers,
            )
            return response.json()
        except requests.exceptions.RequestException as err:
            self._handle_request_error(err, "Combine transaction")
