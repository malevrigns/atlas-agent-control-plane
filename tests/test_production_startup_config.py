from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductionStartupConfigTest(unittest.TestCase):
    def test_root_start_stop_scripts_exist_and_use_compose(self) -> None:
        start_script = ROOT / "scripts" / "start.sh"
        stop_script = ROOT / "scripts" / "stop.sh"

        self.assertTrue(start_script.exists())
        self.assertTrue(stop_script.exists())
        self.assertIn("docker compose up -d", start_script.read_text())
        self.assertIn("docker compose down", stop_script.read_text())

    def test_api_container_runs_start_script_with_migrations(self) -> None:
        dockerfile = (ROOT / "api" / "Dockerfile").read_text()
        start_script = (ROOT / "api" / "scripts" / "start.sh").read_text()

        self.assertIn("COPY scripts ./scripts", dockerfile)
        self.assertIn('CMD ["./scripts/start.sh"]', dockerfile)
        self.assertIn("alembic upgrade head", start_script)
        self.assertIn("uvicorn app.main:app", start_script)

    def test_nginx_has_stream_websocket_and_upload_rules(self) -> None:
        config = (ROOT / "nginx" / "default.conf").read_text()

        self.assertIn("proxy_read_timeout", config)
        self.assertIn("X-Accel-Buffering", config)
        self.assertIn("location /sandbox-vnc/", config)
        self.assertIn("proxy_set_header Upgrade $http_upgrade", config)
        self.assertIn("auth_request /_atlas_auth", config)
        self.assertIn("location /uploads/", config)
        self.assertIn('add_header X-Content-Type-Options "nosniff"', config)

    def test_compose_uses_loopback_auth_and_durable_redis_policy(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text()

        self.assertIn("${NGINX_HOST:-127.0.0.1}:${NGINX_PORT:-8088}:80", compose)
        self.assertIn("API_AUTH_ENABLED", compose)
        self.assertIn("SANDBOX_AUTH_ENABLED", compose)
        self.assertIn("--maxmemory-policy noeviction", compose)


if __name__ == "__main__":
    unittest.main()
