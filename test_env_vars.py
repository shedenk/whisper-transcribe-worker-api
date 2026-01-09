
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from utils import valid_int_env, valid_str_env
    print("PASS: Imported utils")
except ImportError as e:
    print(f"FAIL: Could not import utils: {e}")
    sys.exit(1)

def test_valid_str_env():
    # Test 1: Normal string
    os.environ["TEST_STR"] = "cuda"
    assert valid_str_env("TEST_STR", "cpu") == "cuda"
    print("PASS: valid_str_env normal")

    # Test 2: Empty string -> default
    os.environ["TEST_STR"] = ""
    assert valid_str_env("TEST_STR", "cpu") == "cpu"
    print("PASS: valid_str_env empty string")

    # Test 3: Whitespace -> default
    os.environ["TEST_STR"] = "   "
    assert valid_str_env("TEST_STR", "cpu") == "cpu"
    print("PASS: valid_str_env whitespace")

    # Test 4: Missing -> default
    if "TEST_STR" in os.environ:
        del os.environ["TEST_STR"]
    assert valid_str_env("TEST_STR", "cpu") == "cpu"
    print("PASS: valid_str_env missing")

def test_valid_int_env():
    # Double check int env still works
    os.environ["TEST_INT"] = ""
    assert valid_int_env("TEST_INT", 99) == 99
    print("PASS: valid_int_env empty string")

if __name__ == "__main__":
    try:
        test_valid_str_env()
        test_valid_int_env()
        print("\nAll tests passed successfully!")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
