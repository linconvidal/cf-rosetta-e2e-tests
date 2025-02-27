import pytest
import logging
import time
from typing import List, Dict

logger = logging.getLogger("test")


@pytest.mark.parametrize(
    "num_inputs,num_outputs,scenario_name",
    [
        (1, 10, "fan-out"),  # Single input, multiple outputs (fan-out)
        (10, 1, "consolidation"),  # Multiple inputs, single output (consolidation)
        (10, 10, "complex"),  # Multiple inputs, multiple outputs (complex)
    ],
)
def test_multi_io_transaction(
    rosetta_client, test_wallet, num_inputs: int, num_outputs: int, scenario_name: str
):
    """
    Test multi-input/output transactions with different scenarios:

    1. Consolidation: Multiple inputs, single output (consolidating UTXOs)
    2. Fan-out: Single input, multiple outputs (sending to multiple recipients)
    3. Complex: Multiple inputs, multiple outputs (combination of both)

    The test follows these steps:
    1. Select appropriate UTXOs based on the scenario
    2. Construct transaction with the specified number of inputs and outputs
    3. Sign and submit the transaction
    4. Validate the transaction on-chain
    """
    logger.info(
        "Starting %s transaction test with %d inputs and %d outputs",
        scenario_name,
        num_inputs,
        num_outputs,
    )

    # Constants for the test
    transfer_amount_per_output = 1_500_000  # 1.5 ADA per output
    estimated_fee = 180_000 + (
        50_000 * (num_inputs + num_outputs - 2)
    )  # Base fee + additional for each extra input/output

    # Calculate total amount needed for the transaction
    total_output_amount = transfer_amount_per_output * num_outputs
    total_required_amount = total_output_amount + estimated_fee

    # Step 1: Select UTXOs based on the scenario
    if num_inputs == 1:
        # For fan-out scenario, select a single UTXO with sufficient funds
        utxos = [
            test_wallet.select_ada_only_utxo(
                rosetta_client=rosetta_client, min_amount=total_required_amount
            )
        ]
        logger.debug("Selected single UTXO for fan-out scenario: %s", utxos[0])
    else:
        # For consolidation or complex scenarios, select multiple UTXOs
        utxos = test_wallet.select_multiple_ada_utxos(
            rosetta_client=rosetta_client,
            num_utxos=num_inputs,
            min_total_amount=total_required_amount,
        )
        logger.debug(
            "Selected %d UTXOs with total value: %d lovelace",
            len(utxos),
            sum(int(utxo["amount"]["value"]) for utxo in utxos),
        )

    # Step 2: Prepare inputs for the transaction
    inputs_data = []
    total_input_value = 0

    for utxo in utxos:
        input_value = int(utxo["amount"]["value"])
        total_input_value += input_value

        inputs_data.append(
            {
                "address": str(test_wallet.address),
                "value": input_value,
                "coin_identifier": utxo["coin_identifier"],
                "coin_change": {
                    "coin_identifier": utxo["coin_identifier"],
                    "coin_action": "coin_spent",
                },
            }
        )

    # Step 3: Prepare outputs for the transaction
    outputs = []
    remaining_value = total_input_value

    # Add transfer outputs (all but the last one, which will be change)
    for i in range(num_outputs - 1):
        outputs.append(
            {
                "address": str(
                    test_wallet.address
                ),  # Using same address for simplicity
                "value": transfer_amount_per_output,
            }
        )
        remaining_value -= transfer_amount_per_output

    # Add the final output (either a transfer or change)
    if num_outputs > 0:
        outputs.append(
            {
                "address": str(test_wallet.address),
                "value": remaining_value,  # All remaining funds (will be adjusted for fee)
            }
        )

    # Step 4: Construct the transaction
    constructed_tx = rosetta_client.construct_transaction(
        inputs=inputs_data, outputs=outputs
    )
    logger.debug("Constructed transaction: %s", constructed_tx)

    # Step 5: Sign the transaction
    # For multi-input transactions from the same wallet, only one signature is needed
    # since all inputs are controlled by the same key
    signature = test_wallet.sign_transaction(constructed_tx)
    logger.debug("Generated transaction signature")

    # Step 6: Combine the transaction with signature
    combined_tx = rosetta_client.combine_transaction(
        unsigned_transaction=constructed_tx["unsigned_transaction"],
        signatures=[signature],
    )
    logger.debug("Combined transaction: %s", combined_tx)

    # Step 7: Submit the transaction
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
    actual_fee = total_input_value - sum(output_values)

    # Log transaction information
    logger.info(
        "Transaction submitted successfully - ID: %s (Scenario: %s, Inputs: %d, Outputs: %d, Fee: %d lovelace)",
        tx_id,
        scenario_name,
        num_inputs,
        num_outputs,
        actual_fee,
    )

    # Log detailed breakdown at DEBUG level
    logger.debug("Transaction details:")
    logger.debug("- Total input value: %d lovelace", total_input_value)
    logger.debug("- Total output value: %d lovelace", sum(output_values))
    logger.debug("- Fee: %d lovelace", actual_fee)

    # Verify transaction hash
    hash_resp = rosetta_client.get_transaction_hash(combined_tx["signed_transaction"])
    verified_hash = hash_resp["transaction_identifier"]["hash"]
    logger.debug("Transaction hash verified: %s", verified_hash)
    assert verified_hash == tx_id, "Transaction hash mismatch!"

    # Step 8: Wait for transaction to appear on-chain and validate it
    logger.info("Waiting for transaction to be included in a block...")

    # Define timeout and polling interval
    timeout_seconds = 180  # 3 minutes
    polling_interval = 5  # 5 seconds
    start_time = time.time()
    found_in_block = False
    current_block_identifier = None

    # Store original operations for later comparison
    original_operations = []

    # Input operations
    for input_data in inputs_data:
        original_operations.append(
            {
                "type": "input",
                "address": input_data["address"],
                "amount": -input_data["value"],
                "coin_identifier": input_data["coin_identifier"]["identifier"],
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

    # Step 9: Fetch and validate the on-chain transaction details
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
    assert (
        len(input_ops) == num_inputs
    ), f"Expected {num_inputs} input operations, got {len(input_ops)}"

    # Validate each input operation
    for i, input_op in enumerate(input_ops):
        assert input_op["account"]["address"] == str(
            test_wallet.address
        ), f"Input {i} address mismatch"
        assert (
            int(input_op["amount"]["value"]) < 0
        ), f"Input {i} amount should be negative"

    # Validate output operations
    assert (
        len(output_ops) == num_outputs
    ), f"Expected {num_outputs} output operations, got {len(output_ops)}"

    # Validate each output operation
    for i, output_op in enumerate(output_ops):
        assert output_op["account"]["address"] == str(
            test_wallet.address
        ), f"Output {i} address mismatch"
        assert (
            int(output_op["amount"]["value"]) > 0
        ), f"Output {i} amount should be positive"

    # Calculate and validate the actual on-chain fee
    onchain_input_value = sum(abs(int(op["amount"]["value"])) for op in input_ops)
    onchain_output_value = sum(int(op["amount"]["value"]) for op in output_ops)
    onchain_fee = onchain_input_value - onchain_output_value

    logger.info("On-chain fee: %d lovelace", onchain_fee)
    assert (
        onchain_fee == actual_fee
    ), f"Fee mismatch: expected {actual_fee}, got {onchain_fee}"

    # Final success message
    logger.info(
        "Multi-IO transaction (%s scenario with %d inputs, %d outputs) successfully validated on-chain!",
        scenario_name,
        num_inputs,
        num_outputs,
    )
