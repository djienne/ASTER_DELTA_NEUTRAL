# GEMINI.md

## Project Overview

This project is a terminal-based Python application for managing a delta-neutral funding rate farming strategy on the Aster DEX. The application is designed to help users identify and manage arbitrage opportunities between Aster's perpetual and spot markets.

The project follows a modular six-module architecture:

### Core Modules

1.  **`aster_api_manager.py` (The Exchange Gateway - 931 lines):** A high-level, unified API manager for both Aster Perpetual and Spot markets. It uses the lower-level `ASTER_codes/api_client.py` for Ethereum-based authentication, data fetching, order execution, and position analysis.
2.  **`strategy_logic.py` (The Brain - 518 lines):** Contains the pure computational logic for the delta-neutral strategy, including opportunity analysis, position sizing, and risk management. This module is stateless and independent of the live API.
3.  **`delta_neutral_bot.py` (The UI & Orchestrator - 1,004 lines):** The main application that integrates the other modules, presents a terminal-based dashboard, and handles user interaction.

### Supporting Modules

4.  **`ui_renderers.py` (UI Rendering - 319 lines):** Pure rendering functions for consistent terminal output across both dashboard and CLI modes. Contains 8 specialized rendering functions.
5.  **`cli_commands.py` (CLI Commands - 497 lines):** Standalone command-line interface functions for non-interactive operation. Contains 10 CLI command functions.
6.  **`utils.py` (Shared Utilities - 30 lines):** Common utility functions used across multiple modules, including precision-aware truncation for exchange compliance.

The core philosophy of the project emphasizes security (never handling raw private keys for fund transfers), user control (requiring explicit confirmation for all trades), a robust modular architecture, and the DRY principle (zero code duplication).

## Building and Running

### Environment Setup

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    The main dependencies are `aiohttp` for asynchronous requests and `web3`/`eth-account` for handling the Ethereum-based authentication required by the Aster API.

2.  **Configure environment variables:**
    Create a `.env` file in the project root and add your API credentials:
    ```
    API_USER=0x...
    API_SIGNER=0x...
    API_PRIVATE_KEY=0x...
    APIV1_PUBLIC_KEY=...
    APIV1_PRIVATE_KEY=...
    ```

### Running the Application

The main application is now implemented in `delta_neutral_bot.py`. It can be run as an interactive dashboard or with one-off CLI commands for specific actions.

```bash
# Run the interactive dashboard (default)
python delta_neutral_bot.py

# Or use CLI commands for specific tasks (e.g., check positions)
python delta_neutral_bot.py --positions

# Open a position interactively
python delta_neutral_bot.py --open

# Open a $100 position in BTCUSDT non-interactively
python delta_neutral_bot.py --open BTCUSDT 100 --yes

# Close a position interactively
python delta_neutral_bot.py --close

# Close a BTCUSDT position non-interactively
python delta_neutral_bot.py --close BTCUSDT --yes
```

### Testing

The project has a comprehensive test suite covering the API manager, strategy logic, and CLI functionality.

*   **Run all unit tests:**
    ```bash
    python -m unittest discover -v
    ```

*   **Run integration tests (requires real API credentials):**
    ```bash
    python run_integration_tests.py
    ```

## Development Conventions

*   **Code Style:** The project follows PEP 8 standards and uses type hints extensively.
*   **Authentication:** The perpetuals API uses a custom Ethereum-based signature mechanism, implemented in `ASTER_codes/api_client.py`.
*   **Modularity:** The code is divided into six focused modules (3 core + 3 supporting) for isolated development, code reusability, and testing.
*   **DRY Principle:** Zero code duplication across the entire codebase through shared utility functions and rendering modules.
*   **Separation of Concerns:** Each module has a single, well-defined responsibility with clean interfaces.
*   **Stateless Logic:** The core strategy logic is implemented as pure, stateless functions for testability.
*   **Asynchronous:** The project uses `asyncio` and `aiohttp` for non-blocking network I/O.
*   **User Confirmation:** All actions that execute trades or modify the state of the user's account require explicit user confirmation.
*   **No Emojis:** The project avoids using Unicode emojis in code or output to ensure compatibility with Windows terminals.

## Architecture Benefits

*   **Modularity:** Each module has a single, well-defined responsibility
*   **Reduced Size:** Main orchestrator reduced from 1,964 to 1,004 lines (49% reduction)
*   **Zero Duplication:** Shared functions eliminate code repetition
*   **Reusability:** UI renderers and CLI commands can be imported anywhere
*   **Testability:** Pure functions and clear boundaries enable comprehensive testing
*   **Maintainability:** Changes in one area don't cascade to unrelated code
*   **Clean Dependencies:** No circular imports, clear dependency graph
