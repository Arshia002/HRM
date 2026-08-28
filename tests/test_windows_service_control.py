import unittest

from sazmanhr.windows_service_control import stop_windows_service


class FakeClock:
    def __init__(self):
        self.value = 0.0
    def __call__(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class WindowsServiceControlTests(unittest.TestCase):
    def test_missing_service_is_safe(self):
        def runner(action, name):
            return 1060, "OpenService FAILED 1060"
        state = stop_windows_service("HRMCentralService", runner=runner)
        self.assertEqual(state["exists"], False)
        self.assertEqual(state["was_running"], False)

    def test_already_stopped_service_is_preserved(self):
        def runner(action, name):
            self.assertEqual(action, "queryex")
            return 0, "        STATE              : 1  STOPPED\n"
        state = stop_windows_service("HRMCentralService", runner=runner)
        self.assertEqual(state["exists"], True)
        self.assertEqual(state["was_running"], False)
        self.assertEqual(state["final_state"], 1)

    def test_running_service_is_stopped_and_verified(self):
        clock = FakeClock()
        queries = iter([4, 3, 1])
        actions = []
        def runner(action, name):
            actions.append(action)
            if action == "stop":
                return 0, "STOP pending"
            state = next(queries)
            return 0, f"        STATE              : {state}  STATE_NAME\n"
        result = stop_windows_service(
            "HRMCentralService", timeout_seconds=5, runner=runner,
            clock=clock, sleeper=clock.sleep,
        )
        self.assertTrue(result["was_running"])
        self.assertEqual(result["final_state"], 1)
        self.assertIn("stop", actions)

    def test_invalid_service_name_is_rejected(self):
        with self.assertRaises(ValueError):
            stop_windows_service('HRM Central & del C:\\', runner=lambda *_: (0, ""))


if __name__ == "__main__":
    unittest.main()
