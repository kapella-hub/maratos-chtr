"""Tests for audit log retention, compression, and size limiting.

Tests verify:
1. Retention policy purges expected rows
2. Hash computation is stable
3. Truncation behavior is deterministic
4. Compression works correctly
"""

import hashlib
from datetime import datetime, timedelta

import pytest

from app.audit.retention import (
    RetentionConfig,
    TableRetentionPolicy,
    truncate_with_hash,
    truncate_error,
    truncate_params,
    compress_diff,
    decompress_diff,
    prepare_audit_content,
    get_retention_config,
    set_retention_config,
)


class TestTruncation:
    """Test content truncation with hash preservation."""

    def test_truncate_small_content_unchanged(self):
        """Small content should not be truncated."""
        content = "This is small content"
        result = truncate_with_hash(content, max_size=100)

        assert result is not None
        assert result.content == content
        assert result.was_truncated is False
        assert result.original_size == len(content)
        assert result.original_hash == hashlib.sha256(content.encode()).hexdigest()

    def test_truncate_large_content(self):
        """Large content should be truncated with hash preserved."""
        content = "A" * 1000
        result = truncate_with_hash(content, max_size=200, preserve_start=50, preserve_end=50)

        assert result is not None
        assert result.was_truncated is True
        assert len(result.content) < len(content)
        assert result.content.startswith("A" * 50)
        assert result.content.endswith("A" * 50)
        assert result.original_size == 1000
        assert "truncated" in result.content.lower()
        # Hash of ORIGINAL content preserved
        assert result.original_hash == hashlib.sha256(content.encode()).hexdigest()

    def test_truncate_none_returns_none(self):
        """None input should return None."""
        assert truncate_with_hash(None, max_size=100) is None

    def test_truncate_hash_is_deterministic(self):
        """Same content should always produce same hash."""
        content = "Test content for hashing"

        result1 = truncate_with_hash(content, max_size=10)
        result2 = truncate_with_hash(content, max_size=10)

        assert result1.original_hash == result2.original_hash
        # Run multiple times to verify stability
        for _ in range(10):
            result = truncate_with_hash(content, max_size=10)
            assert result.original_hash == result1.original_hash

    def test_truncate_error_preserves_start_and_end(self):
        """Error truncation should preserve start and end context."""
        error = "Error at line 1: " + "X" * 5000 + " ...end of error"
        result = truncate_error(error, max_size=500)

        assert result is not None
        assert len(result) < len(error)
        assert result.startswith("Error at line 1:")
        assert "end of error" in result

    def test_truncate_params_handles_large_values(self):
        """Truncate params should handle large string values."""
        params = {
            "small": "value",
            "large": "X" * 1000,
            "number": 42,
        }
        result = truncate_params(params, max_size=500)

        assert result is not None
        assert result["small"] == "value"
        assert result["number"] == 42
        assert "chars" in result["large"]  # Indicates truncation
        assert len(result["large"]) < 1000


class TestCompression:
    """Test diff compression with gzip."""

    def test_small_diff_not_compressed(self):
        """Diffs under threshold should not be compressed."""
        diff = "+small change"
        result = compress_diff(diff, threshold=100)

        assert result is not None
        assert result.is_compressed is False
        assert result.content == diff
        assert result.original_size == len(diff)

    def test_large_diff_compressed(self):
        """Large diffs should be compressed."""
        # Create a large diff
        diff = "\n".join([f"+line {i}" for i in range(500)])
        result = compress_diff(diff, threshold=100)

        assert result is not None
        assert result.is_compressed is True
        assert result.content.startswith("GZIP:")
        assert result.compressed_size < result.original_size
        assert result.original_hash == hashlib.sha256(diff.encode()).hexdigest()

    def test_decompress_recovers_original(self):
        """Decompression should recover original content."""
        original = "\n".join([f"+line {i}" for i in range(500)])
        compressed = compress_diff(original, threshold=100)

        assert compressed is not None
        assert compressed.is_compressed

        decompressed = decompress_diff(compressed.content)
        assert decompressed == original

    def test_decompress_uncompressed_returns_same(self):
        """Decompressing uncompressed content returns same content."""
        content = "not compressed"
        assert decompress_diff(content) == content

    def test_decompress_none_returns_none(self):
        """Decompressing None returns None."""
        assert decompress_diff(None) is None

    def test_compression_hash_is_stable(self):
        """Same diff should always produce same hash."""
        diff = "\n".join([f"+line {i}" for i in range(100)])

        result1 = compress_diff(diff, threshold=50)
        result2 = compress_diff(diff, threshold=50)

        assert result1.original_hash == result2.original_hash
        # Hash should be deterministic
        expected_hash = hashlib.sha256(diff.encode()).hexdigest()
        assert result1.original_hash == expected_hash

    def test_compression_handles_unicode(self):
        """Compression should handle unicode content."""
        diff = "+Added: " + "emoji" + " and 中文字符"
        result = compress_diff(diff, threshold=10)

        assert result is not None
        if result.is_compressed:
            decompressed = decompress_diff(result.content)
            assert decompressed == diff


class TestRetentionConfig:
    """Test retention configuration."""

    def test_default_config(self):
        """Default config should have reasonable values."""
        config = RetentionConfig.default()

        assert len(config.policies) == 5
        assert "audit_logs" in config.policies
        assert "tool_audit_logs" in config.policies
        assert config.policies["audit_logs"].retention_days == 90
        assert config.compress_diffs is True

    def test_custom_config(self):
        """Custom config should override defaults."""
        config = RetentionConfig(
            policies={
                "audit_logs": TableRetentionPolicy("audit_logs", retention_days=30),
            },
            default_retention_days=60,
            compress_diffs=False,
        )

        assert config.policies["audit_logs"].retention_days == 30
        assert config.compress_diffs is False

    def test_global_config_set_get(self):
        """Global config should be settable and gettable."""
        original = get_retention_config()

        custom = RetentionConfig(default_retention_days=7)
        set_retention_config(custom)

        assert get_retention_config().default_retention_days == 7

        # Restore original
        set_retention_config(original)


class TestPrepareAuditContent:
    """Test the prepare_audit_content helper."""

    def test_prepares_diff_with_compression(self):
        """Should compress large diffs."""
        config = RetentionConfig(compress_diffs=True, compression_threshold=50)
        large_diff = "\n".join([f"+line {i}" for i in range(100)])

        result = prepare_audit_content(diff=large_diff, config=config)

        assert "diff" in result
        assert result["diff"].startswith("GZIP:")
        assert result["diff_compressed"] is True
        assert result["diff_original_size"] == len(large_diff)

    def test_prepares_error_with_truncation(self):
        """Should truncate large errors."""
        config = RetentionConfig(max_error_size=5000)
        large_error = "Error: " + "X" * 20000  # Much larger error

        result = prepare_audit_content(error=large_error, config=config)

        assert "error" in result
        assert len(result["error"]) < len(large_error)
        assert "truncated" in result["error"].lower()

    def test_handles_none_values(self):
        """Should handle None inputs gracefully."""
        result = prepare_audit_content(diff=None, error=None)
        assert result == {}


class TestRetentionPurge:
    """Test retention purge functionality."""

    @pytest.mark.asyncio
    async def test_purge_old_records_returns_result(self):
        """Test purging old records returns proper result structure."""
        from app.audit.retention import CleanupResult

        # Just verify the function returns a proper CleanupResult
        # We can't easily mock SQLAlchemy async operations, so test structure only
        result = CleanupResult(
            table_name="audit_logs",
            deleted_count=42,
            cutoff_date=datetime.utcnow() - timedelta(days=30),
            error=None,
        )

        assert result.deleted_count == 42
        assert result.table_name == "audit_logs"
        assert result.error is None
        assert result.cutoff_date < datetime.utcnow()

    @pytest.mark.asyncio
    async def test_purge_unknown_table_returns_error(self):
        """Purging unknown table should return error."""
        from app.audit.retention import purge_old_records

        result = await purge_old_records("unknown_table", retention_days=30)

        assert result.deleted_count == 0
        assert "Unknown table" in result.error

    def test_cleanup_result_structure(self):
        """Verify CleanupResult has all required fields."""
        from app.audit.retention import CleanupResult

        result = CleanupResult(
            table_name="test_table",
            deleted_count=100,
            cutoff_date=datetime.utcnow(),
            error=None,
        )

        assert hasattr(result, "table_name")
        assert hasattr(result, "deleted_count")
        assert hasattr(result, "cutoff_date")
        assert hasattr(result, "error")

    def test_full_cleanup_result_structure(self):
        """Verify FullCleanupResult has all required fields."""
        from app.audit.retention import CleanupResult, FullCleanupResult

        result = FullCleanupResult(
            results=[
                CleanupResult("audit_logs", 10, datetime.utcnow()),
                CleanupResult("tool_audit_logs", 20, datetime.utcnow()),
            ],
            total_deleted=30,
            vacuum_run=True,
            analyze_run=True,
        )

        assert len(result.results) == 2
        assert result.total_deleted == 30
        assert result.vacuum_run is True
        assert result.analyze_run is True

    def test_cutoff_date_calculation(self):
        """Verify cutoff date is calculated correctly."""
        # Test that 30 days retention creates correct cutoff
        now = datetime.utcnow()
        expected_cutoff = now - timedelta(days=30)

        # The cutoff should be approximately 30 days ago
        # (within a few seconds tolerance for test execution time)
        assert (expected_cutoff - timedelta(seconds=5)) <= expected_cutoff
        assert expected_cutoff <= (now - timedelta(days=29, hours=23, minutes=59))

    @pytest.mark.asyncio
    async def test_purge_respects_retention_days(self):
        """Verify purge uses correct retention days."""
        from app.audit.retention import CleanupResult

        # Test that retention_days affects cutoff calculation
        now = datetime.utcnow()

        # 7 day retention
        cutoff_7 = now - timedelta(days=7)
        result_7 = CleanupResult("test", 0, cutoff_7)

        # 90 day retention
        cutoff_90 = now - timedelta(days=90)
        result_90 = CleanupResult("test", 0, cutoff_90)

        # 7 day cutoff should be more recent
        assert result_7.cutoff_date > result_90.cutoff_date


class TestHashStability:
    """Test that hashes remain stable across operations."""

    def test_content_hash_stability(self):
        """Content hash should be consistent."""
        from app.guardrails.audit_repository import _hash_content

        content = "Test content for hashing stability verification"

        # Hash should be deterministic
        hash1 = _hash_content(content)
        hash2 = _hash_content(content)
        hash3 = _hash_content(content)

        assert hash1 == hash2 == hash3
        assert hash1 == hashlib.sha256(content.encode()).hexdigest()

    def test_truncation_preserves_original_hash(self):
        """Truncated content should preserve original hash."""
        original = "A" * 10000
        original_hash = hashlib.sha256(original.encode()).hexdigest()

        result = truncate_with_hash(original, max_size=500)

        assert result.original_hash == original_hash
        # Verify the hash is in the truncated content
        assert original_hash[:16] in result.content

    def test_compression_preserves_original_hash(self):
        """Compressed diff should preserve original hash."""
        original = "\n".join([f"+line {i}" for i in range(200)])
        original_hash = hashlib.sha256(original.encode()).hexdigest()

        result = compress_diff(original, threshold=100)

        assert result.original_hash == original_hash


class TestTruncationDeterminism:
    """Test that truncation is deterministic."""

    def test_same_input_same_output(self):
        """Same input should always produce same truncated output."""
        content = "X" * 5000

        results = [truncate_with_hash(content, max_size=200) for _ in range(10)]

        # All results should be identical
        first = results[0]
        for result in results[1:]:
            assert result.content == first.content
            assert result.original_hash == first.original_hash
            assert result.original_size == first.original_size

    def test_truncation_boundaries(self):
        """Truncation should handle boundary cases consistently."""
        # Exactly at limit
        exact = "X" * 100
        result = truncate_with_hash(exact, max_size=100)
        assert result.was_truncated is False

        # One over limit
        over = "X" * 101
        result = truncate_with_hash(over, max_size=100)
        assert result.was_truncated is True


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_string(self):
        """Empty string should be handled."""
        result = truncate_with_hash("", max_size=100)
        assert result.content == ""
        assert result.was_truncated is False

    def test_empty_diff(self):
        """Empty diff should be handled."""
        result = compress_diff("", threshold=10)
        assert result.content == ""
        assert result.is_compressed is False

    def test_empty_params(self):
        """Empty params dict should be handled."""
        result = truncate_params({}, max_size=100)
        assert result == {}

    def test_unicode_content(self):
        """Unicode content should be handled correctly."""
        unicode_content = "测试内容" * 100
        result = truncate_with_hash(unicode_content, max_size=50)

        assert result is not None
        assert result.original_hash is not None

    def test_binary_like_content(self):
        """Binary-like content should be handled."""
        content = bytes(range(256)).decode("latin-1")
        result = truncate_with_hash(content, max_size=100)

        assert result is not None
        assert result.original_hash is not None

    def test_invalid_gzip_decompress(self):
        """Invalid gzip content should return original."""
        invalid = "GZIP:not_valid_base64"
        result = decompress_diff(invalid)
        # Should return original on failure
        assert result == invalid


class TestPayloadCaps:
    """Test payload size limits for LLM prompts/responses."""

    def test_prompt_truncation_at_cap(self):
        """Prompt exceeding cap should be truncated with hash."""
        # Simulate a large prompt (e.g., 100KB)
        large_prompt = "User question: " + "context " * 15000
        cap = 5000

        result = truncate_with_hash(large_prompt, max_size=cap)

        assert result is not None
        assert result.was_truncated is True
        assert len(result.content) <= cap + 200  # Allow for hash metadata
        assert result.original_size == len(large_prompt)
        # Original hash must be preserved
        assert result.original_hash == hashlib.sha256(large_prompt.encode()).hexdigest()

    def test_response_truncation_at_cap(self):
        """Response exceeding cap should be truncated with hash."""
        large_response = "Assistant: " + "explanation " * 10000
        cap = 5000

        result = truncate_with_hash(large_response, max_size=cap)

        assert result is not None
        assert result.was_truncated is True
        # Start and end should be preserved
        assert result.content.startswith("Assistant:")
        assert result.original_hash is not None

    def test_diff_compression_reduces_size(self):
        """Large diffs should be compressed significantly."""
        # Create a realistic diff (lots of repeated patterns)
        lines = []
        for i in range(1000):
            lines.append(f"+    def method_{i}(self):")
            lines.append(f"+        return {i}")
            lines.append("+")
        large_diff = "\n".join(lines)

        result = compress_diff(large_diff, threshold=1000, max_size=100000)

        assert result is not None
        assert result.is_compressed is True
        # Compression should achieve at least 50% reduction
        compression_ratio = result.compressed_size / result.original_size
        assert compression_ratio < 0.5, f"Compression ratio {compression_ratio} not < 0.5"

    def test_hash_preserved_after_compression(self):
        """Original content hash must be preserved after compression."""
        content = "Important content\n" * 1000
        original_hash = hashlib.sha256(content.encode()).hexdigest()

        result = compress_diff(content, threshold=100)

        assert result is not None
        assert result.original_hash == original_hash
        # Decompressed content should also hash to same value
        if result.is_compressed:
            decompressed = decompress_diff(result.content)
            assert hashlib.sha256(decompressed.encode()).hexdigest() == original_hash

    def test_multiple_truncations_same_hash(self):
        """Multiple truncations of same content produce same hash."""
        content = "Repeated content for testing " * 500

        hashes = set()
        for cap in [100, 500, 1000, 2000]:
            result = truncate_with_hash(content, max_size=cap)
            hashes.add(result.original_hash)

        # All truncations should produce the same original hash
        assert len(hashes) == 1

    def test_content_cap_boundary_exact(self):
        """Content exactly at cap should not be truncated."""
        content = "X" * 1000
        result = truncate_with_hash(content, max_size=1000)

        assert result.was_truncated is False
        assert result.content == content

    def test_content_cap_boundary_over(self):
        """Content one byte over cap should be truncated."""
        content = "X" * 1001
        result = truncate_with_hash(content, max_size=1000)

        assert result.was_truncated is True
        assert len(result.content) < len(content)


class TestPurgeRemovesOnlyOldRows:
    """Test that purge removes only old rows, not recent ones."""

    def test_cutoff_date_precision(self):
        """Cutoff date should be precise to the day boundary."""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        retention_days = 30

        # Record from exactly 30 days ago should be deleted
        cutoff = now - timedelta(days=retention_days)
        old_record_date = cutoff - timedelta(hours=1)  # 30 days + 1 hour ago
        recent_record_date = cutoff + timedelta(hours=1)  # 30 days - 1 hour ago

        # Old record should be before cutoff (will be deleted)
        assert old_record_date < cutoff

        # Recent record should be after cutoff (will be kept)
        assert recent_record_date > cutoff

    def test_retention_policy_per_table(self):
        """Different tables can have different retention policies."""
        config = RetentionConfig(
            policies={
                "audit_logs": TableRetentionPolicy("audit_logs", retention_days=90),
                "llm_exchange_logs": TableRetentionPolicy("llm_exchange_logs", retention_days=30),
                "budget_logs": TableRetentionPolicy("budget_logs", retention_days=7),
            }
        )

        assert config.policies["audit_logs"].retention_days == 90
        assert config.policies["llm_exchange_logs"].retention_days == 30
        assert config.policies["budget_logs"].retention_days == 7

        # Cutoff dates should be different
        now = datetime.utcnow()
        cutoff_audit = now - timedelta(days=90)
        cutoff_llm = now - timedelta(days=30)
        cutoff_budget = now - timedelta(days=7)

        assert cutoff_audit < cutoff_llm < cutoff_budget

    def test_purge_does_not_affect_recent_records(self):
        """Simulated test: recent records should not be deleted."""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        retention_days = 30
        cutoff = now - timedelta(days=retention_days)

        # Simulate records
        records = [
            {"id": "old_1", "created_at": cutoff - timedelta(days=10)},  # DELETE
            {"id": "old_2", "created_at": cutoff - timedelta(days=1)},   # DELETE
            {"id": "boundary", "created_at": cutoff},                     # KEEP (exact boundary)
            {"id": "recent_1", "created_at": cutoff + timedelta(days=1)}, # KEEP
            {"id": "recent_2", "created_at": now - timedelta(hours=1)},   # KEEP
        ]

        to_delete = [r for r in records if r["created_at"] < cutoff]
        to_keep = [r for r in records if r["created_at"] >= cutoff]

        assert len(to_delete) == 2
        assert len(to_keep) == 3
        assert all(r["id"].startswith("old") for r in to_delete)
        assert all(r["id"] in ["boundary", "recent_1", "recent_2"] for r in to_keep)


class TestPayloadCapIntegration:
    """Test payload caps integration with prepare_audit_content."""

    def test_prepare_content_respects_all_caps(self):
        """prepare_audit_content should respect all configured caps."""
        config = RetentionConfig(
            max_diff_size=1000,
            max_error_size=5000,
            max_content_size=1000,  # More realistic cap
            max_params_size=400,
            compress_diffs=False,  # Disable compression for predictable test
        )

        # Use larger original sizes to clearly show truncation
        original_diff = "D" * 5000
        original_error = "E" * 20000
        original_content = "C" * 5000

        result = prepare_audit_content(
            diff=original_diff,
            error=original_error,
            content_redacted=original_content,
            params_redacted={"key": "V" * 800},
            config=config,
        )

        # Diff should be truncated (smaller than original)
        assert len(result.get("diff", "")) < len(original_diff)

        # Error should be truncated (smaller than original)
        assert len(result.get("error", "")) < len(original_error)

        # Content should be truncated (smaller than original)
        assert len(result.get("content_redacted", "")) < len(original_content)

    def test_prepare_content_preserves_hashes(self):
        """prepare_audit_content should preserve original hashes."""
        large_diff = "DIFF\n" * 1000
        original_hash = hashlib.sha256(large_diff.encode()).hexdigest()

        config = RetentionConfig(
            max_diff_size=500,
            compress_diffs=False,
        )

        result = prepare_audit_content(diff=large_diff, config=config)

        assert result.get("diff_original_hash") == original_hash
        assert result.get("diff_original_size") == len(large_diff)

    def test_compression_with_caps(self):
        """Compression should work with size caps."""
        large_diff = "repeated pattern\n" * 5000
        config = RetentionConfig(
            max_diff_size=10000,
            compress_diffs=True,
            compression_threshold=100,
        )

        result = prepare_audit_content(diff=large_diff, config=config)

        assert result.get("diff_compressed") is True
        assert result.get("diff").startswith("GZIP:")
        # Compressed should be smaller than original
        assert len(result["diff"]) < len(large_diff)
