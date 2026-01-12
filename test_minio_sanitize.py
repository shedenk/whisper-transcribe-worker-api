import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from utils import sanitize_minio_endpoint
    print("PASS: Imported utils")
except ImportError as e:
    print(f"FAIL: Could not import utils: {e}")
    sys.exit(1)

def test_sanitize_minio_endpoint():
    test_cases = [
        ("http://minio:9000", "minio:9000"),
        ("https://s3.amazonaws.com/", "s3.amazonaws.com"),
        ("minio:9000/bucket", "minio:9000"),
        ("justhost.com", "justhost.com"),
        ("http://127.0.0.1:9000/some/path", "127.0.0.1:9000"),
        ("", ""),
        (None, ""),
    ]

    for input_val, expected in test_cases:
        result = sanitize_minio_endpoint(input_val)
        if result == expected:
            print(f"PASS: '{input_val}' -> '{result}'")
        else:
            print(f"FAIL: '{input_val}' -> '{result}' (Expected '{expected}')")
            sys.exit(1)

if __name__ == "__main__":
    try:
        test_sanitize_minio_endpoint()
        print("\nAll MinIO sanitization tests passed successfully!")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
