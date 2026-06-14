import unittest
import sys

def main():
    print("Running Page Watcher Test Suite...")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir="tests", pattern="test_*.py")
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        print("❌ Test suite failed!")
        sys.exit(1)
    else:
        print("✅ All tests passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
