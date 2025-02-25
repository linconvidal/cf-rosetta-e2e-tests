import os
from dotenv import load_dotenv
import pytest
import logging
import time
import _pytest.terminal

from rosetta_client.client import RosettaClient
from wallet_utils.pycardano_wallet import PyCardanoWallet

# Load environment variables from .env file
load_dotenv()


# ANSI color/style constants with minimalist design principles
class Style:
    # Colors - using a more restrained palette
    BLUE = "\033[38;5;68m"  # Softer blue
    GREEN = "\033[38;5;71m"  # Muted green
    YELLOW = "\033[38;5;179m"  # Softer yellow
    RED = "\033[38;5;167m"  # Muted red
    GRAY = "\033[38;5;246m"  # Medium gray
    CYAN = "\033[38;5;109m"  # Muted cyan

    # Styles
    BOLD = "\033[1m"
    RESET = "\033[0m"

    # Icons - minimal and functional
    DEBUG_ICON = "•"
    INFO_ICON = "→"
    WARNING_ICON = "!"
    ERROR_ICON = "×"
    CRITICAL_ICON = "‼"
    HTTP_ICON = "⤷"


# Logging level configuration with colors and icons
LOG_LEVELS = {
    "DEBUG": (Style.GRAY, Style.DEBUG_ICON),
    "INFO": (Style.BLUE, Style.INFO_ICON),
    "WARNING": (Style.YELLOW, Style.WARNING_ICON),
    "ERROR": (Style.RED, Style.ERROR_ICON),
    "CRITICAL": (Style.RED + Style.BOLD, Style.CRITICAL_ICON),
}


class SwissDesignFormatter(logging.Formatter):
    """Custom log formatter with minimalist design principles"""

    def formatTime(self, record, datefmt=None):
        """Format timestamp with gray styling"""
        asctime = super().formatTime(record, datefmt)
        return f"{Style.GRAY}{asctime}{Style.RESET}"

    def format(self, record):
        # Simplify logger name
        original_name = record.name
        if "." in original_name:
            record.name = original_name.split(".")[0]

        # Format level name with appropriate design principles
        if record.levelname in LOG_LEVELS:
            color, icon = LOG_LEVELS[record.levelname]
            # Right-aligned level indicators with consistent width
            record.levelname = f"{color}{icon}{Style.RESET}"

        # Format names with consistent width for grid alignment
        record.name = f"{Style.GRAY}{record.name:<10}{Style.RESET}"

        # Special formatting for HTTP-related logs
        if hasattr(record, "msg") and isinstance(record.msg, str):
            msg = record.msg

            # Format HTTP request/response logs with style
            if "[REQUEST " in msg:
                # Balance spacing perfectly with a light touch
                record.msg = f"{Style.CYAN}{Style.HTTP_ICON} {Style.RESET} {msg}"
            elif "[RESPONSE " in msg:
                if "Status: 2" in msg or "Status: 3" in msg:
                    # Success response - subtle but clear indicator
                    record.msg = f"{Style.GREEN}{Style.HTTP_ICON} {Style.RESET} {msg}"
                else:
                    # Error response - visually distinct but not overwhelming
                    record.msg = f"{Style.RED}{Style.HTTP_ICON} {Style.RESET} {msg}"
            elif "[ERROR " in msg:
                record.msg = f"{Style.RED}{Style.HTTP_ICON} {Style.RESET} {msg}"

        # Emphasizes precision and breathing space
        formatted = super().format(record)

        # Grid-like structure for errors and warnings
        if record.levelno >= logging.WARNING:
            # Add structured spacing before warnings/errors - precisely 80 characters
            separator = f"\n{Style.GRAY}{'─' * 80}{Style.RESET}\n"
            formatted = f"{separator}{formatted}"

            # Add clear spacing after for visual breathing room
            formatted = f"{formatted}\n"

        return formatted


# ------------- PYTEST HOOKS -------------
# These hooks implement a custom reporting system that:
# 1. Suppresses pytest's built-in markers (F, s, ., etc.)
# 2. Disables the built-in summary output
# 3. Provides a clean, accurate summary at the end of test execution
# 4. Uses minimalist design principles for clarity and consistency


# Core status reporting hook - completely eliminates 'F' and 's' markers
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Completely disable the default status reporting in the terminal"""
    # Run the original hook
    yield

    # We've already run the test, but we don't want pytest to print
    # any status markers like 'F' or 's' after our output


# This is the most important hook to suppress the F and s markers
@pytest.hookimpl(tryfirst=True)
def pytest_report_teststatus(report, config):
    """
    Disable default status markers (F, s, etc.) completely by returning
    an empty string for the shortletter.
    """
    # By returning a completely empty string as the "shortletter" (second value),
    # we prevent pytest from printing any status marker at all
    return report.outcome, "", report.outcome


# Store collected tests for accurate reporting
collected_tests = {"items": [], "nodeids": []}

# Track session start time for accurate duration reporting
session_start_time = None


# Direct approach to disable the summary
@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session):
    """Session startup hook - directly modify the session object early"""
    global session_start_time
    # Start timing the session
    session_start_time = time.time()

    # Get the terminal reporter directly from the session
    if hasattr(session, "config") and hasattr(session.config, "pluginmanager"):
        terminal = session.config.pluginmanager.getplugin("terminalreporter")
        if terminal:
            # Create a do-nothing summary function
            def disabled_summary(*args, **kwargs):
                return None

            # Replace reporter's methods
            terminal.summary_stats = disabled_summary

            # Try to find any other summary methods
            for attr_name in dir(terminal):
                if attr_name.startswith("summary_") and callable(
                    getattr(terminal, attr_name)
                ):
                    setattr(terminal, attr_name, disabled_summary)


# Add a hook to store all collected tests
@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):
    """
    This hook runs after test collection.
    We'll store all collected tests here.
    """
    # Store the test items for later use
    collected_tests["items"] = items
    collected_tests["nodeids"] = [item.nodeid for item in items]


# Use a direct approach to block terminal reporter's summary generation
@pytest.hookimpl(hookwrapper=True)
def pytest_unconfigure(config):
    """
    Final hook that runs at the very end of pytest execution.
    Use this to print our summary as the very last thing and BLOCK the default summary.
    """
    # Get the terminal reporter
    terminal = config.pluginmanager.getplugin("terminalreporter")
    if terminal:
        # Get all test outcomes before the terminalreporter can use them
        reports = {}
        for outcome in ["failed", "passed", "skipped"]:
            if outcome in terminal.stats:
                reports[outcome] = list(terminal.stats[outcome])

        # Clear the terminal reporter's stats to prevent it from generating a summary
        terminal.stats.clear()

        # Create empty methods for summary reporting
        terminal.summary_stats = lambda: None
        terminal.summary_errors = lambda: None
        terminal.summary_failures = lambda: None
        terminal.summary_warnings = lambda: None

        # Let other hooks run
        yield

        # Get all unique test nodeids for proper counting
        all_nodeids = set()
        for outcome, reports_list in reports.items():
            for report in reports_list:
                all_nodeids.add(report.nodeid)

        # Count tests correctly - failed tests are in the call phase
        failed_nodeids = set(
            r.nodeid for r in reports.get("failed", []) if r.when == "call"
        )

        # Skipped tests are usually not in call phase, often in setup
        # Get all skipped test nodeids
        skipped_nodeids = set(r.nodeid for r in reports.get("skipped", []))

        # A test is counted as passed if it has a passed call phase and is not failed/skipped
        passed_nodeids = set()
        for r in reports.get("passed", []):
            if (
                r.when == "call"
                and r.nodeid not in failed_nodeids
                and r.nodeid not in skipped_nodeids
            ):
                passed_nodeids.add(r.nodeid)

        # Calculate final counts
        failed = len(failed_nodeids)
        passed = len(passed_nodeids)
        skipped = len(skipped_nodeids)

        # For total tests, use all unique nodeids we've collected if available
        total_tests = len(all_nodeids) if all_nodeids else 0

        # If no unique nodeids collected, fall back to collected_tests global
        if total_tests == 0 and collected_tests["items"]:
            total_tests = len(collected_tests["items"])

        # Calculate session duration from our own timer
        duration = 0
        if session_start_time is not None:
            duration = time.time() - session_start_time
        # Fall back to pytest's duration if available
        elif hasattr(config, "_session") and hasattr(config._session, "duration"):
            duration = config._session.duration

        # Print our custom summary at the very end
        print("\n" + "=" * 80)
        print(
            f"{Style.GRAY}SUMMARY {Style.RESET}{Style.BOLD}{duration:.2f}s{Style.RESET}  "
            f"{Style.RED}●{Style.RESET} {failed} failed  "
            f"{Style.GREEN}●{Style.RESET} {passed} passed  "
            f"{Style.YELLOW}●{Style.RESET} {skipped} skipped  "
            f"{Style.BLUE}●{Style.RESET} {total_tests} total"
        )
        print("=" * 80)
    else:
        # No terminal reporter found, just let other hooks run
        yield


# Add a simple hook for test section clarity
@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item):
    """Add a clean separator before each test."""
    # Always print a clear separator and the full test name
    print(f"\n{Style.GRAY}{'═' * 80}{Style.RESET}")
    print(f"{Style.BOLD}{item.nodeid}{Style.RESET}\n")


# Handle test result reporting with our custom styling
@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report):
    """Display result at the end of each test with minimalist design principles."""
    if report.when == "call" or (report.when == "setup" and report.skipped):
        if report.passed:
            print(f"\n{Style.GREEN}✓ {Style.BOLD}PASSED{Style.RESET}")

            # Add request metrics if available
            if hasattr(report, "node") and hasattr(report.node, "funcargs"):
                if "rosetta_client" in report.node.funcargs:
                    client = report.node.funcargs["rosetta_client"]
                    if hasattr(client, "request_debugger"):
                        # Use the new summary report method
                        client.request_debugger.print_summary_report()

        elif report.failed:
            print(f"\n{Style.RED}× {Style.BOLD}FAILED{Style.RESET}")

            # Add request metrics if available
            if hasattr(report, "node") and hasattr(report.node, "funcargs"):
                if "rosetta_client" in report.node.funcargs:
                    client = report.node.funcargs["rosetta_client"]
                    if hasattr(client, "request_debugger"):
                        # Use the new summary report method
                        client.request_debugger.print_summary_report()

            # Add detailed failure information
            if hasattr(report, "longrepr") and report.longrepr:
                # Get the failure message
                if isinstance(report.longrepr, tuple) and len(report.longrepr) >= 3:
                    _, _, error_msg = report.longrepr
                    lines = str(error_msg).strip().split("\n")

                    # Display a cleanly formatted error message
                    print(f"{Style.RED}Error details:{Style.RESET}")
                    for line in lines[:10]:  # Limit to first 10 lines
                        print(f"{Style.GRAY}  {line.strip()}{Style.RESET}")

                    if len(lines) > 10:
                        print(
                            f"{Style.GRAY}  ... ({len(lines) - 10} more lines){Style.RESET}"
                        )
                elif isinstance(report.longrepr, str):
                    print(
                        f"{Style.RED}Error: {Style.GRAY}{report.longrepr}{Style.RESET}"
                    )
        elif report.skipped:
            # Extract the reason in a cleaner way
            reason = ""
            if hasattr(report, "longrepr"):
                if isinstance(report.longrepr, tuple) and len(report.longrepr) >= 3:
                    reason = report.longrepr[2]
                elif isinstance(report.longrepr, str):
                    reason = report.longrepr
                # Clean up the format
                if "Skipped:" in reason:
                    reason = reason.split("Skipped:")[1].strip().strip("'")
            print(
                f"\n{Style.YELLOW}○ {Style.BOLD}SKIPPED{Style.RESET} {Style.GRAY}{reason}{Style.RESET}"
            )


def pytest_configure(config):
    """Configure logging for tests with minimalist design principles"""
    # Basic settings to disable built-in reports
    config.option.verbose = 0
    config.option.no_summary = True
    config.option.no_header = True
    config.option.no_progressbar = True

    # Simplify terminal reporter handling
    terminal = config.pluginmanager.getplugin("terminalreporter")
    if terminal:
        # Disable the path info in reports
        terminal.showfspath = False

        # Override the test status reporting method
        def custom_write_fspath_result(nodeid, res, **kwargs):
            # Suppress the output
            pass

        terminal.write_fspath_result = custom_write_fspath_result.__get__(terminal)

    # Configure root logger with minimalist formatter
    handler = logging.StreamHandler()
    formatter = SwissDesignFormatter(
        fmt="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.DEBUG)

    # Silence noisy libraries
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("pycardano").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("pytest").setLevel(logging.ERROR)

    # Configure rosetta client logging
    client_logger = logging.getLogger("rosetta_client")
    client_logger.setLevel(logging.DEBUG)

    # Configure HTTP request logging specifically - set to INFO by default
    http_logger = logging.getLogger("rosetta_client.http")
    http_logger.setLevel(logging.INFO)  # Use INFO by default for cleaner output

    # Create a logger for our tests with a more concise name
    test_logger = logging.getLogger("test")
    test_logger.setLevel(logging.DEBUG)


@pytest.fixture(scope="session")
def rosetta_client():
    endpoint = os.environ.get("ROSETTA_ENDPOINT", "https://testnet.rosetta-api.io")
    network = os.environ.get("CARDANO_NETWORK", "testnet")
    return RosettaClient(endpoint=endpoint, network=network)


@pytest.fixture(scope="session")
def test_wallet():
    mnemonic = os.environ.get("TEST_WALLET_MNEMONIC", "palavras de teste...")
    return PyCardanoWallet.from_mnemonic(mnemonic, network="testnet")


# Force disable pytest's built-in summary with a more direct approach
_pytest.terminal.TerminalReporter.summary_stats = lambda self: None


# Add a hook that runs when pytest finds plugins to ensure our override is effective
@pytest.hookimpl(trylast=True)
def pytest_plugin_registered(plugin, manager):
    """
    This hook is called after a plugin is registered.
    We'll use it to ensure our override of the summary methods is maintained.
    """
    if isinstance(plugin, _pytest.terminal.TerminalReporter):
        # Ensure the plugin's summary methods are all disabled
        plugin.summary_stats = lambda: None
        plugin.summary_failures = lambda: None
        plugin.summary_warnings = lambda: None
        plugin.summary_deselected = lambda: None
        if hasattr(plugin, "print_summary"):
            plugin.print_summary = lambda: None
