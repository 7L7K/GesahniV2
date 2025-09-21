"""
Metrics API endpoints for monitoring and observability.
"""

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse
from app.metrics.auth_metrics import get_metrics, get_metrics_summary, get_prometheus_metrics

router = APIRouter(prefix="/v1/metrics", tags=["Metrics"])


@router.get("/auth")
async def get_auth_metrics():
    """
    Get authentication metrics in JSON format.
    
    Returns:
        Dictionary containing current authentication metrics
    """
    return get_metrics()


@router.get("/auth/summary")
async def get_auth_metrics_summary():
    """
    Get authentication metrics summary for health checks.
    
    Returns:
        Dictionary containing metrics summary with health status
    """
    return get_metrics_summary()


@router.get("/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics_endpoint():
    """
    Get metrics in Prometheus format for external monitoring systems.
    
    Returns:
        Prometheus-formatted metrics string
    """
    return get_prometheus_metrics()


@router.get("/health")
async def get_health_status():
    """
    Get overall health status based on metrics.
    
    Returns:
        Dictionary containing health status and recommendations
    """
    summary = get_metrics_summary()
    
    # Determine overall health status
    overall_status = "healthy"
    issues = []
    
    if summary["legacy_resolutions"]["status"] != "healthy":
        overall_status = "warning"
        issues.append("Legacy sub resolutions detected")
    
    if summary["db_coercion_failures"]["status"] != "healthy":
        overall_status = "error"
        issues.append("Database UUID coercion failures detected")
    
    if summary["spotify_refresh_failures"]["status"] != "healthy":
        overall_status = "warning"
        issues.append("Spotify refresh failures detected")
    
    return {
        "status": overall_status,
        "issues": issues,
        "metrics": summary,
        "recommendations": _get_recommendations(summary)
    }


def _get_recommendations(summary: dict) -> list[str]:
    """Get recommendations based on current metrics."""
    recommendations = []
    
    if summary["legacy_resolutions"]["total"] > 0:
        recommendations.append("Monitor legacy sub resolutions and plan for sunset")
    
    if summary["db_coercion_failures"]["total"] > 0:
        recommendations.append("Investigate database UUID coercion failures immediately")
    
    if summary["spotify_refresh_failures"]["total"] > 0:
        recommendations.append("Check Spotify API status and token validity")
    
    if summary["token_operations"]["encrypt_bytes"] == 0 and summary["token_operations"]["decrypt_bytes"] == 0:
        recommendations.append("No token operations detected - verify token usage")
    
    return recommendations