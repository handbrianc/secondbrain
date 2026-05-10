import time
from multiprocessing import Pool


def _process_file(path):
    time.sleep(0.1)
    return True


class TestMulticoreParallel:
    """Test parallel execution across multiple cores."""

    def test_parallel_execution_speedup(self):
        num_files = 10
        files = [f"file_{i}.txt" for i in range(num_files)]

        start = time.time()
        for f in files:
            _process_file(f)
        sequential_time = time.time() - start

        start = time.time()
        with Pool(processes=4) as pool:
            pool.map(_process_file, files)
        parallel_time = time.time() - start

        assert parallel_time < sequential_time * 0.8, \
            f"Parallel ({parallel_time:.2f}s) should be faster than sequential ({sequential_time:.2f}s)"

    def test_all_files_processed(self):
        num_files = 20
        files = [f"file_{i}.txt" for i in range(num_files)]

        with Pool(processes=4) as pool:
            results = pool.map(_process_file, files)

        assert len(results) == num_files
        assert all(results)
