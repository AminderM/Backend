"""
Marketing Routes API Tests
Tests for demo request submission, admin endpoints for managing leads
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "aminderpro@gmail.com"
ADMIN_PASSWORD = "Admin123!"


class TestMarketingPublicEndpoints:
    """Public marketing endpoints - no auth required"""
    
    def test_submit_demo_request_success(self):
        """Test successful demo request submission"""
        payload = {
            "first_name": "TEST_John",
            "last_name": "Doe",
            "email": "test_john@example.com",
            "company": "TEST_Company Inc",
            "phone": "(555) 123-4567",
            "role": "Fleet Owner",
            "fleet_size": "11-50 trucks",
            "message": "Interested in TMS features"
        }
        response = requests.post(f"{BASE_URL}/api/marketing/demo-request", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "message" in data
        assert "24 hours" in data["message"]
    
    def test_submit_demo_request_minimal(self):
        """Test demo request with only required fields"""
        payload = {
            "first_name": "TEST_Jane",
            "last_name": "Smith",
            "email": "test_jane@example.com",
            "company": "TEST_Minimal Corp"
        }
        response = requests.post(f"{BASE_URL}/api/marketing/demo-request", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_submit_demo_request_invalid_email(self):
        """Test demo request with invalid email"""
        payload = {
            "first_name": "Test",
            "last_name": "User",
            "email": "invalid-email",
            "company": "Test Company"
        }
        response = requests.post(f"{BASE_URL}/api/marketing/demo-request", json=payload)
        
        # Should fail validation
        assert response.status_code == 422
    
    def test_submit_demo_request_missing_required(self):
        """Test demo request with missing required fields"""
        payload = {
            "first_name": "Test"
            # Missing last_name, email, company
        }
        response = requests.post(f"{BASE_URL}/api/marketing/demo-request", json=payload)
        
        assert response.status_code == 422
    
    def test_get_website_content_hero(self):
        """Test getting hero section content"""
        response = requests.get(f"{BASE_URL}/api/marketing/content/hero")
        
        assert response.status_code == 200
        data = response.json()
        assert "section" in data
        assert "content" in data
        assert data["section"] == "hero"
    
    def test_get_website_content_features(self):
        """Test getting features section content"""
        response = requests.get(f"{BASE_URL}/api/marketing/content/features")
        
        assert response.status_code == 200
        data = response.json()
        assert data["section"] == "features"


class TestMarketingAdminEndpoints:
    """Admin marketing endpoints - auth required"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, "Admin login failed"
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_demo_requests(self):
        """Test getting all demo requests"""
        response = requests.get(
            f"{BASE_URL}/api/marketing/admin/demo-requests",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Verify structure of demo request objects
        if len(data) > 0:
            request = data[0]
            assert "id" in request
            assert "first_name" in request
            assert "last_name" in request
            assert "email" in request
            assert "company" in request
            assert "status" in request
            assert "created_at" in request
    
    def test_get_demo_requests_filter_by_status(self):
        """Test filtering demo requests by status"""
        response = requests.get(
            f"{BASE_URL}/api/marketing/admin/demo-requests?status=new",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned requests should have status 'new'
        for request in data:
            assert request["status"] == "new"
    
    def test_get_marketing_stats(self):
        """Test getting marketing statistics"""
        response = requests.get(
            f"{BASE_URL}/api/marketing/admin/stats",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify stats structure
        assert "total_requests" in data
        assert "new_requests" in data
        assert "contacted" in data
        assert "converted" in data
        assert "recent_requests" in data
        
        # Verify types
        assert isinstance(data["total_requests"], int)
        assert isinstance(data["new_requests"], int)
        assert isinstance(data["recent_requests"], list)
    
    def test_update_demo_request_status(self):
        """Test updating demo request status"""
        # First get a demo request
        list_response = requests.get(
            f"{BASE_URL}/api/marketing/admin/demo-requests",
            headers=self.headers
        )
        assert list_response.status_code == 200
        requests_list = list_response.json()
        
        if len(requests_list) > 0:
            request_id = requests_list[0]["id"]
            
            # Update status
            update_response = requests.put(
                f"{BASE_URL}/api/marketing/admin/demo-requests/{request_id}?status=contacted",
                headers=self.headers
            )
            
            assert update_response.status_code == 200
            data = update_response.json()
            assert data["status"] == "success"
    
    def test_update_demo_request_notes(self):
        """Test updating demo request notes"""
        # First get a demo request
        list_response = requests.get(
            f"{BASE_URL}/api/marketing/admin/demo-requests",
            headers=self.headers
        )
        assert list_response.status_code == 200
        requests_list = list_response.json()
        
        if len(requests_list) > 0:
            request_id = requests_list[0]["id"]
            
            # Update notes
            update_response = requests.put(
                f"{BASE_URL}/api/marketing/admin/demo-requests/{request_id}?notes=Test%20note%20from%20pytest",
                headers=self.headers
            )
            
            assert update_response.status_code == 200
    
    def test_update_nonexistent_request(self):
        """Test updating a non-existent demo request"""
        fake_id = "000000000000000000000000"
        
        response = requests.put(
            f"{BASE_URL}/api/marketing/admin/demo-requests/{fake_id}?status=contacted",
            headers=self.headers
        )
        
        assert response.status_code == 404
    
    def test_admin_endpoints_without_auth(self):
        """Test that admin endpoints require authentication"""
        # No auth header - API returns 401 or 403 for unauthorized access
        response = requests.get(f"{BASE_URL}/api/marketing/admin/demo-requests")
        assert response.status_code in [401, 403]
        
        response = requests.get(f"{BASE_URL}/api/marketing/admin/stats")
        assert response.status_code in [401, 403]


class TestMarketingAdminContentEndpoints:
    """Admin content management endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, "Admin login failed"
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_all_website_content(self):
        """Test getting all website content sections"""
        response = requests.get(
            f"{BASE_URL}/api/marketing/admin/content",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_update_website_content(self):
        """Test updating website content section"""
        payload = {
            "content": {
                "title": "Test Hero Title",
                "subtitle": "Test subtitle"
            }
        }
        
        response = requests.put(
            f"{BASE_URL}/api/marketing/admin/content/hero",
            headers=self.headers,
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
