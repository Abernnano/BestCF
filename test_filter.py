import unittest
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from filter import (
    Config, Logger, CacheManager, get_flag, extract_country_code
)

class TestConfig(unittest.TestCase):
    def test_config_values(self):
        self.assertEqual(Config.BASE_DIR, "./bestcf")
        self.assertIsInstance(Config.CLASSIFY_FILES, list)
        self.assertGreater(len(Config.COLO_MAP), 0)
    
    def test_should_run_at_desired_time(self):
        result = Config.should_run_at_desired_time()
        self.assertIsInstance(result, bool)


class TestLogger(unittest.TestCase):
    def test_logger_methods(self):
        Logger.info("Test info message")
        Logger.warning("Test warning message")
        Logger.error("Test error message")
        Logger.success("Test success message")


class TestCacheManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.test_dir, "test_cache.pkl")
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_cache_operations(self):
        cache = CacheManager(self.cache_file)
        cache.set("test_key", "test_value")
        self.assertEqual(cache.get("test_key"), "test_value")
    
    def test_cache_expiry(self):
        cache = CacheManager(self.cache_file)
        cache.set("expire_key", "expire_value")
        cache.cache["expire_key"] = ("expired_value", datetime.now() - timedelta(hours=25))
        self.assertIsNone(cache.get("expire_key", max_age_hours=24))


class TestUtils(unittest.TestCase):
    def test_get_flag(self):
        self.assertEqual(get_flag("US"), "🇺🇸")
        self.assertEqual(get_flag("CN"), "🇨🇳")
        self.assertEqual(get_flag(""), "🌐")
        self.assertEqual(get_flag(None), "🌐")
        self.assertEqual(get_flag("USA"), "🌐")
    
    def test_extract_country_code(self):
        self.assertEqual(extract_country_code("1.1.1.1#🇺🇸 US | Test"), "US")
        self.assertEqual(extract_country_code("1.1.1.1#🇨🇳 CN | Test"), "CN")
        self.assertEqual(extract_country_code("1.1.1.1#US | Test"), "US")
        self.assertIsNone(extract_country_code("1.1.1.1"))


if __name__ == "__main__":
    unittest.main()
