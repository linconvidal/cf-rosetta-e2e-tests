# Cardano Rosetta E2E Tests

Simple end-to-end testing framework for Cardano's Rosetta API implementation.

## Features

- Basic ADA transfers
- UTXO management
- Transaction construction and signing
- Multi-input/output transactions
- Stake key registration and delegation
- Testnet/mainnet support

## Setup

### Prerequisites

- Python 3.8+
- Poetry (recommended) or pip
- Cardano Rosetta API endpoint
- Test wallet with funds

### Quick Start

```bash
# Using Poetry (recommended)
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
STAKE_POOL_ID=d9812f8d30b5db4b03e5b76cfd242db9cd2763da4671ed062be808a0 # Required for stake delegation tests
```

## Usage

### Running Tests

```bash
# Run all tests
pytest

# Run specific test scenarios
pytest tests/test_multi_io_transactions.py -k basic
pytest tests/test_multi_io_transactions.py -k fan-out
pytest tests/test_multi_io_transactions.py -k consolidation
pytest tests/test_multi_io_transactions.py -k complex

# Run stake tests
pytest tests/test_stake_scenarios.py
```

## Project Structure

```
├── rosetta_client/      # Rosetta API client
├── wallet_utils/        # PyCardano wallet wrapper
├── tests/               # Test suites
└── pyproject.toml       # Project configuration
```

## Test Scenarios

### Transaction Tests

1. **Basic**: Single input → 2 outputs (transfer + change)
2. **Consolidation**: Multiple inputs → Single output
3. **Fan-out**: Single input → Multiple outputs
4. **Complex**: Multiple inputs → Multiple outputs

### Stake Operations

1. **Registration**: Register stake key
2. **Delegation**: Delegate to stake pool
3. **Deregistration**: Deregister stake key

## License

MIT License
