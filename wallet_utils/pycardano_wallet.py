from typing import List, Dict, Optional, Union
from pycardano import (
    Address,
    PaymentVerificationKey,
    PaymentSigningKey,
    PaymentExtendedSigningKey,
    PaymentExtendedVerificationKey,
    StakeExtendedSigningKey,
    StakeExtendedVerificationKey,
    Network,
    HDWallet,
    Transaction,
    TransactionBody,
    TransactionWitnessSet,
    PlutusData,
    Redeemer,
    AuxiliaryData,
    NativeScript,
    VerificationKeyWitness,
    Metadata,
)
from mnemonic import Mnemonic
import cbor2
import logging

logger = logging.getLogger(__name__)


class PyCardanoWallet:
    """Wrapper for PyCardano wallet operations"""

    def __init__(self, network: str = "testnet"):
        self.network = Network.TESTNET if network == "testnet" else Network.MAINNET
        self.payment_signing_key: Optional[PaymentExtendedSigningKey] = None
        self.payment_verification_key: Optional[PaymentExtendedVerificationKey] = None
        self.stake_signing_key: Optional[StakeExtendedSigningKey] = None
        self.stake_verification_key: Optional[StakeExtendedVerificationKey] = None
        self.address: Optional[Address] = None
        self.hd_wallet: Optional[HDWallet] = None

    @classmethod
    def from_mnemonic(
        cls, mnemonic: str, network: str = "testnet", address_type: str = "base"
    ) -> "PyCardanoWallet":
        """Create wallet instance from mnemonic phrase

        Args:
            mnemonic: The mnemonic seed phrase
            network: Network to use ("testnet" or "mainnet")
            address_type: Type of address to create ("base", "enterprise", or "stake")

        Returns:
            PyCardanoWallet instance
        """
        # Validate mnemonic
        if not Mnemonic("english").check(mnemonic):
            raise ValueError("Invalid mnemonic phrase")

        wallet = cls(network)
        # Create HD wallet from mnemonic
        wallet.hd_wallet = HDWallet.from_mnemonic(mnemonic)

        # Derive payment keys (using path 1852H/1815H/0H/0/0 for Cardano)
        payment_derived_wallet = wallet.hd_wallet.derive_from_path(
            "m/1852'/1815'/0'/0/0"
        )
        wallet.payment_signing_key = PaymentExtendedSigningKey.from_hdwallet(
            payment_derived_wallet
        )
        wallet.payment_verification_key = (
            wallet.payment_signing_key.to_verification_key()
        )

        # Derive stake keys (using path 1852H/1815H/0H/2/0 for Cardano)
        stake_derived_wallet = wallet.hd_wallet.derive_from_path("m/1852'/1815'/0'/2/0")
        wallet.stake_signing_key = StakeExtendedSigningKey.from_hdwallet(
            stake_derived_wallet
        )
        wallet.stake_verification_key = wallet.stake_signing_key.to_verification_key()

        # Create appropriate address type
        if address_type == "base":
            # Base address with both payment and staking capabilities
            wallet.address = Address(
                payment_part=wallet.payment_verification_key.hash(),
                staking_part=wallet.stake_verification_key.hash(),
                network=wallet.network,
            )
        elif address_type == "enterprise":
            # Enterprise address with only payment capabilities
            wallet.address = Address(
                payment_part=wallet.payment_verification_key.hash(),
                network=wallet.network,
            )
        elif address_type == "stake":
            # Stake address with only staking capabilities
            wallet.address = Address(
                staking_part=wallet.stake_verification_key.hash(),
                network=wallet.network,
            )
        else:
            raise ValueError(
                "Invalid address type. Must be one of: base, enterprise, stake"
            )

        return wallet

    # @classmethod
    # def create_test_wallet(cls) -> 'PyCardanoWallet':
    #     """Create a new wallet for testing purposes"""
    #     wallet = cls()
    #     wallet.payment_signing_key = PaymentSigningKey.generate()
    #     wallet.payment_verification_key = PaymentVerificationKey.from_signing_key(
    #         wallet.payment_signing_key
    #     )
    #     wallet.address = Address(
    #         payment_part=wallet.payment_verification_key.hash(),
    #         network=wallet.network
    #     )
    #     return wallet

    def get_test_addresses(self) -> List[str]:
        """Get list of test addresses"""
        if not self.address:
            raise ValueError("Wallet not initialized")
        return [str(self.address)]

    def sign_transaction(self, tx_data: Dict) -> Dict:
        """
        Sign a transaction payload from Rosetta API

        Args:
            tx_data: Transaction data from Rosetta construction/payloads endpoint

        Returns:
            Dictionary containing the signature information required by the /construction/combine endpoint
        """
        if not self.payment_signing_key:
            raise ValueError("No signing key available")

        # Extract signing payload
        signing_payload = tx_data.get("payloads", [{}])[0]

        # Get the hex bytes to sign
        hex_bytes = signing_payload.get("hex_bytes")
        if not hex_bytes:
            raise ValueError("No hex_bytes found in signing payload")

        # Sign the payload
        signature = self.payment_signing_key.sign(bytes.fromhex(hex_bytes))

        # Get the raw verification key bytes (32 bytes)
        # The verification key is the first 32 bytes of the key data
        vkey_bytes = bytes(self.payment_verification_key)[:32]

        logger.debug("Verification key length: %d bytes", len(vkey_bytes))
        logger.debug("Verification key hex: %s", vkey_bytes.hex())

        # Return the signature in the format expected by /construction/combine
        return {
            "signing_payload": signing_payload,
            "public_key": {"hex_bytes": vkey_bytes.hex(), "curve_type": "edwards25519"},
            "signature_type": "ed25519",
            "hex_bytes": signature.hex(),
        }

    def get_address(self) -> str:
        """Get wallet's primary address"""
        if not self.address:
            raise ValueError("Wallet not initialized")
        return str(self.address)

    def get_public_key(self) -> str:
        """Get wallet's public key hex"""
        if not self.payment_verification_key:
            raise ValueError("Wallet not initialized")
        return self.payment_verification_key.to_cbor().hex()

    def select_utxos(
        self,
        rosetta_client,
        min_ada_required: Optional[int] = None,
        required_assets: Optional[List[Dict]] = None,
        exclude_utxos: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Select UTXOs that satisfy the given requirements.

        Args:
            rosetta_client: RosettaClient instance to fetch UTXOs
            min_ada_required: Minimum ADA amount required (in lovelace)
            required_assets: List of assets that must be present in the UTXO(s)
                           Format: [{"policy_id": "...", "asset_name": "...", "amount": int}]
            exclude_utxos: List of UTXO identifiers to exclude (e.g. being used in another tx)

        Returns:
            List of UTXOs that satisfy the requirements

        Raises:
            ValueError: If no suitable UTXOs found or if wallet not initialized
        """
        if not self.address:
            raise ValueError("Wallet not initialized")

        # Get all UTXOs
        utxos = rosetta_client.get_utxos(str(self.address))
        if not utxos:
            raise ValueError(f"No UTXOs found for address {self.address}")

        # Filter out excluded UTXOs
        if exclude_utxos:
            utxos = [
                utxo
                for utxo in utxos
                if utxo["coin_identifier"]["identifier"] not in exclude_utxos
            ]

        # Filter UTXOs based on requirements
        suitable_utxos = []
        for utxo in utxos:
            # Check minimum ADA requirement
            ada_amount = int(utxo["amount"]["value"])
            if min_ada_required and ada_amount < min_ada_required:
                continue

            # Check for required assets if specified
            if required_assets:
                has_all_assets = True
                utxo_assets = utxo.get("metadata", {}).get("assets", [])

                for required in required_assets:
                    asset_found = False
                    for asset in utxo_assets:
                        if (
                            asset.get("policy_id") == required["policy_id"]
                            and asset.get("asset_name") == required["asset_name"]
                            and int(asset.get("amount", 0)) >= required["amount"]
                        ):
                            asset_found = True
                            break
                    if not asset_found:
                        has_all_assets = False
                        break

                if not has_all_assets:
                    continue

            suitable_utxos.append(utxo)

        if not suitable_utxos:
            requirements = []
            if min_ada_required:
                requirements.append(f"min {min_ada_required} lovelace")
            if required_assets:
                requirements.append(f"assets: {required_assets}")
            raise ValueError(
                f"No suitable UTXOs found matching requirements: {', '.join(requirements)}"
            )

        return suitable_utxos

    def select_ada_only_utxo(
        self, rosetta_client, min_amount: int, exclude_utxos: Optional[List[str]] = None
    ) -> Dict:
        """
        Select a single UTXO that contains only ADA (no native assets)
        with at least the specified amount.

        Args:
            rosetta_client: RosettaClient instance to fetch UTXOs
            min_amount: Minimum ADA amount required (in lovelace)
            exclude_utxos: List of UTXO identifiers to exclude

        Returns:
            A single UTXO that satisfies the requirements

        Raises:
            ValueError: If no suitable UTXO found
        """
        utxos = self.select_utxos(
            rosetta_client=rosetta_client,
            min_ada_required=min_amount,
            exclude_utxos=exclude_utxos,
        )

        # Further filter to find UTXOs with only ADA (no other assets)
        ada_only_utxos = [
            utxo
            for utxo in utxos
            if not utxo.get("metadata", {}).get("assets")  # No additional assets
        ]

        if not ada_only_utxos:
            raise ValueError(
                f"No UTXOs found with only ADA and minimum {min_amount} lovelace"
            )

        # Return the UTXO with the smallest amount that meets the requirement
        # This helps prevent UTXO fragmentation
        return min(ada_only_utxos, key=lambda u: int(u["amount"]["value"]))
