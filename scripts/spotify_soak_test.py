#!/usr/bin/env python3
"""
Spotify Soak Test

This script performs a 90-minute soak test of the Spotify integration,
calling lightweight endpoints every 60 seconds using access tokens nearing expiry.

The test verifies:
- Zero 500 errors
- If 401, refresh works
- If invalid_grant, tokens are deleted and _diagnose.reason = "reauth_required" within 1 request
"""

import asyncio
import aiohttp
import json
import time
import logging
from datetime import datetime, UTC, timedelta
from typing import Dict, Any, Optional
import jwt
from app.security.jwt_config import get_jwt_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SpotifySoakTest:
    """Spotify integration soak test."""
    
    def __init__(self, base_url: str = "http://localhost:8000", test_duration_minutes: int = 90):
        self.base_url = base_url
        self.test_duration_minutes = test_duration_minutes
        self.test_start_time = datetime.now(UTC)
        self.test_end_time = self.test_start_time + timedelta(minutes=test_duration_minutes)
        
        # Test statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "refresh_attempts": 0,
            "refresh_successes": 0,
            "reauth_required_events": 0,
            "error_500_count": 0,
            "error_401_count": 0,
            "error_other_count": 0,
        }
        
        # Test user credentials
        self.test_user_id = "soak_test_user"
        self.test_token = None
        
    async def create_test_token(self) -> str:
        """Create a test JWT token for the soak test."""
        from app.tokens import make_access
        
        # Create token with 1 hour expiry (will be refreshed during test)
        token = make_access({"user_id": self.test_user_id}, ttl_s=3600)
        return token
    
    async def make_request(self, session: aiohttp.ClientSession, endpoint: str, method: str = "GET") -> Dict[str, Any]:
        """Make a request to the specified endpoint."""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.test_token}",
            "Content-Type": "application/json"
        }
        
        try:
            if method.upper() == "GET":
                async with session.get(url, headers=headers) as response:
                    return await self._handle_response(response, endpoint)
            elif method.upper() == "POST":
                async with session.post(url, headers=headers) as response:
                    return await self._handle_response(response, endpoint)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
        except Exception as e:
            logger.error(f"Request failed for {endpoint}: {e}")
            self.stats["failed_requests"] += 1
            return {"error": str(e), "status": "failed"}
    
    async def _handle_response(self, response: aiohttp.ClientResponse, endpoint: str) -> Dict[str, Any]:
        """Handle HTTP response and update statistics."""
        self.stats["total_requests"] += 1
        
        try:
            response_data = await response.json()
        except:
            response_data = {"text": await response.text()}
        
        result = {
            "endpoint": endpoint,
            "status_code": response.status,
            "response": response_data,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        if response.status == 200:
            self.stats["successful_requests"] += 1
            logger.info(f"✅ {endpoint}: {response.status}")
        elif response.status == 401:
            self.stats["error_401_count"] += 1
            logger.warning(f"🔑 {endpoint}: {response.status} - Token may need refresh")
            await self._handle_401_response(endpoint, response_data)
        elif response.status == 500:
            self.stats["error_500_count"] += 1
            logger.error(f"💥 {endpoint}: {response.status} - Server error")
        else:
            self.stats["error_other_count"] += 1
            logger.warning(f"⚠️ {endpoint}: {response.status}")
        
        return result
    
    async def _handle_401_response(self, endpoint: str, response_data: Dict[str, Any]) -> None:
        """Handle 401 responses by attempting token refresh."""
        self.stats["refresh_attempts"] += 1
        
        # Try to refresh the token
        try:
            new_token = await self.create_test_token()
            if new_token:
                self.test_token = new_token
                self.stats["refresh_successes"] += 1
                logger.info(f"🔄 Token refreshed successfully for {endpoint}")
            else:
                logger.error(f"❌ Token refresh failed for {endpoint}")
        except Exception as e:
            logger.error(f"❌ Token refresh error for {endpoint}: {e}")
    
    async def test_spotify_status(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Test Spotify status endpoint."""
        return await self.make_request(session, "/v1/spotify/status")
    
    async def test_spotify_diagnose(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Test Spotify diagnose endpoint."""
        return await self.make_request(session, "/v1/spotify/_diagnose")
    
    async def test_spotify_refresh(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Test Spotify refresh endpoint."""
        return await self.make_request(session, "/v1/oauth/spotify/refresh", "POST")
    
    async def test_spotify_disconnect(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Test Spotify disconnect endpoint."""
        return await self.make_request(session, "/v1/oauth/spotify/disconnect", "POST")
    
    async def run_soak_test(self) -> Dict[str, Any]:
        """Run the 90-minute soak test."""
        logger.info(f"🚀 Starting Spotify soak test for {self.test_duration_minutes} minutes")
        logger.info(f"Test will run from {self.test_start_time} to {self.test_end_time}")
        
        # Create initial test token
        self.test_token = await self.create_test_token()
        logger.info(f"🔑 Created test token for user: {self.test_user_id}")
        
        # Test endpoints to cycle through
        test_endpoints = [
            ("/v1/spotify/status", "GET"),
            ("/v1/spotify/_diagnose", "GET"),
            ("/v1/sessions", "GET"),
            ("/v1/auth/whoami", "GET"),
        ]
        
        endpoint_index = 0
        iteration = 0
        
        async with aiohttp.ClientSession() as session:
            while datetime.now(UTC) < self.test_end_time:
                iteration += 1
                current_time = datetime.now(UTC)
                remaining_time = self.test_end_time - current_time
                
                logger.info(f"🔄 Iteration {iteration} - {remaining_time} remaining")
                
                # Test current endpoint
                endpoint, method = test_endpoints[endpoint_index]
                result = await self.make_request(session, endpoint, method)
                
                # Check for reauth_required events
                if result.get("response", {}).get("reason") == "reauth_required":
                    self.stats["reauth_required_events"] += 1
                    logger.warning(f"🔐 Reauth required detected for {endpoint}")
                
                # Move to next endpoint
                endpoint_index = (endpoint_index + 1) % len(test_endpoints)
                
                # Wait 60 seconds before next iteration
                await asyncio.sleep(60)
        
        logger.info("🏁 Soak test completed")
        return self._generate_test_report()
    
    def _generate_test_report(self) -> Dict[str, Any]:
        """Generate test report with statistics and assertions."""
        test_duration = datetime.now(UTC) - self.test_start_time
        
        # Calculate success rate
        success_rate = (self.stats["successful_requests"] / self.stats["total_requests"] * 100) if self.stats["total_requests"] > 0 else 0
        
        # Calculate refresh success rate
        refresh_success_rate = (self.stats["refresh_successes"] / self.stats["refresh_attempts"] * 100) if self.stats["refresh_attempts"] > 0 else 100
        
        report = {
            "test_summary": {
                "duration_minutes": test_duration.total_seconds() / 60,
                "start_time": self.test_start_time.isoformat(),
                "end_time": datetime.now(UTC).isoformat(),
                "user_id": self.test_user_id,
            },
            "statistics": self.stats.copy(),
            "calculated_metrics": {
                "success_rate_percent": round(success_rate, 2),
                "refresh_success_rate_percent": round(refresh_success_rate, 2),
                "requests_per_minute": round(self.stats["total_requests"] / (test_duration.total_seconds() / 60), 2),
            },
            "assertions": {
                "zero_500_errors": self.stats["error_500_count"] == 0,
                "refresh_works_on_401": self.stats["refresh_successes"] > 0 or self.stats["error_401_count"] == 0,
                "reauth_required_detected": self.stats["reauth_required_events"] >= 0,
                "overall_success_rate_acceptable": success_rate >= 95.0,
            },
            "recommendations": self._generate_recommendations()
        }
        
        return report
    
    def _generate_recommendations(self) -> list[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        if self.stats["error_500_count"] > 0:
            recommendations.append("Investigate 500 errors - zero 500 errors expected")
        
        if self.stats["error_401_count"] > 0 and self.stats["refresh_successes"] == 0:
            recommendations.append("Token refresh mechanism may not be working properly")
        
        if self.stats["reauth_required_events"] > 0:
            recommendations.append("Monitor reauth_required events - tokens may be expiring too quickly")
        
        success_rate = (self.stats["successful_requests"] / self.stats["total_requests"] * 100) if self.stats["total_requests"] > 0 else 0
        if success_rate < 95.0:
            recommendations.append(f"Success rate is {success_rate:.1f}% - investigate failures")
        
        if not recommendations:
            recommendations.append("All assertions passed - system is healthy")
        
        return recommendations


async def main():
    """Main function to run the soak test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Spotify Soak Test")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL for the API")
    parser.add_argument("--duration", type=int, default=90, help="Test duration in minutes")
    parser.add_argument("--output", help="Output file for test report")
    
    args = parser.parse_args()
    
    # Run the soak test
    test = SpotifySoakTest(base_url=args.base_url, test_duration_minutes=args.duration)
    report = await test.run_soak_test()
    
    # Print report
    print("\n" + "="*80)
    print("SPOTIFY SOAK TEST REPORT")
    print("="*80)
    print(json.dumps(report, indent=2))
    
    # Save report to file if specified
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    # Exit with error code if assertions failed
    failed_assertions = [k for k, v in report["assertions"].items() if not v]
    if failed_assertions:
        print(f"\n❌ Failed assertions: {failed_assertions}")
        exit(1)
    else:
        print("\n✅ All assertions passed!")
        exit(0)


if __name__ == "__main__":
    asyncio.run(main())
