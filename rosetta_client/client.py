from typing import Dict, List, Optional
import requests
import json
import logging
from .exceptions import NetworkError, ValidationError


logger = logging.getLogger(__name__)


class RosettaClient:
    """Client for interacting with Cardano Rosetta API"""

    def __init__(self, endpoint: str, network: str = "testnet"):
        self.endpoint = endpoint.rstrip("/")
        self.network = network
        self.headers = {"Content-Type": "application/json"}

    def _get_network_identifier(self) -> Dict:
        return {"blockchain": "cardano", "network": self.network}

    def network_status(self) -> Dict:
        """Get current network status"""
        try:
            response = requests.post(
                f"{self.endpoint}/network/status",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "metadata": {},
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if 400 <= status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            raise NetworkError(f"Network error: {str(req_err)}")

    def get_balance(self, address: str) -> Dict:
        """Get account balance"""
        try:
            response = requests.post(
                f"{self.endpoint}/account/balance",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "account_identifier": {"address": address},
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if 400 <= status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            raise NetworkError(f"Network error: {str(req_err)}")

    def get_utxos(self, address: str) -> List[Dict]:
        """Get UTXOs for an address"""
        try:
            response = requests.post(
                f"{self.endpoint}/account/coins",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "account_identifier": {"address": address},
                    "include_mempool": True,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("coins", [])
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if 400 <= status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            raise NetworkError(f"Network error: {str(req_err)}")

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
            "=" * 50,
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

            preprocess_response = requests.post(
                f"{self.endpoint}/construction/preprocess",
                json=preprocess_payload,
                headers=self.headers,
            )
            preprocess_response.raise_for_status()
            preprocess_data = preprocess_response.json()

            # Step 2: /construction/metadata
            # Fetches network-specific metadata (e.g. recent block hash, suggested fee)
            metadata_payload = {
                "network_identifier": self._get_network_identifier(),
                "options": preprocess_data["options"],
                "public_keys": [],  # Add if needed for multi-sig
            }
            self._log_request("/construction/metadata", metadata_payload)

            metadata_response = requests.post(
                f"{self.endpoint}/construction/metadata",
                json=metadata_payload,
                headers=self.headers,
            )
            metadata_response.raise_for_status()
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
                    raise ValidationError(
                        f"Fee is greater than the total input: "
                        f"inputs={total_input}, outputs={total_output}, fee={suggested_fee}"
                    )

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

            payloads_response = requests.post(
                f"{self.endpoint}/construction/payloads",
                json=payloads_payload,
                headers=self.headers,
            )
            payloads_response.raise_for_status()
            return payloads_response.json()

        except requests.exceptions.HTTPError as http_err:
            error_response = None
            try:
                error_response = http_err.response.json()
            except:
                pass

            logger.error(
                "HTTP Error %d: %s\nResponse: %s",
                http_err.response.status_code,
                str(http_err),
                (
                    json.dumps(error_response, indent=2)
                    if error_response
                    else "No response body"
                ),
            )

            if 400 <= http_err.response.status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            logger.error("Request Error: %s", str(req_err))
            raise NetworkError(f"Network error: {str(req_err)}")

    def submit_transaction(self, signed_transaction: str) -> Dict:
        """Submit a signed transaction"""
        try:
            response = requests.post(
                f"{self.endpoint}/construction/submit",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "signed_transaction": signed_transaction,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if 400 <= status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            raise NetworkError(f"Network error: {str(req_err)}")

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
            response = requests.post(
                f"{self.endpoint}/construction/parse",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "signed": signed,
                    "transaction": transaction_hex,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if 400 <= status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            raise NetworkError(f"Network error: {str(req_err)}")

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
            response = requests.post(
                f"{self.endpoint}/construction/hash",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "signed_transaction": signed_transaction,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if 400 <= status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            raise NetworkError(f"Network error: {str(req_err)}")

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
            response = requests.post(
                f"{self.endpoint}/construction/combine",
                json={
                    "network_identifier": self._get_network_identifier(),
                    "unsigned_transaction": unsigned_transaction,
                    "signatures": signatures,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            if 400 <= status_code < 500:
                raise ValidationError(f"Validation error: {str(http_err)}")
            else:
                raise NetworkError(f"Server/network error: {str(http_err)}")
        except requests.exceptions.RequestException as req_err:
            raise NetworkError(f"Network error: {str(req_err)}")
