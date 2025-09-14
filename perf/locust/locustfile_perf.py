import os

from locust import HttpUser, between, events, task

SLO_P95_MS = int(os.getenv("LOCUST_SLO_P95_MS", "500"))


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):  # type: ignore
    try:
        p95 = environment.stats.total.get_response_time_percentile(0.95)
        if p95 and p95 > SLO_P95_MS:
            environment.process_exit_code = 1
            print(f"SLO breach: p95={p95:.0f}ms > {SLO_P95_MS}ms")
    except Exception:
        pass


class SmokeUser(HttpUser):
    wait_time = between(0.5, 1.5)

    @task(2)
    def health(self):
        r = self.client.get("/v1/healthz")
        assert r.status_code == 200

    @task(1)
    def status_features(self):
        self.client.get("/v1/status/features")
