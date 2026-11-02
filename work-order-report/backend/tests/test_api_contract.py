"""Database-free regression checks for the public API contract."""

import unittest

from api.main import app


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
STANDARD_ERRORS = {"400", "401", "403", "404", "409", "422", "500", "502", "503"}


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = app.openapi()
        cls.operations = [
            (path, method, operation)
            for path, path_item in cls.schema["paths"].items()
            for method, operation in path_item.items()
            if method in HTTP_METHODS
        ]

    def test_operation_ids_are_unique(self):
        operation_ids = [operation["operationId"] for _, _, operation in self.operations]
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_canonical_v1_operation_count(self):
        v1 = [item for item in self.operations if item[0].startswith("/api/v1/")]
        self.assertEqual(44, len(v1))

    def test_v1_operations_document_standard_errors(self):
        for path, method, operation in self.operations:
            if not path.startswith("/api/v1/"):
                continue
            with self.subTest(path=path, method=method):
                self.assertTrue(STANDARD_ERRORS.issubset(operation["responses"]))

    def test_only_v1_application_operations_are_exposed(self):
        application_operations = [
            item for item in self.operations if item[0].startswith("/api/")
        ]
        self.assertTrue(application_operations)
        self.assertTrue(
            all(path.startswith("/api/v1/") for path, _, _ in application_operations)
        )

    def test_v1_daily_report_has_only_supported_query_parameters(self):
        operation = self.schema["paths"]["/api/v1/daily-reports"]["get"]
        parameters = {parameter["name"] for parameter in operation.get("parameters", [])}
        self.assertNotIn("group", parameters)
        self.assertNotIn("include_live_records", parameters)

    def test_resource_creation_status_codes(self):
        self.assertIn("201", self.schema["paths"]["/api/v1/auth/sessions"]["post"]["responses"])
        self.assertIn("201", self.schema["paths"]["/api/v1/report-deliveries"]["post"]["responses"])
        self.assertIn("201", self.schema["paths"]["/api/v1/automation/task-reminder-executions"]["post"]["responses"])

    def test_automation_trigger_uses_api_key_security(self):
        operation = self.schema["paths"]["/api/v1/automation/task-reminder-executions"]["post"]
        security_names = {name for requirement in operation["security"] for name in requirement}
        self.assertIn("APIKeyHeader", security_names)


if __name__ == "__main__":
    unittest.main()
