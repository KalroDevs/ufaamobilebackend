# test_permissions.py
import os
from django.conf import settings

def test_media_permissions():
    media_root = settings.MEDIA_ROOT
    print(f"Media root: {media_root}")
    print(f"Exists: {os.path.exists(media_root)}")
    print(f"Is directory: {os.path.isdir(media_root)}")
    print(f"Permissions: {oct(os.stat(media_root).st_mode)[-3:]}")
    print(f"Writable: {os.access(media_root, os.W_OK)}")
    
    # Test creating a test file
    test_file = os.path.join(media_root, 'test.txt')
    try:
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print("Write test: SUCCESS")
    except Exception as e:
        print(f"Write test: FAILED - {e}")

# Run this in Django shell
test_media_permissions()
