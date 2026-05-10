#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ufaamobilebackend.settings')
django.setup()

from django.db import connections
from apps.live_operations.models import LiveUnclaimedAsset
from apps.accounts.models import User

def test_routers():
    print("Testing database routers...")
    print("-" * 50)
    
    # Test live_operations model
    try:
        db = LiveUnclaimedAsset.objects.db
        print(f"✅ LiveUnclaimedAsset uses database: {db}")
    except Exception as e:
        print(f"❌ LiveUnclaimedAsset error: {e}")
    
    # Test accounts model
    try:
        db = User.objects.db
        print(f"✅ User model uses database: {db}")
    except Exception as e:
        print(f"❌ User model error: {e}")
    
    # Test direct connections
    print("\nTesting direct connections...")
    
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT 1")
            print("✅ Default (PostgreSQL) connection successful")
    except Exception as e:
        print(f"❌ Default connection error: {e}")
    
    try:
        with connections['ereunify'].cursor() as cursor:
            cursor.execute("SELECT 1")
            print("✅ Ereunify (MSSQL) connection successful")
    except Exception as e:
        print(f"❌ Ereunify connection error: {e}")

if __name__ == "__main__":
    test_routers()