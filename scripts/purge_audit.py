#!/usr/bin/env python3
"""Audit log purge script for MaratOS.

Purges old audit log records based on retention policies. Designed for both
manual execution and cron automation.

Usage:
    # Purge records older than 90 days (default)
    python scripts/purge_audit.py

    # Purge records older than 30 days
    python scripts/purge_audit.py --days 30

    # Dry run (show what would be deleted)
    python scripts/purge_audit.py --dry-run

    # Cron mode (quiet, exit code only)
    python scripts/purge_audit.py --cron

    # Show stats only
    python scripts/purge_audit.py --stats

    # JSON output for automation
    python scripts/purge_audit.py --json

Crontab example (daily at 3am):
    0 3 * * * cd /path/to/maratos && python scripts/purge_audit.py --cron
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.audit.retention import (
    RetentionConfig,
    TableRetentionPolicy,
    purge_all_tables,
    get_table_stats,
    set_retention_config,
    FullCleanupResult,
)
from app.database import init_db


def setup_logging(verbose: bool = False, cron: bool = False) -> None:
    """Configure logging based on mode."""
    if cron:
        # Cron mode: only errors to stderr
        logging.basicConfig(
            level=logging.ERROR,
            format="%(message)s",
            stream=sys.stderr,
        )
    elif verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )


def print_stats(stats: dict, json_output: bool = False) -> None:
    """Print table statistics."""
    if json_output:
        print(json.dumps({"stats": stats}, indent=2))
        return

    print("\n" + "=" * 70)
    print("AUDIT TABLE STATISTICS")
    print("=" * 70)

    for table_name, table_stats in stats.items():
        if "error" in table_stats:
            print(f"\n{table_name}:")
            print(f"  Error: {table_stats['error']}")
            continue

        print(f"\n{table_name}:")
        print(f"  Records: {table_stats.get('count', 0):,}")
        if table_stats.get("oldest"):
            print(f"  Oldest:  {table_stats['oldest']}")
        if table_stats.get("newest"):
            print(f"  Newest:  {table_stats['newest']}")

    print("\n" + "=" * 70)


def print_purge_result(result: FullCleanupResult, json_output: bool = False) -> None:
    """Print purge results."""
    if json_output:
        output = {
            "total_deleted": result.total_deleted,
            "vacuum_run": result.vacuum_run,
            "analyze_run": result.analyze_run,
            "tables": [
                {
                    "name": r.table_name,
                    "deleted": r.deleted_count,
                    "cutoff": r.cutoff_date.isoformat(),
                    "error": r.error,
                }
                for r in result.results
            ],
        }
        print(json.dumps(output, indent=2))
        return

    print("\n" + "=" * 70)
    print("PURGE RESULTS")
    print("=" * 70)

    for table_result in result.results:
        status = "ERROR" if table_result.error else "OK"
        print(
            f"\n{table_result.table_name}:"
            f"\n  Status:  {status}"
            f"\n  Deleted: {table_result.deleted_count:,} records"
            f"\n  Cutoff:  {table_result.cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if table_result.error:
            print(f"  Error:   {table_result.error}")

    print(f"\n{'=' * 70}")
    print(f"TOTAL DELETED: {result.total_deleted:,} records")
    print(f"VACUUM:        {'Yes' if result.vacuum_run else 'No'}")
    print(f"ANALYZE:       {'Yes' if result.analyze_run else 'No'}")
    print("=" * 70 + "\n")


async def dry_run(days: int) -> dict:
    """Show what would be deleted without actually deleting."""
    from app.database import async_session_factory, AuditLog, ToolAuditLog
    from app.database import LLMExchangeLog, FileChangeLog, BudgetLog
    from sqlalchemy import select, func

    cutoff = datetime.utcnow() - timedelta(days=days)

    table_map = {
        "audit_logs": AuditLog,
        "tool_audit_logs": ToolAuditLog,
        "llm_exchange_logs": LLMExchangeLog,
        "file_change_logs": FileChangeLog,
        "budget_logs": BudgetLog,
    }

    results = {}
    total = 0

    async with async_session_factory() as session:
        for table_name, model in table_map.items():
            count_result = await session.execute(
                select(func.count(model.id)).where(model.created_at < cutoff)
            )
            count = count_result.scalar() or 0
            results[table_name] = count
            total += count

    return {"tables": results, "total": total, "cutoff": cutoff.isoformat()}


async def run_purge(
    days: int | None = None,
    dry_run_mode: bool = False,
    stats_only: bool = False,
    json_output: bool = False,
    cron: bool = False,
    no_vacuum: bool = False,
) -> int:
    """Run the purge operation.

    Returns:
        Exit code (0 = success, 1 = errors)
    """
    # Initialize database
    await init_db()

    # Stats only mode
    if stats_only:
        stats = await get_table_stats()
        print_stats(stats, json_output)
        return 0

    # Dry run mode
    if dry_run_mode:
        if days is None:
            days = 90  # Default

        result = await dry_run(days)

        if json_output:
            print(json.dumps({"dry_run": result}, indent=2))
        else:
            print("\n" + "=" * 70)
            print(f"DRY RUN - Records older than {days} days (before {result['cutoff']})")
            print("=" * 70)
            for table, count in result["tables"].items():
                print(f"  {table}: {count:,} records would be deleted")
            print(f"\n  TOTAL: {result['total']:,} records would be deleted")
            print("=" * 70 + "\n")
        return 0

    # Configure retention
    if days is not None:
        # Override all tables with same retention
        config = RetentionConfig(
            policies={
                "audit_logs": TableRetentionPolicy("audit_logs", days),
                "tool_audit_logs": TableRetentionPolicy("tool_audit_logs", days),
                "llm_exchange_logs": TableRetentionPolicy("llm_exchange_logs", days),
                "file_change_logs": TableRetentionPolicy("file_change_logs", days),
                "budget_logs": TableRetentionPolicy("budget_logs", days),
            },
            default_retention_days=days,
        )
        set_retention_config(config)

    # Run purge
    result = await purge_all_tables(
        run_vacuum=not no_vacuum,
        run_analyze=not no_vacuum,
    )

    # Check for errors
    has_errors = any(r.error for r in result.results)

    # Output results
    if not cron:
        print_purge_result(result, json_output)
    elif has_errors:
        # In cron mode, only print errors
        for r in result.results:
            if r.error:
                print(f"ERROR: {r.table_name}: {r.error}", file=sys.stderr)

    return 1 if has_errors else 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Purge old audit log records from MaratOS database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--days", "-d",
        type=int,
        help="Days of retention (delete records older than this). "
             "Defaults to configured retention per table.",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be deleted without actually deleting.",
    )
    parser.add_argument(
        "--stats", "-s",
        action="store_true",
        help="Show table statistics only.",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--cron",
        action="store_true",
        help="Cron mode: quiet output, exit code only. "
             "Only prints errors to stderr.",
    )
    parser.add_argument(
        "--no-vacuum",
        action="store_true",
        help="Skip VACUUM and ANALYZE after purge (faster, but DB may grow).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging.",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, cron=args.cron)

    # Run async
    try:
        exit_code = asyncio.run(
            run_purge(
                days=args.days,
                dry_run_mode=args.dry_run,
                stats_only=args.stats,
                json_output=args.json,
                cron=args.cron,
                no_vacuum=args.no_vacuum,
            )
        )
        return exit_code
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        logging.error(f"Purge failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
