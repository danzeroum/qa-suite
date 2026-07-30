"""Carga real com Locust: throughput, latência por percentil e erros sob usuários simultâneos.

Uso:
    locust -f loadtest/locustfile.py --host https://alvo.com
    # ou sem UI:
    locust -f loadtest/locustfile.py --host https://alvo.com --headless -u 50 -r 5 -t 2m

Riscos (gerenciamento de riscos): rode SOMENTE contra ambientes que você
tem autorização para testar; carga em produção de terceiros pode ser ilegal.
"""
from locust import HttpUser, between, task


class Visitante(HttpUser):
    wait_time = between(1, 3)

    @task(5)
    def home(self):
        self.client.get("/", name="home")

    @task(2)
    def recurso_estatico(self):
        self.client.get("/favicon.ico", name="favicon", catch_response=True)

    @task(1)
    def rota_inexistente(self):
        # tratamento de erro sob carga também é requisito de qualidade
        with self.client.get("/webqa-404-load", name="404", catch_response=True) as resp:
            if resp.status_code in (404, 410):
                resp.success()
