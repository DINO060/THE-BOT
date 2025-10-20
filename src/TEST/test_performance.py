# ==================== tests/test_performance.py ====================
"""Performance and load testing"""

import pytest
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
import random
import statistics

from src.core.cache import cache
from src.core.security import RateLimiter
from src.services.storage import storage_service


class TestPerformance:
    """Performance benchmarks"""
    
    @pytest.mark.benchmark
    async def test_cache_performance(self):
        """Test cache read/write performance"""
        iterations = 1000
        
        # Write performance
        write_times = []
        for i in range(iterations):
            key = f"perf_test_{i}"
            value = {"data": f"value_{i}" * 100}  # ~1KB data
            
            start = time.perf_counter()
            await cache.set("performance", key, value)
            write_times.append(time.perf_counter() - start)
        
        # Read performance
        read_times = []
        for i in range(iterations):
            key = f"perf_test_{i}"
            
            start = time.perf_counter()
            await cache.get("performance", key)
            read_times.append(time.perf_counter() - start)
        
        # Cleanup
        await cache.invalidate_pattern("performance:perf_test_*")
        
        # Assertions
        avg_write = statistics.mean(write_times) * 1000  # Convert to ms
        avg_read = statistics.mean(read_times) * 1000
        p95_write = statistics.quantiles(write_times, n=20)[18] * 1000
        p95_read = statistics.quantiles(read_times, n=20)[18] * 1000
        
        print(f"\nCache Performance:")
        print(f"  Avg Write: {avg_write:.2f}ms")
        print(f"  Avg Read: {avg_read:.2f}ms")
        print(f"  P95 Write: {p95_write:.2f}ms")
        print(f"  P95 Read: {p95_read:.2f}ms")
        
        # Performance requirements
        assert avg_write < 10  # Average write under 10ms
        assert avg_read < 5    # Average read under 5ms
        assert p95_write < 50  # P95 write under 50ms
        assert p95_read < 20   # P95 read under 20ms
    
    @pytest.mark.benchmark
    async def test_rate_limiter_performance(self):
        """Test rate limiter under load"""
        from src.core.cache import cache
        limiter = RateLimiter(cache.redis)
        
        # Simulate concurrent users
        async def simulate_user(user_id: int, requests: int):
            results = []
            for _ in range(requests):
                start = time.perf_counter()
                allowed = limiter.check_rate_limit(
                    f"user:{user_id}",
                    limit=10,
                    window=60
                )
                results.append(time.perf_counter() - start)
                await asyncio.sleep(random.uniform(0.01, 0.1))
            return results
        
        # Run simulation
        tasks = []
        for user_id in range(100):  # 100 concurrent users
            tasks.append(simulate_user(user_id, 20))
        
        start = time.perf_counter()
        all_results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start
        
        # Flatten results
        all_times = [t for user_times in all_results for t in user_times]
        
        # Calculate metrics
        avg_check = statistics.mean(all_times) * 1000
        p95_check = statistics.quantiles(all_times, n=20)[18] * 1000
        throughput = len(all_times) / total_time
        
        print(f"\nRate Limiter Performance:")
        print(f"  Avg Check: {avg_check:.2f}ms")
        print(f"  P95 Check: {p95_check:.2f}ms")
        print(f"  Throughput: {throughput:.0f} checks/sec")
        
        # Performance requirements
        assert avg_check < 5   # Average check under 5ms
        assert p95_check < 20  # P95 check under 20ms
        assert throughput > 500  # Handle 500+ checks/sec
    
    @pytest.mark.load
    async def test_concurrent_downloads(self):
        """Test system under concurrent download load"""
        # This would typically be run against a test environment
        # with mocked external services
        
        async def simulate_download(user_id: int):
            """Simulate a download request"""
            from src.workers.tasks.download import process_media_download
            
            try:
                # Mock the actual download
                with patch('src.plugins.youtube.YouTubePlugin.download') as mock_dl:
                    mock_dl.return_value = (True, '/tmp/test.mp4', {})
                    
                    result = await process_media_download(
                        user_id,
                        f"https://youtube.com/watch?v=test_{user_id}",
                        'video',
                        {}
                    )
                    return 'success' if result['success'] else 'failed'
            except Exception:
                return 'error'
        
        # Simulate 50 concurrent downloads
        tasks = []
        for i in range(50):
            tasks.append(simulate_download(10000 + i))
        
        start = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.perf_counter() - start
        
        # Count results
        success = sum(1 for r in results if r == 'success')
        failed = sum(1 for r in results if r == 'failed')
        errors = sum(1 for r in results if r == 'error' or isinstance(r, Exception))
        
        print(f"\nConcurrent Download Test:")
        print(f"  Total: 50 downloads")
        print(f"  Success: {success}")
        print(f"  Failed: {failed}")
        print(f"  Errors: {errors}")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Throughput: {50/duration:.1f} downloads/sec")
        
        # Requirements
        assert success >= 45  # At least 90% success rate
        assert duration < 30  # Complete within 30 seconds
