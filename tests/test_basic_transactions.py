import pytest
import logging
import time

logger = logging.getLogger("test")


def test_send_ada(rosetta_client, test_wallet):
    """
    Basic transaction test that:
      1) Fetches a UTXO from the wallet
      2) Constructs a transaction with 1 input and 2 outputs (destination + change)
      3) Signs with PyCardano
      4) Submits via Rosetta
      5) Performs assertions
      6) Waits for and validates the transaction on-chain

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
    change_amount = input_value - transfer_amount

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

    # Calculate the actual fee (input amount - sum of all outputs)
    output_values = [int(output["value"]) for output in outputs]
    actual_fee = input_value - sum(output_values)

    # Log only the essential transaction information at INFO level
    logger.info(
        "Transaction submitted successfully - ID: %s (Amount: %d lovelace, Fee: %d lovelace)",
        tx_id,
        transfer_amount,
        actual_fee,
    )

    # Log detailed breakdown at DEBUG level
    logger.debug("Transaction details:")
    logger.debug("- Input UTXO: %s", first_utxo["coin_identifier"]["identifier"])
    logger.debug("- Input amount: %d lovelace", input_value)
    logger.debug("- Transfer amount: %d lovelace", transfer_amount)
    logger.debug("- Fee: %d lovelace", actual_fee)
    logger.debug("- Change amount: %d lovelace", change_amount)

    # Verify transaction hash
    hash_resp = rosetta_client.get_transaction_hash(combined_tx["signed_transaction"])
    verified_hash = hash_resp["transaction_identifier"]["hash"]
    logger.debug("Transaction hash verified: %s", verified_hash)
    assert verified_hash == tx_id, "Transaction hash mismatch!"

    # Step 6: Wait for transaction to appear on-chain and validate it
    logger.info("Waiting for transaction to be included in a block...")

    # Define timeout and polling interval
    timeout_seconds = 180  # 3 minutes
    polling_interval = 5  # 5 seconds
    start_time = time.time()
    found_in_block = False
    current_block_identifier = None

    # Store original operations for later comparison
    original_operations = []
    # Input operation
    original_operations.append(
        {
            "type": "input",
            "address": str(test_wallet.address),
            "amount": -input_value,
            "coin_identifier": first_utxo["coin_identifier"]["identifier"],
        }
    )
    # Output operations
    for output in outputs:
        original_operations.append(
            {"type": "output", "address": output["address"], "amount": output["value"]}
        )

    # Poll the network until we find the transaction in a block
    while not found_in_block and (time.time() - start_time < timeout_seconds):
        # Get current network status
        network_status = rosetta_client.network_status()
        current_block_identifier = network_status.get("current_block_identifier")

        if not current_block_identifier:
            logger.warning("Could not get current block identifier, retrying...")
            time.sleep(polling_interval)
            continue

        # Get the current block
        try:
            block_data = rosetta_client.get_block(current_block_identifier)

            # Check if our transaction is in this block
            if "block" in block_data and "transactions" in block_data["block"]:
                for tx in block_data["block"]["transactions"]:
                    if tx["transaction_identifier"]["hash"] == tx_id:
                        found_in_block = True
                        logger.info(
                            "Transaction found in block %s",
                            current_block_identifier.get("index", "unknown"),
                        )
                        break
        except Exception as e:
            logger.warning("Error checking block: %s", str(e))

        if not found_in_block:
            logger.debug(
                "Transaction not found in block %s, waiting %d seconds...",
                current_block_identifier.get("index", "unknown"),
                polling_interval,
            )
            time.sleep(polling_interval)

    # Verify transaction was found on-chain
    assert (
        found_in_block
    ), f"Transaction {tx_id} not found on-chain within {timeout_seconds} seconds"

    # Step 7: Fetch and validate the on-chain transaction details
    logger.info("Validating on-chain transaction data...")

    block_tx_details = rosetta_client.get_block_transaction(
        current_block_identifier, tx_id
    )

    # Verify transaction exists in response
    assert (
        "transaction" in block_tx_details
    ), "Transaction details not found in response"
    onchain_tx = block_tx_details["transaction"]

    # Verify operations exist
    assert "operations" in onchain_tx, "Operations not found in transaction"
    onchain_ops = onchain_tx["operations"]

    # Validate number of operations
    assert len(onchain_ops) == len(original_operations), (
        f"Operation count mismatch: expected {len(original_operations)}, "
        f"got {len(onchain_ops)}"
    )

    # Validate operations
    input_ops = [op for op in onchain_ops if op["type"] == "input"]
    output_ops = [op for op in onchain_ops if op["type"] == "output"]

    # Validate input operations
    assert len(input_ops) == 1, f"Expected 1 input operation, got {len(input_ops)}"
    input_op = input_ops[0]
    assert input_op["account"]["address"] == str(
        test_wallet.address
    ), "Input address mismatch"
    assert int(input_op["amount"]["value"]) == -input_value, "Input amount mismatch"
    assert (
        input_op["coin_change"]["coin_identifier"]["identifier"]
        == first_utxo["coin_identifier"]["identifier"]
    ), "Input UTXO mismatch"

    # Validate output operations
    assert len(output_ops) == 2, f"Expected 2 output operations, got {len(output_ops)}"

    # Validate first output (transfer)
    transfer_op = next(
        (op for op in output_ops if int(op["amount"]["value"]) == transfer_amount), None
    )
    assert (
        transfer_op is not None
    ), f"Transfer output of {transfer_amount} lovelace not found"
    assert transfer_op["account"]["address"] == str(
        test_wallet.address
    ), "Transfer address mismatch"

    # Validate second output (change)
    change_op = next((op for op in output_ops if op != transfer_op), None)
    assert change_op is not None, "Change output not found"
    assert change_op["account"]["address"] == str(
        test_wallet.address
    ), "Change address mismatch"

    # Calculate and validate the actual on-chain fee
    onchain_input_value = sum(abs(int(op["amount"]["value"])) for op in input_ops)
    onchain_output_value = sum(int(op["amount"]["value"]) for op in output_ops)
    onchain_fee = onchain_input_value - onchain_output_value

    logger.info("On-chain fee: %d lovelace", onchain_fee)
    assert (
        onchain_fee == actual_fee
    ), f"Fee mismatch: expected {actual_fee}, got {onchain_fee}"

    # Final success message
    logger.info("Transaction successfully validated on-chain!")
