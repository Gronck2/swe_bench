# Negative Testing Report

This document summarizes negative test scenarios to verify validator robustness.

## Scenarios

1. Invalid JSON syntax
   - Input: malformed JSON in `data_points/*.json`
   - Expected: `INVALID_JSON` with file path and parse error snippet

2. Missing required fields
   - Input: absent `patch`, `FAIL_TO_PASS`, or `PASS_TO_PASS`
   - Expected: structured schema error with field names

3. Invalid patch format
   - Input: non-diff content in `patch` or `test_patch`
   - Expected: `FAILED` with patch-apply failure details

4. Patch does not apply
   - Input: valid diff but mismatched `base_commit`
   - Expected: `FAILED` with git apply error

5. Tests still failing (FAIL_TO_PASS)
   - Input: patch insufficient to fix tests
   - Expected: `FAILED` with failing tests listed

6. Regressions in PASS_TO_PASS
   - Input: patch breaks previously passing tests
   - Expected: `FAILED` with regression tests listed

7. Docker runtime errors
   - Input: Docker daemon unavailable
   - Expected: `ERROR` with actionable hints

8. Timeout exceeded
   - Input: long-running tests beyond configured timeout
   - Expected: `TIMEOUT` with elapsed time and test context

## Artifacts

- Logs: `logs/run_evaluation/<timestamp>/...`
- Build logs: `logs/build_images/...`
- Suggested ENV for stress: `SWE_BENCH_CACHE_LEVEL=none`, low timeouts

## Notes

- For GitHub-hosted runners, use `SWE_BENCH_CACHE_LEVEL=base`.
- Prefer self-hosted for heavy caching levels (`env`, `instance`).

