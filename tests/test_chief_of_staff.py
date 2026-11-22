#!/usr/bin/env python3
"""
test_chief_of_staff.py - Suite determinista unittest (stdlib puro) para Chief of Staff.
Valida view_tokens.py, verify_handoff.py, memory_search.py, consult_council.py e install.sh
en directorios temporales aislados, sin depender de agy instalado ni de ~/.gemini real.
"""
from datetime import datetime, timedelta, timezone
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "skills", "chief-of-staff-ops", "scripts")
INSTALL_SH = os.path.join(REPO_ROOT, "install.sh")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import consult_council  # noqa: E402
import memory_search  # noqa: E402
import verify_handoff  # noqa: E402
import view_tokens  # noqa: E402


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestViewTokens(unittest.TestCase):
    """Pruebas para view_tokens.py: filtros temporales, no doble conteo y multi-familia."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.metrics_path = os.path.join(self.tmpdir.name, "metrics.jsonl")
        self.quota_file = os.path.join(self.tmpdir.name, "quota_budget.json")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_temporal_filters_and_multi_family(self) -> None:
        now = datetime.now(timezone.utc)
        entries = [
            {
                "ts": _iso_utc(now - timedelta(hours=2)),
                "script": "consult_council.py",
                "alias": "claude",
                "model": "claude-sonnet-5-5-high",
                "duration_s": 1.2,
                "status": "OK",
                "exit_code": 0,
                "usage": {
                    "input_tokens": 50_000,
                    "output_tokens": 50_000,
                    "thinking_tokens": 0,
                    "cache_read_tokens": 0,
                    "total_tokens": 100_000,
                },
            },
            {
                "ts": _iso_utc(now - timedelta(days=3)),
                "script": "consult_council.py",
                "alias": "argon",
                "model": "gemini-4-argon-high",
                "duration_s": 2.0,
                "status": "OK",
                "exit_code": 0,
                "usage": {
                    "input_tokens": 100_000,
                    "output_tokens": 100_000,
                    "thinking_tokens": 0,
                    "cache_read_tokens": 0,
                    "total_tokens": 200_000,
                },
            },
            {
                "ts": _iso_utc(now - timedelta(days=5)),
                "script": "consult_council.py",
                "alias": "hydrogen",
                "model": "gemini-4-hydrogen-high",
                "duration_s": 1.5,
                "status": "OK",
                "exit_code": 0,
                "usage": {
                    "input_tokens": 40_000,
                    "output_tokens": 40_000,
                    "thinking_tokens": 0,
                    "cache_read_tokens": 0,
                    "total_tokens": 80_000,
                },
            },
            {
                "ts": _iso_utc(now - timedelta(days=10)),
                "script": "consult_council.py",
                "alias": "gpt",
                "model": "gpt-oss-120b-medium",
                "duration_s": 0.9,
                "status": "OK",
                "exit_code": 0,
                "usage": {
                    "input_tokens": 25_000,
                    "output_tokens": 25_000,
                    "thinking_tokens": 0,
                    "cache_read_tokens": 0,
                    "total_tokens": 50_000,
                },
            },
        ]
        with open(self.metrics_path, "w", encoding="utf-8") as f:
            for item in entries:
                f.write(json.dumps(item) + "\n")

        rec_1d = view_tokens.load_council_records(self.metrics_path, since_dt=now - timedelta(days=1))
        self.assertEqual(len(rec_1d), 1)
        sum_1d = view_tokens.aggregate_records(rec_1d)
        self.assertEqual(sum_1d["totals"]["total_tokens"], 100_000)

        rec_7d = view_tokens.load_council_records(self.metrics_path, since_dt=now - timedelta(days=7))
        self.assertEqual(len(rec_7d), 3)
        sum_7d = view_tokens.aggregate_records(rec_7d)
        self.assertEqual(sum_7d["totals"]["total_tokens"], 380_000)
        fams_7d = {f["family"]: f["total_tokens"] for f in sum_7d["families"]}
        self.assertEqual(fams_7d["Claude 5.5"], 100_000)
        self.assertEqual(fams_7d["Argon 4"], 200_000)
        self.assertEqual(fams_7d["Gemini Heavy"], 80_000)
        self.assertNotIn("GPT-OSS", fams_7d)

    def test_no_double_counting_between_metrics_and_transcripts(self) -> None:
        now = datetime.now(timezone.utc)
        rec = [
            {
                "ts": _iso_utc(now - timedelta(hours=1)),
                "script": "consult_council.py",
                "alias": "claude",
                "model": "claude-sonnet-5-5-high",
                "duration_s": 1.0,
                "status": "OK",
                "exit_code": 0,
                "usage": {"input_tokens": 60_000, "output_tokens": 60_000, "total_tokens": 120_000},
            }
        ]
        summary = view_tokens.aggregate_records(rec)
        fake_audit = {
            "sessions_scanned": 2,
            "subagent_invocations": 1,
            "subagents": [],
            "council_calls": 1,
            "council_by_model": {"claude": 1},
            "family_tokens": {
                "Claude 5.5": {"input_tokens": 500_000, "output_tokens": 400_000, "total_tokens": 900_000},
                "Gemini Flash": {"input_tokens": 20_000, "output_tokens": 30_000, "total_tokens": 50_000},
                "Other": {"input_tokens": 15_000, "output_tokens": 25_000, "total_tokens": 40_000},
            },
        }
        report = view_tokens.compute_quota_report(summary, fake_audit, 7, self.quota_file)
        by_fam = {r["family"]: r for r in report["families"]}
        # Claude 5.5 es council_truth_family: usa exactamente council_tokens (120k), sin sumar transcript_tokens (900k)
        self.assertEqual(by_fam["Claude 5.5"]["used_tokens"], 120_000)
        self.assertEqual(by_fam["Gemini Flash"]["used_tokens"], 50_000)
        # Other se reporta aparte como unlabeled_ide_tokens
        self.assertEqual(report["unlabeled_ide_tokens"], 40_000)


class TestVerifyHandoff(unittest.TestCase):
    """Pruebas para verify_handoff.py: AST OK/FAIL y escaneo de secretos."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_ast_syntax_ok_and_fail(self) -> None:
        ok_py = os.path.join(self.tmpdir.name, "valid_mod.py")
        bad_py = os.path.join(self.tmpdir.name, "broken_mod.py")
        with open(ok_py, "w", encoding="utf-8") as f:
            f.write("def add(a: int, b: int) -> int:\n    return a + b\n")
        with open(bad_py, "w", encoding="utf-8") as f:
            f.write("def broken(:\n    pass\n")

        status_ok, _ = verify_handoff.check_syntax(ok_py)
        status_bad, msg_bad = verify_handoff.check_syntax(bad_py)
        self.assertEqual(status_ok, "OK")
        self.assertEqual(status_bad, "FAIL")
        self.assertIn("sintaxis", msg_bad.lower())

    def test_secret_scan_detects_fake_key_and_ignores_example(self) -> None:
        fake_key = "AIza" + ("X" * 24)
        leak_file = os.path.join(self.tmpdir.name, "config_real.py")
        example_file = os.path.join(self.tmpdir.name, "config.py.example")

        with open(leak_file, "w", encoding="utf-8") as f:
            f.write(f'API_KEY = "{fake_key}"\n')
        with open(example_file, "w", encoding="utf-8") as f:
            f.write(f'API_KEY = "{fake_key}"\n')

        findings_leak = verify_handoff.scan_secrets(leak_file)
        findings_example = verify_handoff.scan_secrets(example_file)
        self.assertEqual(len(findings_leak), 1)
        self.assertIn("Google API Key", findings_leak[0])
        self.assertEqual(findings_example, [])


class TestMemorySearch(unittest.TestCase):
    """Pruebas para memory_search.py: FTS5 en :memory: sobre tmpdir."""

    def test_fts5_search_on_tmpdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mem_dir = os.path.join(tmp, "memory")
            os.makedirs(mem_dir, exist_ok=True)
            with open(os.path.join(tmp, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write("# Índice de Memoria\n\n- Proyecto Demo y servicio Cache.\n")
            with open(os.path.join(mem_dir, "ficha_cache.md"), "w", encoding="utf-8") as f:
                f.write(
                    "# Servicio Cache Interno\n"
                    "Confidence: 0.95\n\n"
                    "El worker corre en 10.0.0.10 puerto 6379 con motor cache_engine.\n"
                )

            report = memory_search.search_memory(tmp, "cache_engine", top_k=5)
            self.assertEqual(report["files_indexed"], 2)
            self.assertGreaterEqual(len(report["results"]), 1)
            top = report["results"][0]
            self.assertIn("ficha_cache.md", top["path"])
            self.assertEqual(top["confidence"], "0.95")
            self.assertIn("cache_engine", top["snippet"])


class TestConsultCouncil(unittest.TestCase):
    """Pruebas para consult_council.py: --check-env, COS_PROFILE=lite, -m auto --dry-run-route y fallback."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.metrics_path = os.path.join(self.tmpdir.name, "metrics.jsonl")
        self.quota_file = os.path.join(self.tmpdir.name, "quota_budget.json")
        self.script_path = os.path.join(SCRIPTS_DIR, "consult_council.py")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _base_env(self, extra: dict | None = None) -> dict:
        env = os.environ.copy()
        env["COS_METRICS_PATH"] = self.metrics_path
        env["COS_QUOTA_FILE"] = self.quota_file
        env.pop("COS_PROFILE", None)
        if extra:
            env.update(extra)
        return env

    def test_check_env_and_student_lite_mode(self) -> None:
        res_check = subprocess.run(
            [sys.executable, self.script_path, "--check-env"],
            capture_output=True,
            text=True,
            env=self._base_env({"COS_PROFILE": "lite"}),
        )
        self.assertEqual(res_check.returncode, 0)
        info = json.loads(res_check.stdout.strip())
        self.assertEqual(info["mode"], "student-lite")
        self.assertEqual(info["cos_profile"], "lite")

        res_lite = subprocess.run(
            [sys.executable, self.script_path, "-p", "hola"],
            capture_output=True,
            text=True,
            env=self._base_env({"COS_PROFILE": "lite"}),
        )
        self.assertEqual(res_lite.returncode, 2)
        self.assertIn("Modo Student Lite", res_lite.stdout)

    def test_auto_dry_run_route_rotates_when_claude_saturated(self) -> None:
        # 1) Sin uso previo: tarea 'code' (default) elige 'claude'
        res_fresh = subprocess.run(
            [sys.executable, self.script_path, "-m", "auto", "--dry-run-route"],
            capture_output=True,
            text=True,
            env=self._base_env(),
        )
        self.assertEqual(res_fresh.returncode, 0)
        route_fresh = json.loads(res_fresh.stdout.strip())
        self.assertEqual(route_fresh["task"], "code")
        self.assertEqual(route_fresh["selected_alias"], "claude")
        self.assertEqual(route_fresh["selected_model"], "claude-sonnet-5-5-high")

        # 2) Inferencia desde --agent mentor-architect -> task 'plan' -> elige 'argon'
        res_plan = subprocess.run(
            [sys.executable, self.script_path, "-m", "auto", "--agent", "mentor-architect", "--dry-run-route"],
            capture_output=True,
            text=True,
            env=self._base_env(),
        )
        self.assertEqual(res_plan.returncode, 0)
        route_plan = json.loads(res_plan.stdout.strip())
        self.assertEqual(route_plan["task"], "plan")
        self.assertEqual(route_plan["selected_alias"], "argon")

        # 3) Saturar Claude >=85% en ventana 1d (270k / 300k = 90.0%)
        now = datetime.now(timezone.utc)
        with open(self.metrics_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "ts": _iso_utc(now - timedelta(hours=1)),
                    "script": "consult_council.py",
                    "alias": "claude",
                    "model": "claude-sonnet-5-5-high",
                    "duration_s": 2.5,
                    "status": "OK",
                    "exit_code": 0,
                    "usage": {"input_tokens": 135_000, "output_tokens": 135_000, "total_tokens": 270_000},
                })
                + "\n"
            )

        res_rot = subprocess.run(
            [sys.executable, self.script_path, "-m", "auto", "--dry-run-route"],
            capture_output=True,
            text=True,
            env=self._base_env(),
        )
        self.assertEqual(res_rot.returncode, 0)
        route_rot = json.loads(res_rot.stdout.strip())
        self.assertEqual(route_rot["task"], "code")
        self.assertEqual(route_rot["selected_alias"], "argon")
        self.assertEqual(route_rot["selected_model"], "gemini-4-argon-high")
        self.assertEqual(route_rot["candidates"], ["claude", "argon", "hydrogen", "neon", "flash"])
        self.assertIn("claude", route_rot["reason"])

    def test_auto_fallback_on_429_with_fake_agy(self) -> None:
        bin_dir = os.path.join(self.tmpdir.name, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        fake_agy = os.path.join(bin_dir, "agy")
        with open(fake_agy, "w", encoding="utf-8") as f:
            f.write(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "args = sys.argv[1:]\n"
                "model = args[args.index('--model') + 1] if '--model' in args else ''\n"
                "if 'claude' in model:\n"
                "    sys.stderr.write('HTTP 429 rate limit: quota exhausted\\n')\n"
                "    sys.exit(1)\n"
                "print(json.dumps({\n"
                "    'response': 'Respuesta desde fallback Argon',\n"
                "    'status': 'SUCCESS',\n"
                "    'duration_seconds': 0.2,\n"
                "    'usage': {'input_tokens': 12, 'output_tokens': 8, 'total_tokens': 20}\n"
                "}))\n"
            )
        os.chmod(fake_agy, os.stat(fake_agy).st_mode | stat.S_IEXEC)

        out_file = os.path.join(self.tmpdir.name, "out.md")
        env = self._base_env({"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"})
        res = subprocess.run(
            [sys.executable, self.script_path, "-m", "auto", "-p", "test fallback", "-o", out_file],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("Respuesta desde fallback Argon", res.stdout)
        with open(self.metrics_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["alias"], "argon")
        self.assertEqual(records[0]["fallback_from"], "claude")


class TestInstallSh(unittest.TestCase):
    """Pruebas para install.sh: --copy --init-config --doctor en tmpdir aislado."""

    def test_install_copy_init_config_doctor_and_idempotence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gemini_home = os.path.join(tmp, "gemini_home")
            cos_target = os.path.join(tmp, "cos_target")
            env = os.environ.copy()
            env["GEMINI_HOME"] = gemini_home
            env["COS_TARGET"] = cos_target

            res = subprocess.run(
                ["bash", INSTALL_SH, "--copy", "--init-config", "--doctor"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertTrue(os.path.isfile(os.path.join(gemini_home, "GEMINI.md")))
            self.assertTrue(os.path.isfile(os.path.join(cos_target, "MEMORY.md")))
            self.assertTrue(os.path.isfile(os.path.join(cos_target, "mcp_config.json")))
            self.assertTrue(os.path.isfile(os.path.join(cos_target, "quota_budget.json")))
            self.assertTrue(
                os.path.isfile(os.path.join(cos_target, "skills", "chief-of-staff-ops", "scripts", "consult_council.py"))
            )

            # Verificar que re-ejecutar no sobrescribe MEMORY.md ni quota_budget.json existentes
            custom_mem = "# Custom Memory Sentinel\n"
            mem_file = os.path.join(cos_target, "MEMORY.md")
            with open(mem_file, "w", encoding="utf-8") as f:
                f.write(custom_mem)

            res2 = subprocess.run(
                ["bash", INSTALL_SH, "--copy", "--init-config", "--doctor"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(res2.returncode, 0, msg=res2.stderr)
            with open(mem_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), custom_mem)


if __name__ == "__main__":
    unittest.main()
