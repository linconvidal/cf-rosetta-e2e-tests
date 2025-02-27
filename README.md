# Cardano Rosetta E2E Tests

Simple end-to-end testing framework for Cardano's Rosetta API implementation, currently focused on basic ADA transfers.

## Features

### Working Now

- ✅ Basic ADA transfers
- ✅ UTXO management
- ✅ Transaction construction and signing
- ✅ Testnet/mainnet support
- ✅ Multi-input/output transactions

### Coming Later

- Native asset transactions
- Stake delegation
- Governance operations
- Native token operations

## Setup

### Prerequisites

- Python 3.8+
- Poetry (recommended) or pip
- Cardano Rosetta API endpoint
- Test wallet with funds

### Quick Start

```bash
# Using Poetry (recommended)
curl -sSL https://install.python-poetry.org | python3 -
poetry install

# Using pip
pip install -r requirements.txt
```

### Configuration

Create `.env` file:

```env
ROSETTA_ENDPOINT=http://localhost:8082
CARDANO_NETWORK=preview
TEST_WALLET_MNEMONIC=your mnemonic here
```

> ⚠️ Use testnet for testing. Never commit mnemonics. Use test wallets with minimal funds.

## Usage

### Running Tests

```bash
pytest                                              # All tests
pytest --log-cli-level=DEBUG                       # With debug logs
pytest tests/test_basic_transactions.py -k test_send_ada  # Specific test
pytest tests/test_multi_io_transactions.py         # Multi-input/output tests
```

### Project Structure

```
├── rosetta_client/      # Rosetta API client
├── wallet_utils/        # PyCardano wallet wrapper
├── tests/              # Test suites
│   ├── test_basic_transactions.py    # Basic ADA transfers
│   └── test_multi_io_transactions.py # Multi-input/output transactions
└── pyproject.toml     # Project configuration
```

## Contributing

1. Fork repository
2. Create feature branch
3. Submit pull request

## Test Scenarios

### Basic Transactions

The basic transaction tests verify the fundamental functionality of the Rosetta API:

- Selecting a UTXO
- Constructing a transaction with 1 input and 2 outputs (destination + change)
- Signing and submitting the transaction
- Validating the transaction on-chain

### Multi-Input/Output Transactions

The multi-input/output tests verify more complex transaction scenarios:

1. **Consolidation** (Multiple inputs → Single output)

   - Combines multiple UTXOs into a single output
   - Useful for reducing UTXO fragmentation
   - Tests proper handling of multiple inputs with a single signature

2. **Fan-out** (Single input → Multiple outputs)

   - Splits a single UTXO into multiple outputs
   - Useful for distributing funds to multiple recipients
   - Tests proper handling of multiple outputs

3. **Complex** (Multiple inputs → Multiple outputs)
   - Combines multiple UTXOs and creates multiple outputs
   - Tests the most complex transaction scenario
   - Validates proper fee calculation and change handling

All scenarios follow the complete Rosetta transaction flow:

1. UTXO selection

   - `/account/coins` - Retrieve available UTXOs for the address

2. Transaction construction

   - `/construction/preprocess` - Prepare options for metadata
   - `/construction/metadata` - Fetch network-specific metadata (TTL, parameters)
   - `/construction/payloads` - Generate unsigned transaction and signing payloads

3. Signing

   - Client-side signing with PyCardano
   - `/construction/combine` - Combine unsigned transaction with signatures

4. Submission

   - `/construction/hash` - Get transaction hash for tracking
   - `/construction/submit` - Submit signed transaction to the network

5. On-chain validation
   - `/network/status` - Get current block information
   - `/block` - Retrieve block data to verify transaction inclusion
   - `/block/transaction` - Verify transaction details on-chain

## Resources

### Documentation

- [Mesh API Specification](https://docs.cdp.coinbase.com/mesh/docs/api-reference/)
- [PyCardano Documentation](https://pycardano.readthedocs.io/en/latest/)
- [Cardano Developer Portal](https://developers.cardano.org/)

### Related Projects

- [Cardano Rosetta Java](https://github.com/cardano-foundation/cardano-rosetta-java)
- [PyCardano](https://github.com/Python-Cardano/pycardano)
- [Mesh Specifications](https://github.com/coinbase/mesh-specifications)
- [Yaci-Store](https://github.com/bloxbean/yaci-store)

## License

MIT License - see https://opensource.org/licenses/MIT
