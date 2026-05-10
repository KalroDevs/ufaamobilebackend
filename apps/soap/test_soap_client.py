#!/usr/bin/env python
"""Test script for SOAP web services"""

from zeep import Client
import sys

def test_soap_services():
    """Test all SOAP services"""
    
    # WSDL URL
    wsdl_url = "http://localhost:8000/soap/wsdl/"
    
    print("Testing SOAP Services...")
    print(f"WSDL URL: {wsdl_url}")
    print("-" * 50)
    
    try:
        client = Client(wsdl_url)
        
        # Test 1: Search Assets
        print("\n1. Testing Asset Search...")
        result = client.service.search_assets("12345678", "id")
        print(f"   Success: {result.success}")
        print(f"   Message: {result.message}")
        print(f"   Assets found: {len(result.assets)}")
        
        # Test 2: Submit Claim
        print("\n2. Testing Claim Submission...")
        claim_data = {
            'claim_number': 'SOAP-TEST-001',
            'claim_type': 'original_owner',
            'claimant': {
                'surname': 'Test',
                'given_name': 'User',
                'id_number': '12345678',
                'kra_pin': 'A001234567J',
                'phone_number': '+254712345678',
                'email': 'test@example.com',
                'nationality': 'Kenyan',
                'physical_address': '123 Test Street, Nairobi',
                'has_disability': False,
                'disability_category': ''
            },
            'assets': [{
                'asset_id': 'AST001',
                'holder_name': 'Equity Bank',
                'asset_type': 'cash',
                'amount': 150000,
                'source': 'bank_account',
                'description': 'Savings account'
            }],
            'total_amount': 150000,
            'payment_details': 'Bank transfer to Equity account'
        }
        result = client.service.submit_claim(claim_data)
        print(f"   Success: {result.success}")
        print(f"   Claim Number: {result.claim_number}")
        print(f"   Message: {result.message}")
        print(f"   Tracking URL: {result.tracking_url}")
        
        # Test 3: Get Claim Status
        print("\n3. Testing Claim Status...")
        result = client.service.get_claim_status("SOAP-TEST-001", "12345678")
        print(f"   Success: {result.success}")
        print(f"   Status: {result.status}")
        print(f"   Total Amount: {result.total_amount}")
        print(f"   Next Step: {result.next_step}")
        
        # Test 4: Staff Login
        print("\n4. Testing Staff Login...")
        result = client.service.staff_login("EMP001", "password", "test_device_123")
        print(f"   Success: {result.success}")
        print(f"   Staff Name: {result.staff_name}")
        print(f"   Department: {result.department}")
        print(f"   Session Token: {result.session_token[:20]}...")
        
        # Test 5: Update Asset Location
        print("\n5. Testing Asset Location Update...")
        result = client.service.update_asset_location(
            "AST001", "found", "Located in main branch", "EMP001", -1.283333, 36.816667
        )
        print(f"   Success: {result.success}")
        print(f"   Status: {result.status}")
        print(f"   Message: {result.message}")
        
        print("\n" + "=" * 50)
        print("All SOAP tests completed successfully!")
        
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_soap_services()