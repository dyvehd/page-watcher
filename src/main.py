import argparse
import asyncio
import logging
import sys
from src.config import load_config
from src.scheduler import WatcherScheduler

def setup_logging():
    """Configure basic console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Reduce verbose logging from third party libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

async def main():
    parser = argparse.ArgumentParser(description="Page Watcher Daemon")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the config.yaml configuration file"
    )
    parser.add_argument(
        "--db",
        default="watcher.db",
        help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run all due checks once and exit (no daemon loop)"
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Initializing Page Watcher Service...")

    try:
        config = load_config(args.config)
        logger.info(f"Loaded config from: {args.config}")
        logger.info(f"Configured groups: {list(config.groups.keys())}")
    except Exception as e:
        logger.critical(f"Failed to load configuration: {e}")
        sys.exit(1)

    scheduler = WatcherScheduler(config, db_path=args.db)

    if args.once:
        logger.info("Running page checks once...")
        await scheduler.run_once()
        logger.info("Page checks completed. Exiting.")
    else:
        # Run daemon loop
        await scheduler.start(poll_interval_seconds=15)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nService interrupted by user. Exiting.")
        sys.exit(0)
