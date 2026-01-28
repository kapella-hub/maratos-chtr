#!/usr/bin/env python3
"""Admin CLI commands for audit log maintenance.

Commands:
    purge_old_audit --days N    Delete records older than N days
    audit_stats                 Show table statistics
    audit_vacuum                Run VACUUM and ANALYZE on audit tables

Usage:
    python -m app.cli.audit_admin purge_old_audit --days 30
    python -m app.cli.audit_admin audit_stats
    python -m app.cli.audit_admin audit_vacuum
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime

# Add project root to path for imports
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.audit.retention import (
    RetentionConfig,
    TableRetentionPolicy,
    purge_old_records,
    purge_all_tables,
    get_table_stats,
)
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def cmd_purge_old_audit(args: argparse.Namespace) -> int:
    """Purge audit records older than specified days."""
    await init_db()

    if args.table:
        # Purge specific table
        logger.info(f"Purging records older than {args.days} days from {args.table}...")
        result = await purge_old_records(args.table, args.days)

        if result.error:
            logger.error(f"Error: {result.error}")
            return 1

        logger.info(f"Deleted {result.deleted_count} records from {result.table_name}")
        logger.info(f"Cutoff date: {result.cutoff_date.isoformat()}")
    else:
        # Purge all tables with custom retention
        config = RetentionConfig(
            policies={
                "audit_logs": TableRetentionPolicy("audit_logs", retention_days=args.days),
                "tool_audit_logs": TableRetentionPolicy("tool_audit_logs", retention_days=args.days),
                "llm_exchange_logs": TableRetentionPolicy("llm_exchange_logs", retention_days=args.days),
                "file_change_logs": TableRetentionPolicy("file_change_logs", retention_days=args.days),
                "budget_logs": TableRetentionPolicy("budget_logs", retention_days=args.days),
            }
        )

        logger.info(f"Purging all audit tables (records older than {args.days} days)...")
        result = await purge_all_tables(
            config,
            run_vacuum=not args.no_vacuum,
            run_analyze=not args.no_analyze,
        )

        print("\n" + "=" * 60)
        print("PURGE RESULTS")
        print("=" * 60)

        for table_result in result.results:
            status = "OK" if not table_result.error else f"ERROR: {table_result.error}"
            print(f"  {table_result.table_name:25} {table_result.deleted_count:8} deleted  [{status}]")

        print("-" * 60)
        print(f"  {'TOTAL':25} {result.total_deleted:8} deleted")
        print()
        print(f"  VACUUM:  {'completed' if result.vacuum_run else 'skipped'}")
        print(f"  ANALYZE: {'completed' if result.analyze_run else 'skipped'}")
        print("=" * 60)

    return 0


async def cmd_audit_stats(args: argparse.Namespace) -> int:
    """Show audit table statistics."""
    await init_db()

    logger.info("Fetching audit table statistics...")
    stats = await get_table_stats()

    print("\n" + "=" * 80)
    print("AUDIT TABLE STATISTICS")
    print("=" * 80)
    print(f"{'Table':<25} {'Count':>12} {'Oldest':>20} {'Newest':>20}")
    print("-" * 80)

    total_count = 0
    for table_name, table_stats in stats.items():
        if "error" in table_stats:
            print(f"  {table_name:<25} ERROR: {table_stats['error']}")
        else:
            count = table_stats.get("count", 0)
            total_count += count
            oldest = table_stats.get("oldest", "-")[:19] if table_stats.get("oldest") else "-"
            newest = table_stats.get("newest", "-")[:19] if table_stats.get("newest") else "-"
            print(f"  {table_name:<25} {count:>10} {oldest:>20} {newest:>20}")

    print("-" * 80)
    print(f"  {'TOTAL':<25} {total_count:>10}")
    print("=" * 80)

    return 0


async def cmd_audit_vacuum(args: argparse.Namespace) -> int:
    """Run VACUUM and ANALYZE on audit tables."""
    await init_db()

    from sqlalchemy import text
    from app.database import async_session_factory

    logger.info("Running database maintenance...")

    try:
        async with async_session_factory() as session:
            if not args.no_vacuum:
                logger.info("Running VACUUM...")
                await session.execute(text("VACUUM"))
                logger.info("VACUUM completed")

            if not args.no_analyze:
                logger.info("Running ANALYZE...")
                await session.execute(text("ANALYZE"))
                logger.info("ANALYZE completed")

            await session.commit()

        print("\nDatabase maintenance completed successfully.")
        return 0

    except Exception as e:
        logger.error(f"Maintenance failed: {e}")
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Audit log administration commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # purge_old_audit command
    purge_parser = subparsers.add_parser(
        "purge_old_audit",
        help="Delete audit records older than N days",
    )
    purge_parser.add_argument(
        "--days",
        type=int,
        required=True,
        help="Delete records older than this many days",
    )
    purge_parser.add_argument(
        "--table",
        type=str,
        choices=[
            "audit_logs",
            "tool_audit_logs",
            "llm_exchange_logs",
            "file_change_logs",
            "budget_logs",
        ],
        help="Specific table to purge (default: all tables)",
    )
    purge_parser.add_argument(
        "--no-vacuum",
        action="store_true",
        help="Skip VACUUM after purge",
    )
    purge_parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Skip ANALYZE after purge",
    )

    # audit_stats command
    stats_parser = subparsers.add_parser(
        "audit_stats",
        help="Show audit table statistics",
    )

    # audit_vacuum command
    vacuum_parser = subparsers.add_parser(
        "audit_vacuum",
        help="Run VACUUM and ANALYZE on database",
    )
    vacuum_parser.add_argument(
        "--no-vacuum",
        action="store_true",
        help="Skip VACUUM",
    )
    vacuum_parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Skip ANALYZE",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Run the appropriate command
    if args.command == "purge_old_audit":
        return asyncio.run(cmd_purge_old_audit(args))
    elif args.command == "audit_stats":
        return asyncio.run(cmd_audit_stats(args))
    elif args.command == "audit_vacuum":
        return asyncio.run(cmd_audit_vacuum(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
