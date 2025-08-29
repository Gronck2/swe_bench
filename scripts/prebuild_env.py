#!/usr/bin/env python3
"""
Prebuild SWE-bench base/env/instance images for local data_points JSON files.

- Reads changed files from CHANGED_FILES / CHANGED_FILES_JSON (newline-separated).
- For each JSON, constructs TestSpec and invokes docker_build helpers to ensure images exist.

Safe to run multiple times; uses force rebuild if FORCE_REBUILD=1.
"""
from __future__ import annotations

import json
import os
import sys
import inspect
from pathlib import Path
from typing import List


def get_changed_json_files() -> List[Path]:
    changed_files_json = os.environ.get("CHANGED_FILES_JSON", "").strip()
    changed_files_raw = os.environ.get("CHANGED_FILES", "").strip()

    files: List[str] = []
    if changed_files_json:
        try:
            parsed = json.loads(changed_files_json)
            if isinstance(parsed, list):
                files = [str(p) for p in parsed if str(p).endswith(".json")]
        except Exception:
            pass
    if not files and changed_files_raw:
        files = [line.strip() for line in changed_files_raw.split("\n") if line.strip().endswith(".json")]

    # Fallback: prebuild all data_points/*.json
    if not files and Path("data_points").exists():
        files = [str(p) for p in Path("data_points").glob("*.json")]

    # Dedup and keep order
    seen = set()
    unique_files: List[Path] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique_files.append(Path(f))
    return unique_files


def main() -> int:
    try:
        from swebench.harness.test_spec.test_spec import make_test_spec
        import swebench.harness.docker_build as docker_build
        import docker  # type: ignore
    except Exception as e:
        print(f"Skip prebuild: SWE-bench harness not available: {e}")
        return 0

    force_rebuild = os.environ.get("FORCE_REBUILD", "0") in {"1", "true", "True"}
    client = docker.from_env()

    def call_helper(func, test_spec, force: bool = False) -> bool:
        try:
            sig = inspect.signature(func)
            params = sig.parameters
        except Exception:
            params = {}

        kwargs = {}
        if "test_spec" in params:
            kwargs["test_spec"] = test_spec
        if "client" in params:
            kwargs["client"] = client
        if "docker_client" in params:
            kwargs["docker_client"] = client
        if "logger" in params:
            import logging

            kwargs["logger"] = logging.getLogger("prebuild")
        for k in ("nocache", "no_cache", "force_rebuild", "rebuild", "ensure"):
            if k in params:
                kwargs[k] = bool(force)

        try:
            func(**kwargs)
            return True
        except TypeError:
            # positional fallback: (test_spec, client, logger, nocache)
            args = []
            if "test_spec" in params:
                args.append(test_spec)
            if "client" in params:
                args.append(client)
            if "logger" in params:
                import logging

                args.append(logging.getLogger("prebuild"))
            if "nocache" in params:
                args.append(bool(force))
            func(*args)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"Helper {getattr(func, '__name__', '<func>')} failed: {e}")
            return False

    files = get_changed_json_files()
    if not files:
        print("No data point files to prebuild.")
        return 0

    print("Prebuilding images for files:")
    for f in files:
        print(f"  - {f}")

    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            test_spec = make_test_spec(data)
        except Exception as e:  # noqa: BLE001
            print(f"Skip {fp}: cannot create TestSpec: {e}")
            continue

        # Base image first
        for base_name in ("ensure_base_image", "build_base_image", "build_base"):
            if hasattr(docker_build, base_name):
                print(f"Calling {base_name} for base (from {fp})")
                try:
                    call_helper(getattr(docker_build, base_name), test_spec, force=force_rebuild)
                    break
                except Exception as be:  # noqa: BLE001
                    print(f"Base helper {base_name} failed: {be}")

        # Environment image
        env_ok = False
        for name in ("ensure_env_image", "build_env_image", "build_environment_image", "build_env"):
            if hasattr(docker_build, name):
                print(f"Calling {name} for {fp}")
                if call_helper(getattr(docker_build, name), test_spec, force=force_rebuild):
                    env_ok = True
                    break
        if not env_ok:
            print(f"No suitable env build helper for {fp}; continuing")

    return 0


if __name__ == "__main__":
    sys.exit(main())


