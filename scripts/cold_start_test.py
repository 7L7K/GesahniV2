#!/usr/bin/env python3
"""
Cold Start / Redeploy Test

This script tests that resolvers and token crypto don't depend on lazy imports
or missing environment variables during cold starts and redeploys.
"""

import asyncio
import aiohttp
import json
import time
import logging
from datetime import datetime, UTC
from typing import Dict, Any, List
import subprocess
import signal
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ColdStartTest:
    """Cold start and redeploy test."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_results = []
        
    async def test_endpoint_availability(self, session: aiohttp.ClientSession, endpoint: str, expected_status: int = 200) -> Dict[str, Any]:
        """Test that an endpoint is available and returns expected status."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with session.get(url) as response:
                result = {
                    "endpoint": endpoint,
                    "status_code": response.status,
                    "expected_status": expected_status,
                    "available": response.status == expected_status,
                    "timestamp": datetime.now(UTC).isoformat()
                }
                
                if response.status == expected_status:
                    logger.info(f"✅ {endpoint}: {response.status}")
                else:
                    logger.warning(f"⚠️ {endpoint}: {response.status} (expected {expected_status})")
                
                return result
                
        except Exception as e:
            result = {
                "endpoint": endpoint,
                "status_code": None,
                "expected_status": expected_status,
                "available": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat()
            }
            logger.error(f"❌ {endpoint}: {e}")
            return result
    
    async def test_jwt_token_creation(self) -> Dict[str, Any]:
        """Test JWT token creation after cold start."""
        try:
            from app.tokens import make_access
            from app.auth.jwt import build_claims
            
            # Test token creation with legacy username
            legacy_username = "cold_start_test"
            token = make_access({"user_id": legacy_username})
            
            # Test claims building
            claims = build_claims(legacy_username)
            
            result = {
                "test": "jwt_token_creation",
                "success": True,
                "token_created": bool(token),
                "claims_created": bool(claims),
                "sub_is_uuid": len(claims.get("sub", "")) == 36,
                "timestamp": datetime.now(UTC).isoformat()
            }
            
            logger.info("✅ JWT token creation: Success")
            return result
            
        except Exception as e:
            result = {
                "test": "jwt_token_creation",
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat()
            }
            logger.error(f"❌ JWT token creation: {e}")
            return result
    
    async def test_uuid_resolution(self) -> Dict[str, Any]:
        """Test UUID resolution after cold start."""
        try:
            from app.util.ids import to_uuid
            
            # Test resolution with legacy username
            legacy_username = "cold_start_test"
            resolved_uuid = str(to_uuid(legacy_username))
            
            result = {
                "test": "uuid_resolution",
                "success": True,
                "resolved_uuid": resolved_uuid,
                "is_valid_uuid": len(resolved_uuid) == 36,
                "timestamp": datetime.now(UTC).isoformat()
            }
            
            logger.info("✅ UUID resolution: Success")
            return result
            
        except Exception as e:
            result = {
                "test": "uuid_resolution",
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat()
            }
            logger.error(f"❌ UUID resolution: {e}")
            return result
    
    async def test_database_connection(self) -> Dict[str, Any]:
        """Test database connection after cold start."""
        try:
            from app.db.database import get_async_db
            
            async with get_async_db() as session:
                # Simple query to test connection
                result = await session.execute("SELECT 1")
                row = result.fetchone()
                
                result = {
                    "test": "database_connection",
                    "success": True,
                    "query_result": row[0] if row else None,
                    "timestamp": datetime.now(UTC).isoformat()
                }
                
                logger.info("✅ Database connection: Success")
                return result
                
        except Exception as e:
            result = {
                "test": "database_connection",
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat()
            }
            logger.error(f"❌ Database connection: {e}")
            return result
    
    async def test_environment_variables(self) -> Dict[str, Any]:
        """Test that required environment variables are available."""
        required_vars = [
            "JWT_SECRET",
            "DATABASE_URL",
            "OPENAI_API_KEY",
        ]
        
        missing_vars = []
        available_vars = []
        
        for var in required_vars:
            if os.getenv(var):
                available_vars.append(var)
            else:
                missing_vars.append(var)
        
        result = {
            "test": "environment_variables",
            "success": len(missing_vars) == 0,
            "required_variables": required_vars,
            "available_variables": available_vars,
            "missing_variables": missing_vars,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        if result["success"]:
            logger.info("✅ Environment variables: All required variables available")
        else:
            logger.warning(f"⚠️ Environment variables: Missing {missing_vars}")
        
        return result
    
    async def test_import_dependencies(self) -> Dict[str, Any]:
        """Test that all required modules can be imported."""
        required_modules = [
            "app.tokens",
            "app.auth.jwt",
            "app.util.ids",
            "app.db.database",
            "app.metrics.auth_metrics",
        ]
        
        import_results = {}
        failed_imports = []
        
        for module in required_modules:
            try:
                __import__(module)
                import_results[module] = "success"
            except Exception as e:
                import_results[module] = f"failed: {e}"
                failed_imports.append(module)
        
        result = {
            "test": "import_dependencies",
            "success": len(failed_imports) == 0,
            "import_results": import_results,
            "failed_imports": failed_imports,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        if result["success"]:
            logger.info("✅ Import dependencies: All modules imported successfully")
        else:
            logger.error(f"❌ Import dependencies: Failed to import {failed_imports}")
        
        return result
    
    async def run_cold_start_test(self) -> Dict[str, Any]:
        """Run the cold start test."""
        logger.info("🚀 Starting cold start / redeploy test")
        
        # Test 1: Environment variables
        env_test = await self.test_environment_variables()
        self.test_results.append(env_test)
        
        # Test 2: Import dependencies
        import_test = await self.test_import_dependencies()
        self.test_results.append(import_test)
        
        # Test 3: UUID resolution
        uuid_test = await self.test_uuid_resolution()
        self.test_results.append(uuid_test)
        
        # Test 4: JWT token creation
        jwt_test = await self.test_jwt_token_creation()
        self.test_results.append(jwt_test)
        
        # Test 5: Database connection
        db_test = await self.test_database_connection()
        self.test_results.append(db_test)
        
        # Test 6: API endpoints (if server is running)
        try:
            async with aiohttp.ClientSession() as session:
                # Test health endpoint
                health_test = await self.test_endpoint_availability(session, "/health", 200)
                self.test_results.append(health_test)
                
                # Test metrics endpoint
                metrics_test = await self.test_endpoint_availability(session, "/v1/metrics/auth", 200)
                self.test_results.append(metrics_test)
                
        except Exception as e:
            logger.warning(f"⚠️ API endpoint tests skipped: {e}")
            self.test_results.append({
                "test": "api_endpoints",
                "success": False,
                "error": f"Server not available: {e}",
                "timestamp": datetime.now(UTC).isoformat()
            })
        
        return self._generate_test_report()
    
    def _generate_test_report(self) -> Dict[str, Any]:
        """Generate test report."""
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results if result.get("success", False))
        failed_tests = total_tests - successful_tests
        
        report = {
            "test_summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "success_rate": (successful_tests / total_tests * 100) if total_tests > 0 else 0,
                "timestamp": datetime.now(UTC).isoformat()
            },
            "test_results": self.test_results,
            "assertions": {
                "all_imports_successful": all(r.get("success", False) for r in self.test_results if r.get("test") == "import_dependencies"),
                "environment_variables_available": all(r.get("success", False) for r in self.test_results if r.get("test") == "environment_variables"),
                "uuid_resolution_works": all(r.get("success", False) for r in self.test_results if r.get("test") == "uuid_resolution"),
                "jwt_creation_works": all(r.get("success", False) for r in self.test_results if r.get("test") == "jwt_token_creation"),
                "database_connection_works": all(r.get("success", False) for r in self.test_results if r.get("test") == "database_connection"),
            },
            "recommendations": self._generate_recommendations()
        }
        
        return report
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        for result in self.test_results:
            if not result.get("success", False):
                test_name = result.get("test", "unknown")
                error = result.get("error", "unknown error")
                recommendations.append(f"Fix {test_name}: {error}")
        
        if not recommendations:
            recommendations.append("All cold start tests passed - system is ready for deployment")
        
        return recommendations


async def main():
    """Main function to run the cold start test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cold Start / Redeploy Test")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL for the API")
    parser.add_argument("--output", help="Output file for test report")
    
    args = parser.parse_args()
    
    # Run the cold start test
    test = ColdStartTest(base_url=args.base_url)
    report = await test.run_cold_start_test()
    
    # Print report
    print("\n" + "="*80)
    print("COLD START / REDEPLOY TEST REPORT")
    print("="*80)
    print(json.dumps(report, indent=2))
    
    # Save report to file if specified
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    # Exit with error code if any tests failed
    if report["test_summary"]["failed_tests"] > 0:
        print(f"\n❌ {report['test_summary']['failed_tests']} tests failed")
        exit(1)
    else:
        print("\n✅ All cold start tests passed!")
        exit(0)


if __name__ == "__main__":
    asyncio.run(main())
