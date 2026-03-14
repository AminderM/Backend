"""
Comprehensive Backend Testing for Carrier Profile API
Tests all 9 carrier profile endpoints with authentication, encryption, and edge cases.
"""
import requests
import json
import sys
import os
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional

class CarrierProfileTester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.token = None
        self.profile_id = None
        self.document_id = None
        self.package_access_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}: PASSED {details}")
        else:
            print(f"❌ {name}: FAILED {details}")
        
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details
        })

    def make_request(self, method: str, endpoint: str, data: dict = None, files: dict = None, auth_required: bool = True) -> tuple:
        """Make HTTP request with proper headers"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'} if not files else {}
        
        if auth_required and self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    # Remove Content-Type for file uploads
                    headers.pop('Content-Type', None)
                    response = requests.post(url, headers=headers, files=files, data=data)
                else:
                    response = requests.post(url, headers=headers, json=data)
            elif method == 'PATCH':
                response = requests.patch(url, headers=headers, json=data)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            print(f"📡 {method} {endpoint} -> Status: {response.status_code}")
            
            try:
                response_data = response.json()
            except:
                response_data = {"raw_response": response.text}

            return response.status_code, response_data

        except Exception as e:
            print(f"❌ Request failed: {str(e)}")
            return 500, {"error": str(e)}

    def test_authentication(self) -> bool:
        """Test login with provided credentials"""
        print("\n🔐 Testing Authentication...")
        
        login_data = {
            "email": "aminderpro@gmail.com",
            "password": "Admin@123!"
        }
        
        status, response = self.make_request('POST', 'auth/login', login_data, auth_required=False)
        
        if status == 200 and 'access_token' in response:
            self.token = response['access_token']
            self.log_test("Authentication", True, f"Token: {self.token[:20]}...")
            return True
        else:
            self.log_test("Authentication", False, f"Status {status}: {response}")
            return False

    def test_get_carrier_profile(self) -> bool:
        """Test GET /api/carrier-profiles/me - Should auto-create profile if not exists"""
        print("\n📋 Testing Get Carrier Profile (Auto-creation)...")
        
        status, response = self.make_request('GET', 'carrier-profiles/me')
        
        if status == 200:
            self.profile_id = response.get('id')
            completion = response.get('profile_completion', 0)
            self.log_test("Get Carrier Profile", True, f"ID: {self.profile_id}, Completion: {completion}%")
            
            # Validate structure
            required_fields = ['id', 'user_id', 'company_info', 'documents', 'regulatory', 'fleet', 'payment']
            missing_fields = [field for field in required_fields if field not in response]
            if missing_fields:
                self.log_test("Profile Structure", False, f"Missing fields: {missing_fields}")
                return False
            
            self.log_test("Profile Structure", True, "All required fields present")
            return True
        else:
            self.log_test("Get Carrier Profile", False, f"Status {status}: {response}")
            return False

    def test_update_carrier_profile(self) -> bool:
        """Test PATCH /api/carrier-profiles/me - Primary save endpoint with encrypted payment"""
        print("\n💾 Testing Update Carrier Profile (with encryption)...")
        
        update_data = {
            "company_info": {
                "legal_name": "Test Trucking Co Ltd",
                "dba_name": "TTC",
                "company_type": "trucking_company",
                "country": "Canada",
                "province": "Ontario",
                "phone": "416-555-1234",
                "email": "info@testtruck.com",
                "website": "https://testtruck.com"
            },
            "regulatory": {
                "nsc_number": "NSC123456",
                "nsc_safety_rating": "Satisfactory",
                "cvor_number": "CVOR987654",
                "usdot_number": "DOT12345",
                "mc_number": "MC67890",
                "cross_border_capable": True,
                "fast_card_enrolled": True
            },
            "fleet": {
                "number_of_trucks": 15,
                "number_of_trailers": 25,
                "equipment_types": ["dry_van", "flatbed", "reefer"],
                "hazmat_capable": True,
                "cross_border_capable": True,
                "eld_provider": "ELD Solutions Inc",
                "is_24x7_dispatch": True
            },
            "payment": {
                "payment_method": "direct_deposit",
                "bank_name": "Royal Bank of Canada",
                "transit_number": "12345",
                "institution_number": "003",
                "account_number": "1234567890123",
                "account_type": "checking",
                "currency": "CAD",
                "payment_terms": "net_30"
            }
        }
        
        status, response = self.make_request('PATCH', 'carrier-profiles/me', update_data)
        
        if status == 200:
            self.log_test("Update Carrier Profile", True, f"Profile updated successfully")
            
            # Check that payment fields are masked in response
            payment = response.get('payment', {})
            
            # Check encryption masking
            encryption_tests = [
                ('transit_number_masked', payment.get('transit_number_masked', '').startswith('*')),
                ('account_number_masked', payment.get('account_number_masked', '').startswith('*')),
                ('has_transit_number', payment.get('has_transit_number') == True),
                ('has_account_number', payment.get('has_account_number') == True),
            ]
            
            encryption_passed = all([test[1] for test in encryption_tests])
            if encryption_passed:
                self.log_test("Payment Encryption", True, "Payment fields properly masked")
            else:
                failed_tests = [test[0] for test in encryption_tests if not test[1]]
                self.log_test("Payment Encryption", False, f"Failed tests: {failed_tests}")
            
            # Check profile completion calculation
            completion = response.get('profile_completion', 0)
            if completion > 70:  # Should be high with all this data
                self.log_test("Profile Completion", True, f"Completion: {completion}%")
            else:
                self.log_test("Profile Completion", False, f"Low completion: {completion}%")
            
            return True
        else:
            self.log_test("Update Carrier Profile", False, f"Status {status}: {response}")
            return False

    def test_document_upload(self) -> bool:
        """Test POST /api/carrier-profiles/me/documents - Document upload with expiry"""
        print("\n📄 Testing Document Upload...")
        
        # Create a test PDF file content (base64 encoded)
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000074 00000 n\n0000000120 00000 n\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n179\n%%EOF"
        
        # Prepare file data
        files = {
            'file': ('test_nsc_certificate.pdf', test_pdf_content, 'application/pdf')
        }
        
        # Future expiry date
        expiry_date = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'
        
        data = {
            'document_type': 'nsc_certificate',
            'expiry_date': expiry_date
        }
        
        # Prepare URL with query parameters for file upload
        url_params = f"?document_type=nsc_certificate&expiry_date={expiry_date}"
        endpoint = f"carrier-profiles/me/documents{url_params}"
        
        status, response = self.make_request('POST', endpoint, data=None, files=files)
        
        if status == 200:
            document = response.get('document', {})
            self.document_id = document.get('id')
            
            # Validate document structure
            required_fields = ['id', 'document_type', 'file_name', 'file_url', 'status']
            missing_fields = [field for field in required_fields if field not in document]
            
            if missing_fields:
                self.log_test("Document Upload", False, f"Missing fields: {missing_fields}")
                return False
            
            # Check file URL format (should be base64 data URL)
            file_url = document.get('file_url', '')
            if file_url.startswith('data:application/pdf;base64,'):
                self.log_test("Document Upload", True, f"Document ID: {self.document_id}")
                return True
            else:
                self.log_test("Document Upload", False, f"Invalid file URL format: {file_url[:50]}...")
                return False
        else:
            self.log_test("Document Upload", False, f"Status {status}: {response}")
            return False

    def test_document_deletion(self) -> bool:
        """Test DELETE /api/carrier-profiles/me/documents/{document_id}"""
        print("\n🗑️ Testing Document Deletion...")
        
        if not self.document_id:
            self.log_test("Document Deletion", False, "No document ID available")
            return False
        
        status, response = self.make_request('DELETE', f'carrier-profiles/me/documents/{self.document_id}')
        
        if status == 200:
            self.log_test("Document Deletion", True, response.get('message', 'Deleted successfully'))
            return True
        else:
            self.log_test("Document Deletion", False, f"Status {status}: {response}")
            return False

    def test_logo_upload(self) -> bool:
        """Test POST /api/carrier-profiles/me/logo"""
        print("\n🖼️ Testing Logo Upload...")
        
        # Create a small test image (PNG)
        test_image = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )
        
        files = {
            'file': ('test_logo.png', test_image, 'image/png')
        }
        
        status, response = self.make_request('POST', 'carrier-profiles/me/logo', files=files)
        
        if status == 200:
            logo_url = response.get('logo_url', '')
            if logo_url.startswith('data:image/png;base64,'):
                self.log_test("Logo Upload", True, "Logo uploaded successfully")
                return True
            else:
                self.log_test("Logo Upload", False, f"Invalid logo URL: {logo_url[:50]}...")
                return False
        else:
            self.log_test("Logo Upload", False, f"Status {status}: {response}")
            return False

    def test_logo_deletion(self) -> bool:
        """Test DELETE /api/carrier-profiles/me/logo"""
        print("\n🗑️ Testing Logo Deletion...")
        
        status, response = self.make_request('DELETE', 'carrier-profiles/me/logo')
        
        if status == 200:
            self.log_test("Logo Deletion", True, response.get('message', 'Deleted successfully'))
            return True
        else:
            self.log_test("Logo Deletion", False, f"Status {status}: {response}")
            return False

    def test_send_package(self) -> bool:
        """Test POST /api/carrier-profiles/me/packages"""
        print("\n📦 Testing Send Package...")
        
        package_data = {
            "recipients": [
                {"email": "broker@example.com", "name": "John Broker"},
                {"email": "freight@example.com", "name": "Jane Freight"}
            ],
            "message": "Please review our carrier profile for partnership opportunities.",
            "included_sections": ["company_info", "documents", "regulatory", "fleet"]
        }
        
        status, response = self.make_request('POST', 'carrier-profiles/me/packages', package_data)
        
        if status == 200:
            package = response.get('package', {})
            self.package_access_token = package.get('access_token')
            recipients_count = response.get('recipients_count', 0)
            
            if self.package_access_token and recipients_count == 2:
                self.log_test("Send Package", True, f"Package sent to {recipients_count} recipients")
                return True
            else:
                self.log_test("Send Package", False, f"Missing access token or wrong recipient count")
                return False
        else:
            self.log_test("Send Package", False, f"Status {status}: {response}")
            return False

    def test_get_packages(self) -> bool:
        """Test GET /api/carrier-profiles/me/packages"""
        print("\n📋 Testing Get Packages History...")
        
        status, response = self.make_request('GET', 'carrier-profiles/me/packages')
        
        if status == 200:
            packages = response.get('packages', [])
            if len(packages) > 0:
                # Check if our sent package is in the list
                found_package = any(p.get('access_token') == self.package_access_token for p in packages)
                if found_package:
                    self.log_test("Get Packages", True, f"Found {len(packages)} packages")
                    return True
                else:
                    self.log_test("Get Packages", False, "Sent package not found in history")
                    return False
            else:
                self.log_test("Get Packages", False, "No packages found")
                return False
        else:
            self.log_test("Get Packages", False, f"Status {status}: {response}")
            return False

    def test_public_package_access(self) -> bool:
        """Test GET /api/carrier-profiles/package/{access_token} - Public access without auth"""
        print("\n🌐 Testing Public Package Access (No Auth)...")
        
        if not self.package_access_token:
            self.log_test("Public Package Access", False, "No access token available")
            return False
        
        # Make request WITHOUT authentication
        status, response = self.make_request('GET', f'carrier-profiles/package/{self.package_access_token}', auth_required=False)
        
        if status == 200:
            # Check that payment information is NOT included
            if 'payment' in response:
                self.log_test("Public Package Security", False, "Payment info leaked in public package")
                return False
            
            # Check that included sections are present
            included_sections = ['company_info', 'regulatory', 'fleet', 'package_info']
            missing_sections = [section for section in included_sections if section not in response]
            
            if missing_sections:
                self.log_test("Public Package Access", False, f"Missing sections: {missing_sections}")
                return False
            
            self.log_test("Public Package Access", True, "Package accessible without auth")
            self.log_test("Public Package Security", True, "Payment info properly excluded")
            return True
        else:
            self.log_test("Public Package Access", False, f"Status {status}: {response}")
            return False

    def test_invalid_access_token(self) -> bool:
        """Test public package access with invalid token"""
        print("\n❌ Testing Invalid Access Token...")
        
        status, response = self.make_request('GET', 'carrier-profiles/package/invalid-token-12345', auth_required=False)
        
        if status == 404:
            self.log_test("Invalid Access Token", True, "Properly returns 404 for invalid token")
            return True
        else:
            self.log_test("Invalid Access Token", False, f"Expected 404, got {status}")
            return False

    def test_file_size_limits(self) -> bool:
        """Test file size limits for documents and logos"""
        print("\n📏 Testing File Size Limits...")
        
        # Test oversized document (simulate 11MB file)
        oversized_content = b"x" * (11 * 1024 * 1024)  # 11MB
        files = {
            'file': ('oversized.pdf', oversized_content, 'application/pdf')
        }
        
        status, response = self.make_request('POST', 'carrier-profiles/me/documents?document_type=test_doc', files=files)
        
        if status == 400 and "size exceeds" in str(response):
            self.log_test("File Size Limit", True, "Properly rejects oversized files")
            return True
        else:
            self.log_test("File Size Limit", False, f"Expected 400 size error, got {status}: {response}")
            return False

    def run_comprehensive_tests(self) -> bool:
        """Run all carrier profile API tests"""
        print("🚀 Starting Comprehensive Carrier Profile API Tests")
        print("=" * 60)
        
        # Authentication required for most tests
        if not self.test_authentication():
            print("❌ Authentication failed - cannot proceed with other tests")
            return False
        
        # Core profile operations
        tests = [
            self.test_get_carrier_profile,
            self.test_update_carrier_profile,
            self.test_document_upload,
            self.test_document_deletion,
            self.test_logo_upload,
            self.test_logo_deletion,
            self.test_send_package,
            self.test_get_packages,
            self.test_public_package_access,
            self.test_invalid_access_token,
            self.test_file_size_limits
        ]
        
        # Run all tests
        for test in tests:
            try:
                test()
            except Exception as e:
                self.log_test(f"{test.__name__}", False, f"Exception: {str(e)}")
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        print(f"🎯 Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("🎉 ALL TESTS PASSED!")
            return True
        else:
            print("❌ Some tests failed - check details above")
            return False

def main():
    """Main test runner"""
    tester = CarrierProfileTester()
    success = tester.run_comprehensive_tests()
    
    # Return exit code based on results
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())