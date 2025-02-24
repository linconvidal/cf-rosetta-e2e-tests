import os
from dotenv import load_dotenv
import pytest
import logging

from rosetta_client.client import RosettaClient
from wallet_utils.pycardano_wallet import PyCardanoWallet

# Load environment variables from .env file
load_dotenv()


def pytest_configure():
    """Configure logging for tests"""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s (%(threadName)s): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@pytest.fixture(scope="session")
def rosetta_client():
    endpoint = os.environ.get("ROSETTA_ENDPOINT", "https://testnet.rosetta-api.io")
    network = os.environ.get("CARDANO_NETWORK", "testnet")
    return RosettaClient(endpoint=endpoint, network=network)


@pytest.fixture(scope="session")
def test_wallet():
    mnemonic = os.environ.get("TEST_WALLET_MNEMONIC", "palavras de teste...")
    return PyCardanoWallet.from_mnemonic(mnemonic, network="testnet")
