from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductionStartupConfigTest(unittest.TestCase):
    def test_root_start_stop_scripts_exist_and_use_compose(self) -> None:
        start_script = ROOT / "scripts" / "start.sh"
        stop_script = ROOT / "scripts" / "stop.sh"
        start_ps1 = ROOT / "scripts" / "start.ps1"
        stop_ps1 = ROOT / "scripts" / "stop.ps1"

        self.assertTrue(start_script.exists())
        self.assertTrue(stop_script.exists())
        self.assertTrue(start_ps1.exists())
        self.assertTrue(stop_ps1.exists())
        start_text = start_script.read_text(encoding="utf-8")
        self.assertIn("docker compose up -d", start_text)
        self.assertIn("--wait", start_text)
        self.assertIn("docker compose down", stop_script.read_text(encoding="utf-8"))
        self.assertIn("docker compose up -d", start_ps1.read_text(encoding="utf-8"))

    def test_api_container_is_typescript(self) -> None:
        dockerfile = (ROOT / "backend" / "api-ts" / "Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("FROM node:22-alpine", dockerfile)
        self.assertIn('CMD ["pnpm", "start"]', dockerfile)
        self.assertIn("context: ./backend/api-ts", compose)
        self.assertIn("fetch('http://127.0.0.1:8000/api/status')", compose)

    def test_sandbox_container_is_typescript(self) -> None:
        dockerfile = (ROOT / "backend" / "sandbox-ts" / "Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("FROM node:22-bookworm-slim", dockerfile)
        self.assertIn("context: ./backend/sandbox-ts", compose)
        self.assertIn("fetch('http://127.0.0.1:8100/api/status')", compose)

    def test_nginx_has_stream_websocket_and_upload_rules(self) -> None:
        config = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")

        self.assertIn("proxy_read_timeout", config)
        self.assertIn("X-Accel-Buffering", config)
        self.assertIn("location /sandbox-vnc/", config)
        self.assertIn("proxy_set_header Upgrade $http_upgrade", config)
        self.assertIn("auth_request /_atlas_auth", config)
        self.assertIn("location /uploads/", config)
        self.assertIn('add_header X-Content-Type-Options "nosniff"', config)

    def test_compose_passes_rag_env_and_uses_busybox_wget(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("env_file:", compose)
        self.assertIn("RAG_VECTOR_BACKEND", compose)
        self.assertIn("QDRANT_URL", compose)
        self.assertIn("wget -qO- http://127.0.0.1/", compose)
        self.assertNotIn("wget --spider", compose)

    def test_compose_uses_loopback_auth_and_durable_redis_policy(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("${NGINX_HOST:-127.0.0.1}:${NGINX_PORT:-8088}:80", compose)
        self.assertIn("API_AUTH_ENABLED", compose)
        self.assertIn("SANDBOX_AUTH_ENABLED", compose)
        self.assertIn("--maxmemory-policy noeviction", compose)

    def test_quickstart_is_node_and_needs_no_external_services(self) -> None:
        script = (ROOT / "scripts" / "quickstart-ts.mjs").read_text(encoding="utf-8")
        self.assertIn("backend", script)
        self.assertIn("api-ts", script)
        self.assertIn("pnpm", script)
        self.assertNotIn("docker compose", script)
        self.assertNotIn("uvicorn", script)


if __name__ == "__main__":
    unittest.main()
