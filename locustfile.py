from locust import HttpUser, between, task


class APISmokeUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(2)
    def health(self):
        r = self.client.get("/healthz")
        assert r.status_code == 200

    @task(2)
    def me(self):
        r = self.client.get("/v1/me")
        assert r.status_code == 200

    @task(1)
    def ask(self):
        r = self.client.post("/v1/ask", json={"prompt": "hello"})
        assert r.status_code in (200, 400, 401, 500)


