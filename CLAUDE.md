# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **delta-neutral funding rate farming strategy application** for the Aster DEX. The project implements a terminal-based Python application that helps users manage arbitrage opportunities between Aster's perpetual and spot markets.

**Core Philosophy:**
- **Security First**: Never handles raw private keys for fund transfers - only instructs users to transfer manually
- **User Control**: Semi-automated tool requiring explicit user confirmation for all trade executions
- **Modular Architecture**: Strictly divided into three main components for isolated development and testing
- **No Emojis**: Never use Unicode emojis in code or output - use ASCII alternatives for Windows compatibility

## Development Commands

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Load environment variables (API credentials stored in .env)
# Required variables: API_USER, API_SIGNER, API_PRIVATE_KEY, APIV1_PUBLIC_KEY, APIV1_PRIVATE_KEY
```

### Testing
```bash
# Run API manager tests (Step 1)
python -m unittest test_api_manager -v

# Run strategy logic tests (Step 2)
python -m unittest test_strategy_logic -v

# Run all unit tests
python -m unittest test_api_manager test_strategy_logic -v

# Run integration tests (requires real API credentials)
python run_integration_tests.py

# Run verification scripts
python step1_verification.py
python step2_verification.py

# Run the complete application
python delta_neutral_bot.py

# CLI Commands (without starting the dashboard)
python delta_neutral_bot.py --pairs           # Check available delta-neutral pairs
python delta_neutral_bot.py --funding-rates   # Check current funding rates for all pairs with effective APR
python delta_neutral_bot.py --positions       # Show current delta-neutral positions and portfolio
python delta_neutral_bot.py --spot-assets     # Show current spot asset balances with USD values
python delta_neutral_bot.py --perpetual       # Show perpetual positions with detailed PnL analysis (USD + %)
python delta_neutral_bot.py --test            # Run dashboard in test mode (fetch once, exit)
python delta_neutral_bot.py --help            # Show all available options

# Run with Docker
docker-compose build
docker-compose run --rm dn_bot
```

### Code Validation
```bash
# Check Python compilation
python -m py_compile aster_api_manager.py
python -m py_compile strategy_logic.py
python -m py_compile test_api_manager.py
python -m py_compile test_strategy_logic.py

# Test module imports
python -c "import aster_api_manager; print('API manager import successful!')"
python -c "import strategy_logic; print('Strategy logic import successful!')"
```

## Architecture Overview

### Six-Module Architecture (Refactored from Three-Tier Design)

#### Core Modules

1. **`aster_api_manager.py`** - The Exchange Gateway (931 lines, 17 methods)
   - Unified API manager for both Aster Perpetual and Spot markets
   - Handles dual authentication: Ethereum signatures (perps) + HMAC-SHA256 (spot)
   - Lazy session management with proper async cleanup
   - All read/write operations for market data and order execution
   - Leverage management: checking and setting leverage (default 1x for delta-neutral)
   - Position analysis: `perform_funding_analysis()` and `perform_health_check_analysis()`
   - Detects delta-neutral setups with 2% imbalance threshold

2. **`strategy_logic.py`** - The Brain (518 lines)
   - Pure computational logic for delta-neutral strategy
   - Stateless functions for opportunity analysis and position sizing
   - Risk management and health monitoring calculations
   - Dynamic pair discovery and liquidity filtering
   - Comprehensive rebalancing and validation logic

3. **`delta_neutral_bot.py`** - The UI & Orchestrator (1,004 lines)
   - Terminal-based dashboard with real-time updates and colorized output
   - User interaction and confirmation workflows with keyboard controls
   - Integration of API manager and strategy logic
   - Cross-platform compatibility (Windows/Linux/Mac)
   - Comprehensive error handling and session management
   - Main application loop and interactive workflows

#### Supporting Modules

4. **`ui_renderers.py`** - UI Rendering Functions (319 lines)
   - Pure rendering functions for terminal output
   - Ensures consistent formatting across CLI and dashboard
   - **Functions:**
     - `render_funding_rates_table()` - Funding rates with APR calculations
     - `render_perpetual_positions_table()` - Perpetual positions with PnL
     - `render_portfolio_summary()` - Account balance summary
     - `render_delta_neutral_positions()` - Delta-neutral position details
     - `render_spot_balances()` - Spot asset balances
     - `render_other_positions()` - Non-delta-neutral holdings
     - `render_opportunities()` - Available trading opportunities
     - `render_funding_analysis_results()` - Funding payment analysis

5. **`cli_commands.py`** - CLI Command Functions (497 lines)
   - Standalone command-line interface for non-interactive operation
   - Direct access to all bot features via command arguments
   - **Functions:**
     - `check_available_pairs()` - List delta-neutral pairs
     - `check_current_positions()` - Show portfolio summary
     - `check_spot_assets()` - Display spot balances
     - `check_perpetual_positions()` - Show perpetual positions
     - `check_funding_rates()` - List current funding rates
     - `check_portfolio_health()` - Perform health check
     - `rebalance_usdt_cli()` - Rebalance USDT between accounts
     - `open_position_cli()` - Open delta-neutral position
     - `close_position_cli()` - Close delta-neutral position
     - `analyze_fundings_cli()` - Analyze funding payments

6. **`utils.py`** - Shared Utilities (30 lines)
   - Common utility functions used across multiple modules
   - **Functions:**
     - `truncate()` - Precision-aware number truncation for exchange compliance

#### Architecture Benefits

- **Modularity**: Each module has a single, well-defined responsibility
- **Reduced Size**: Main orchestrator reduced from 1,964 to 1,004 lines (49% reduction)
- **Zero Duplication**: Shared functions eliminate code repetition
- **Reusability**: UI renderers and CLI commands can be imported anywhere
- **Testability**: Pure functions and clear boundaries enable comprehensive testing
- **Maintainability**: Changes in one area don't cascade to unrelated code
- **DRY Principle**: Single source of truth for rendering and utilities
- **Clean Imports**: Clear dependency graph prevents circular dependencies

### Key Dependencies and Authentication

**API Authentication:**
- **Perpetuals API**: Uses Ethereum-style signatures via `ASTER_codes/api_client.py`
  - Requires: `API_USER` (Ethereum address), `API_SIGNER` (Ethereum address), `API_PRIVATE_KEY`
  - Base URL: `https://fapi.asterdex.com`
- **Spot API**: Uses HMAC-SHA256 signatures
  - Requires: `APIV1_PUBLIC_KEY`, `APIV1_PRIVATE_KEY`
  - Base URL: `https://sapi.asterdex.com`

**Critical Implementation Details:**
- `aiohttp.ClientSession` created lazily to avoid event loop issues
- Sessions must be properly closed with `await manager.close()`
- All API methods are async and require proper error handling

### Legacy Code Structure

The `ASTER_codes/` directory contains legacy example code and utilities:
- `api_client.py` - Low-level perpetuals API client (used by `aster_api_manager.py`)
- Various example scripts for testing individual API endpoints
- Terminal dashboard prototypes and WebSocket implementations

### Testing Strategy

**Unit Tests**:
- `test_api_manager.py`: Mock all HTTP requests, test authentication, validate request formatting
- `test_strategy_logic.py`: Test all computational logic with mocked data, validate edge cases
- No real API calls required for unit tests

**Integration Tests**:
- Require real API credentials from `.env` file
- Test live API endpoints with actual market data
- Include controlled order lifecycle testing (with user confirmation)
- Automatically skip when credentials unavailable

**Verification Scripts**:
- `step1_verification.py`: Comprehensive validation of API manager requirements
- `step2_verification.py`: Comprehensive validation of strategy logic requirements

## Environment Configuration

Store API credentials in `.env` file at project root:
```
API_USER=0x...
API_SIGNER=0x...
API_PRIVATE_KEY=0x...
APIV1_PUBLIC_KEY=...
APIV1_PRIVATE_KEY=...
```

Load using `python-dotenv` before running integration tests.

## Strategy Logic Implementation (Step 2)

### Core Methods Implemented

**Opportunity Analysis:**
- `analyze_funding_opportunities()`: Identifies profitable funding rate opportunities
- `filter_viable_pairs()`: Filters pairs by liquidity requirements
- `find_delta_neutral_pairs()`: Discovers pairs available in both spot and perpetual markets

**Position Management:**
- `calculate_position_size()`: Determines optimal position sizes for delta-neutral strategies
- `check_position_health()`: Monitors liquidation risk, imbalance, and PnL
- `determine_rebalance_action()`: Decides when to rebalance, hold, or close positions
- `calculate_rebalance_quantities()`: Calculates specific rebalancing amounts

**Risk Management:**
- `validate_strategy_preconditions()`: Validates sufficient account balances and 1x leverage requirement
- Built-in risk thresholds and safety parameters
- Leverage-aware liquidation risk calculations
- Comprehensive edge case handling

### Strategy Constants (Tunable)
- `ANNUALIZED_APR_THRESHOLD = 15.0%`: Minimum APR to consider opportunities
- `MAX_VOLATILITY_THRESHOLD = 0.05`: Maximum coefficient of variation for stability
- `IMBALANCE_THRESHOLD_PCT = 5.0%`: Maximum allowed position imbalance
- `HIGH_RISK_LIQUIDATION_PCT = 2.0%`: Liquidation risk threshold

### Available Trading Pairs
Current delta-neutral pairs on Aster DEX:
- `BTCUSDT`: Bitcoin (high liquidity)
- `ETHUSDT`: Ethereum (high liquidity)
- `ASTERUSDT`: Native token (medium liquidity)
- `USD1USDT`: Stablecoin (lower liquidity)

## Development Status

- [DONE] **Step 1 Complete**: `aster_api_manager.py` (931 lines) - unified API manager with analysis methods
- [DONE] **Step 2 Complete**: `strategy_logic.py` (518 lines) - pure computational strategy logic
- [DONE] **Step 3 Complete**: `delta_neutral_bot.py` (1,004 lines) - orchestration and interactive workflows
- [DONE] **Refactoring Complete**: Modular architecture with 3 supporting modules (ui_renderers.py, cli_commands.py, utils.py)

### Additional Components
- [READY] **Docker Support**: `Dockerfile` and `docker-compose.yml` for containerized deployment
- [READY] **Documentation**: Complete `README.md` with setup and usage instructions
- [ENHANCED] **Test Suite**: 45+ comprehensive unit tests with CLI functionality coverage

### Key Features Implemented

**Complete Terminal Application:**
- **Dashboard**: Real-time portfolio display with colorized output using colorama
- **User Controls**: Interactive keyboard commands (refresh, scan, execute, quit)
- **CLI Commands**: Direct command-line access for pair discovery, funding rate analysis with effective APR, position monitoring, spot asset management, and perpetual trading analysis with percentage PnL
- **Cross-Platform**: Windows/Linux/Mac compatibility with platform-specific input handling
- **Error Handling**: Comprehensive exception handling and graceful degradation
- **Session Management**: Proper async lifecycle management for API connections

**Position Analysis & Risk Management:**
- **Real-time Detection**: `analyze_current_positions()` method for delta-neutral position tracking
- **Risk Monitoring**: Liquidation risk, imbalance detection, and position health analysis
- **Leverage Management**: Automatic 1x leverage validation and enforcement
- **Opportunity Scanning**: Dynamic funding rate analysis and pair discovery

**Production-Ready Features:**
- **Docker Support**: Complete containerization with multi-stage builds
- **Environment Configuration**: Secure credential management via `.env` files
- **Comprehensive Testing**: 45+ unit tests covering core functionality and CLI commands
- **Documentation**: Complete setup and usage guides in README.md

### Refactoring Summary (Latest Enhancement)

**Code Organization:**
- **Main Module Reduction**: Reduced `delta_neutral_bot.py` from 1,964 to 1,004 lines (49% reduction)
- **New Supporting Modules**: Created 3 focused modules for shared functionality
  - `ui_renderers.py` (319 lines) - 8 rendering functions
  - `cli_commands.py` (497 lines) - 10 CLI command functions
  - `utils.py` (30 lines) - Shared utilities
- **Analysis Methods**: Moved `perform_funding_analysis()` and `perform_health_check_analysis()` to `aster_api_manager.py`
- **Zero Duplication**: Eliminated all duplicate code (e.g., `_truncate()` function)

**Architecture Improvements:**
- **Separation of Concerns**: Each module has a single, well-defined responsibility
- **DRY Principle**: Single source of truth for rendering, CLI commands, and utilities
- **Reusability**: Rendering and CLI functions can be imported anywhere
- **Testability**: Pure functions with clear boundaries enable comprehensive testing
- **Maintainability**: Changes isolated to specific modules without cascading effects
- **Clean Dependencies**: No circular imports, clear dependency graph

**Enhanced Features:**
- **Effective APR**: Shows APR/2 for 1x leverage delta-neutral strategies
- **Percentage PnL**: Real-time percentage calculations for perpetual positions
- **Consistent Formatting**: Identical table rendering across CLI and dashboard
- **Cross-Platform**: Enhanced Windows compatibility with ASCII-only output
- **Error Handling**: Improved API error suppression during price discovery

Refer to `mega_plan.md` for detailed implementation specifications and `README.md` for usage instructions.