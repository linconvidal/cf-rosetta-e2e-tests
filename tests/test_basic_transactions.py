import pytest
import logging

logger = logging.getLogger(__name__)


def test_send_ada(rosetta_client, test_wallet):
    """
    Basic transaction test that:
      1) Fetches a UTXO from the wallet
      2) Constructs a transaction with 1 input and 2 outputs (destination + change)
      3) Signs with PyCardano
      4) Submits via Rosetta
      5) Performs assertions

    The transaction structure follows Cardano's UTXO model where typically:
    - One input is consumed (the UTXO)
    - Two outputs are created:
        a) The actual transfer to the destination
        b) The change returned to sender (input amount - transfer - fee)

    Logging:
    - INFO level: Transaction submission success with ID, amount and fee
    - DEBUG level: Detailed transaction breakdown including UTXO, amounts, and hash verification
    """
    transfer_amount = 2_000_000  # 2 ADA in lovelace
    estimated_fee = 180_000  # 0.18 ADA initial estimate for UTXO selection

    logger.debug(
        "Starting transaction test with transfer amount: %d lovelace", transfer_amount
    )

    # Step 1: Select a suitable UTXO
    first_utxo = test_wallet.select_ada_only_utxo(
        rosetta_client=rosetta_client, min_amount=transfer_amount + estimated_fee
    )
    logger.debug("Selected UTXO: %s", first_utxo)

    # Ensure value is handled as integer
    input_value = int(first_utxo["amount"]["value"])

    # Build input in the format expected by RosettaClient._build_operations
    input_data = {
        "address": str(test_wallet.address),
        "value": input_value,
        "coin_identifier": first_utxo["coin_identifier"],
        "coin_change": {
            "coin_identifier": first_utxo["coin_identifier"],
            "coin_action": "coin_spent",
        },
    }

    # Calculate change amount considering estimated fee
    change_amount = input_value - transfer_amount - estimated_fee

    # Define outputs with estimated fee
    outputs = [
        {
            "address": str(test_wallet.address),
            "value": transfer_amount,
        },
        {
            "address": str(test_wallet.address),
            "value": change_amount,
        },
    ]

    # Step 2: Construct the transaction
    constructed_tx = rosetta_client.construct_transaction(
        inputs=[input_data], outputs=outputs
    )
    logger.debug("Constructed transaction: %s", constructed_tx)

    # Step 3: Sign with PyCardano
    signature = test_wallet.sign_transaction(constructed_tx)
    logger.debug("Transaction signature: %s", signature)

    # Step 4: Combine unsigned transaction with signature
    combined_tx = rosetta_client.combine_transaction(
        unsigned_transaction=constructed_tx["unsigned_transaction"],
        signatures=[signature],
    )
    logger.debug("Combined transaction: %s", combined_tx)

    # Step 5: Submit transaction
    submit_response = rosetta_client.submit_transaction(
        combined_tx["signed_transaction"]
    )

    # Assertions and logging of final result
    assert (
        "transaction_identifier" in submit_response
    ), "Failed: no transaction_identifier returned."
    tx_id = submit_response["transaction_identifier"]["hash"]
    assert tx_id, "Empty transaction hash!"

    # Log only the essential transaction information at INFO level
    logger.info(
        "Transaction submitted successfully - ID: %s (Amount: %d lovelace, Fee: %d lovelace)",
        tx_id,
        transfer_amount,
        estimated_fee,
    )

    # Log detailed breakdown at DEBUG level
    logger.debug("Transaction details:")
    logger.debug("- Input UTXO: %s", first_utxo["coin_identifier"]["identifier"])
    logger.debug("- Input amount: %d lovelace", input_value)
    logger.debug("- Transfer amount: %d lovelace", transfer_amount)
    logger.debug("- Fee: %d lovelace", estimated_fee)
    logger.debug("- Change amount: %d lovelace", change_amount)

    # Verify transaction hash
    hash_resp = rosetta_client.get_transaction_hash(combined_tx["signed_transaction"])
    verified_hash = hash_resp["transaction_identifier"]["hash"]
    logger.debug("Transaction hash verified: %s", verified_hash)
    assert verified_hash == tx_id, "Transaction hash mismatch!"
