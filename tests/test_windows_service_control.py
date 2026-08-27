import unittest

from sazmanhr.windows_service_control import stop_windows_service


def query_output(state: int, label: str = "STATE") -> str:
    return (
        "SERVICE_NAME: HRMCentralService\n"
        "        TYPE               : 10  WIN32_OWN_PROCESS\n"
        f"        {label:<19}: {state}  TEST_STATE\n"
        "        WIN32_EXIT_CODE    : 0  (0x0)\n"
    )


class SequenceRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, action, service_name):
        self.calls.append((action, service_name))
        if not self.responses:
            raise AssertionError("Unexpected sc.exe call")
        expected_action, response = self.responses.pop(0)
        if action != expected_action:
            raise AssertionError(f"Expected {expected_action}, got {action}")
        return response


class WindowsServiceControlTests(unittest.TestCase):
    def test_running_service_is_stopped_and_verified(self):
        runner = SequenceRunner([
            ("queryex", (0, query_output(4))),
            ("stop", (0, "[SC] ControlService SUCCESS\n")),
            ("queryex", (0, query_output(3))),
            ("queryex", (0, query_output(1))),
        ])
        now = [0.0]

        def clock():
            return now[0]

        def sleep(seconds):
            now[0] += seconds

        result = stop_windows_service(
            "HRMCentralService", 30, runner=runner, clock=clock, sleeper=sleep
        )
        self.assertTrue(result["exists"])
        self.assertTrue(result["was_running"])
        self.assertEqual(result["final_state"], 1)
        self.assertEqual(runner.responses, [])

    def test_stopped_service_is_not_started_or_stopped_again(self):
        runner = SequenceRunner([("queryex", (0, query_output(1, "وضعیت")))])
        result = stop_windows_service("HRMCentralService", runner=runner)
        self.assertTrue(result["exists"])
        self.assertFalse(result["was_running"])
        self.assertEqual(runner.calls, [("queryex", "HRMCentralService")])

    def test_missing_service_is_safe(self):
        runner = SequenceRunner([
            ("queryex", (1060, "OpenService FAILED 1060: service does not exist")),
        ])
        result = stop_windows_service("HRMCentralService", runner=runner)
        self.assertFalse(result["exists"])
        self.assertFalse(result["was_running"])

    def test_stop_timeout_is_a_hard_failure(self):
        runner = SequenceRunner([
            ("queryex", (0, query_output(4))),
            ("stop", (0, "[SC] ControlService SUCCESS\n")),
            ("queryex", (0, query_output(3))),
            ("queryex", (0, query_output(3))),
        ])
        now = [0.0]

        def clock():
            return now[0]

        def sleep(seconds):
            now[0] += seconds

        with self.assertRaises(TimeoutError):
            stop_windows_service(
                "HRMCentralService", 0.25, runner=runner, clock=clock, sleeper=sleep
            )

    def test_invalid_service_name_is_rejected(self):
        with self.assertRaises(ValueError):
            stop_windows_service("HRM & whoami", runner=lambda *_: (0, ""))


if __name__ == "__main__":
    unittest.main()
