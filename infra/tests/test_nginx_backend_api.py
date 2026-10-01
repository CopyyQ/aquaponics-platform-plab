from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


def service_block(compose_text: str, service_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service_name)}:\n(.*?)(?=^  [A-Za-z0-9_]+:\n|^volumes:\n|\Z)",
        compose_text,
    )
    if match is None:
        raise AssertionError(f"service {service_name!r} is missing")
    return match.group(1)


class NginxBackendApiInfrastructureTest(unittest.TestCase):
    def assert_compose_uses_api_gateway(self, compose_name: str) -> None:
        compose_text = (ROOT / compose_name).read_text(encoding="utf-8")
        backend = service_block(compose_text, "backend")
        gateway = service_block(compose_text, "api_gateway")

        self.assertNotIn('"8000:8000"', backend)
        self.assertIn('"8000"', backend)
        self.assertIn("image: nginx:1.27-alpine", gateway)
        self.assertIn('"8000:80"', gateway)
        self.assertIn(
            "./infra/nginx/backend-api.conf:/etc/nginx/conf.d/default.conf:ro",
            gateway,
        )
        self.assertRegex(
            gateway,
            r"(?ms)depends_on:\s+backend:\s+condition: service_healthy",
        )

    def test_root_compose_routes_public_backend_port_through_nginx(self) -> None:
        self.assert_compose_uses_api_gateway("docker-compose.yml")

    def test_local_compose_routes_public_backend_port_through_nginx(self) -> None:
        self.assert_compose_uses_api_gateway("docker-compose.local.yml")

    def test_nginx_proxies_backend_paths_and_forwarded_headers(self) -> None:
        config_path = ROOT / "infra" / "nginx" / "backend-api.conf"
        self.assertTrue(config_path.is_file(), "backend API Nginx config is missing")
        config = config_path.read_text(encoding="utf-8")

        self.assertIn("upstream backend_api {", config)
        self.assertIn("server backend:8000;", config)
        self.assertIn("keepalive 256;", config)
        self.assertIn("location / {", config)
        self.assertIn("proxy_pass http://backend_api;", config)
        self.assertIn('proxy_set_header Connection "";', config)
        self.assertIn("proxy_set_header Host $host;", config)
        self.assertIn("proxy_set_header X-Real-IP $remote_addr;", config)
        self.assertIn(
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            config,
        )
        self.assertIn("proxy_set_header X-Forwarded-Proto $scheme;", config)


if __name__ == "__main__":
    unittest.main()
