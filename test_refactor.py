
import os
import sys

# Add current directory to path so we can import utils
sys.path.append(os.getcwd())

try:
    from utils import valid_int_env
    print("PASS: Imported valid_int_env from utils")
except ImportError as e:
    print(f"FAIL: Could not import valid_int_env: {e}")
    sys.exit(1)

def test_valid_int_env():
    # Test case 1: Normal integer
    os.environ["TEST_VAR"] = "123"
    assert valid_int_env("TEST_VAR", 10) == 123
    print("PASS: Normal integer")

    # Test case 2: Empty string
    os.environ["TEST_VAR"] = ""
    assert valid_int_env("TEST_VAR", 10) == 10
    print("PASS: Empty string")

    # Test case 3: Unset variable
    if "TEST_VAR" in os.environ:
        del os.environ["TEST_VAR"]
    assert valid_int_env("TEST_VAR", 10) == 10
    print("PASS: Unset variable")

    # Test case 4: Invalid integer
    os.environ["TEST_VAR"] = "abc"
    assert valid_int_env("TEST_VAR", 10) == 10
    print("PASS: Invalid integer")

    # Test case 5: Whitespace only
    os.environ["TEST_VAR"] = "   "
    assert valid_int_env("TEST_VAR", 10) == 10
    print("PASS: Whitespace only")

if __name__ == "__main__":
    try:
        test_valid_int_env()
        print("\nAll tests passed successfully!")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
