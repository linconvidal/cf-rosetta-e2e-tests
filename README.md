# Cardano Rosetta E2E Tests

Simple end-to-end testing framework for Cardano's Rosetta API implementation, currently focused on basic ADA transfers.

## Features

### Working Now

✅ Basic ADA transfers
✅ UTXO management
✅ Transaction construction and signing
✅ Testnet/mainnet support

### Coming Later

- Multi-asset transactions
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
```

### Project Structure

```
├── rosetta_client/      # Rosetta API client
├── wallet_utils/        # PyCardano wallet wrapper
├── tests/              # Test suites
└── pyproject.toml     # Project configuration
```

## Contributing

1. Fork repository
2. Create feature branch
3. Submit pull request

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

MIT License - see LICENSE file
