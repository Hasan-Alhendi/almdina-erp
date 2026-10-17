from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
from threading import Event
from time import monotonic, sleep
from unittest import mock
from uuid import uuid4

import frappe
import MySQLdb
import pymysql
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.services.new_order_recovery_service import (
    reconcile_new_order_creation,
)


class _NoopOrderSaveGateway:
    def enforce_immutability(self) -> None:
        pass

    def set_piece_numbers(self) -> None:
        pass

    def validate_piece_inputs(self) -> None:
        pass

    def validate_piece_policies(self) -> None:
        pass

    def load_board_snapshot(self) -> None:
        pass

    def calculate_cut_dimensions(self) -> None:
        pass

    def calculate_piece_costs(self) -> None:
        pass

    def calculate_extra_addon_prices(self) -> None:
        pass


class TestNewOrderRecoveryIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.tokens: list[str] = []
        self.test_roles: list[str] = []
        self.test_users: list[str] = []

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        if self.tokens:
            frappe.db.delete(
                "Door Cutting Order",
                {"recovery_creation_token": ["in", self.tokens]},
            )
        for user in self.test_users:
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in self.test_roles:
            frappe.db.delete("Almdina Permission Audit", {"role": role})
            frappe.db.delete("Custom DocPerm", {"role": role})
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        if self.test_roles:
            frappe.clear_cache()
        super().tearDown()

    def _insert(self, token: str):
        order = frappe.new_doc("Door Cutting Order")
        order.recovery_creation_token = token
        order.flags._order_save_gateway = _NoopOrderSaveGateway()
        with (
            mock.patch(
                "almdina_erp.almdina_erp.doctype.door_cutting_order."
                "door_cutting_order_controller.invalidate_stale_draft_plans"
            ),
            mock.patch(
                "almdina_erp.almdina_erp.doctype.door_cutting_order."
                "door_cutting_order_controller.refresh_order_commercial_totals"
            ),
        ):
            order.insert(ignore_permissions=True, ignore_mandatory=True)
        return order

    def _create_user(self, *, can_create: bool) -> str:
        from almdina_erp.almdina_erp.domain.security.authorization import Capability
        from almdina_erp.almdina_erp.services.permission_management_service import (
            update_role_permissions,
        )

        role = f"Almdina Recovery Test {uuid4().hex[:8]}"
        email = f"almdina.recovery.{uuid4().hex[:12]}@example.com"
        frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
        self.test_roles.append(role)
        if can_create:
            update_role_permissions(role, {Capability.CREATE_ORDER: True})
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Recovery",
                "last_name": "Test",
                "user_type": "System User",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        self.test_users.append(email)
        frappe.clear_cache(user=email)
        frappe.clear_cache(doctype="Door Cutting Order")
        frappe.local.role_permissions = {}
        if hasattr(frappe.local, "almdina_matrix_capabilities"):
            del frappe.local.almdina_matrix_capabilities
        return email

    def test_lost_response_reconciles_to_one_native_insert(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)

        inserted = self._insert(token)
        # Model the client losing the successful HTTP response by discarding the
        # inserted Document and asking only through the creation token.
        first_reconciliation = reconcile_new_order_creation(token)
        repeated_reconciliation = reconcile_new_order_creation(token)

        self.assertEqual(first_reconciliation["status"], "CREATED")
        self.assertEqual(first_reconciliation["door_cutting_order"], inserted.name)
        self.assertEqual(repeated_reconciliation, first_reconciliation)

        unique_errors = tuple(
            error
            for error in (
                getattr(frappe, "DuplicateEntryError", None),
                getattr(frappe, "UniqueValidationError", None),
            )
            if isinstance(error, type)
        )
        self.assertTrue(unique_errors)
        with self.assertRaises(unique_errors):
            self._insert(token)

        names = frappe.get_all(
            "Door Cutting Order",
            filters={"recovery_creation_token": token},
            pluck="name",
        )
        self.assertEqual(names, [inserted.name], "the repeated identity cannot create DCO B")

    def test_reconciliation_rejects_unauthenticated_token_probing(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        self._insert(token)

        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            reconcile_new_order_creation(token)

    def test_unbound_identity_is_proven_without_creating_a_dco(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)

        result = reconcile_new_order_creation(token)

        self.assertEqual(result, {"status": "NOT_FOUND"})
        self.assertFalse(
            frappe.db.exists("Door Cutting Order", {"recovery_creation_token": token})
        )

    def test_acknowledged_creation_binding_is_immutable(self) -> None:
        token = str(uuid4())
        replacement = str(uuid4())
        self.tokens.extend((token, replacement))
        order = self._insert(token)
        order.recovery_creation_token = replacement
        order.flags._order_save_gateway = _NoopOrderSaveGateway()

        with self.assertRaises(frappe.ValidationError):
            order.save(ignore_permissions=True, ignore_version=True)

    def test_insert_binds_token_to_session_user_and_rejects_malformed_token(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        order = self._insert(token)
        self.assertEqual(
            frappe.db.get_value("Door Cutting Order", order.name, "recovery_creation_user"),
            "Administrator",
        )

        malformed = "not-a-uuid"
        invalid = frappe.new_doc("Door Cutting Order")
        invalid.recovery_creation_token = malformed
        invalid.flags._order_save_gateway = _NoopOrderSaveGateway()
        with self.assertRaises(frappe.ValidationError):
            invalid.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertFalse(
            frappe.db.exists("Door Cutting Order", {"recovery_creation_token": malformed})
        )

    def test_reconciliation_scopes_tokens_and_checks_real_document_read_permission(self) -> None:
        owner_token = str(uuid4())
        self.tokens.append(owner_token)
        self._insert(owner_token)

        creator_user = self._create_user(can_create=True)
        frappe.set_user(creator_user)
        self.assertTrue(
            frappe.has_permission("Door Cutting Order", "read", user=creator_user),
            "CREATE_ORDER grants VIEW_ORDERS and native DCO read by contract",
        )
        # Another user's token is indistinguishable from an unused token.
        self.assertEqual(reconcile_new_order_creation(owner_token), {"status": "NOT_FOUND"})

        own_token = str(uuid4())
        self.tokens.append(own_token)
        own_order = self._insert(own_token)
        self.assertTrue(
            frappe.has_permission("Door Cutting Order", "read", own_order, user=creator_user),
            "the creator's real projected Frappe permission allows reading the bound DCO",
        )
        own_result = reconcile_new_order_creation(own_token)
        self.assertEqual(own_result["status"], "CREATED")
        self.assertEqual(own_result["door_cutting_order"], own_order.name)

        frappe.set_user("Administrator")
        no_create_user = self._create_user(can_create=False)
        frappe.set_user(no_create_user)
        with self.assertRaises(frappe.PermissionError):
            reconcile_new_order_creation(str(uuid4()))

    def test_concurrent_database_inserts_reject_duplicate_creation_token(self) -> None:
        token = str(uuid4())
        self.tokens.append(token)
        site = frappe.local.site
        use_mysqlclient = frappe.conf.get("use_mysqlclient", 1)
        frappe_db_driver = "mysqlclient" if use_mysqlclient else "pymysql"
        frappe_integrity_error = (
            MySQLdb.IntegrityError if use_mysqlclient else pymysql.err.IntegrityError
        )
        evidence: dict[str, object] = {
            "test": "test_concurrent_database_inserts_reject_duplicate_creation_token",
            "boundary": "MariaDB unique index on recovery_creation_token",
            "frappe_mariadb_driver": frappe_db_driver,
            "status": "INCOMPLETE",
            "unique_index_verified": False,
            "connection_ids": [],
            "observed_unique_lock_wait": None,
            "outcomes": [],
            "committed_row_count": None,
        }
        insert_sql = """
            INSERT INTO `tabDoor Cutting Order`
                (`name`, `owner`, `creation`, `modified`, `modified_by`,
                 `docstatus`, `idx`, `recovery_creation_token`, `recovery_creation_user`)
            VALUES (%s, %s, NOW(6), NOW(6), %s, 0, 0, %s, %s)
        """
        first_insert_completed = Event()
        competitor_attempting_insert = Event()
        allow_first_commit = Event()
        connection_ids: dict[int, int] = {}

        def write_evidence() -> None:
            evidence_path = os.environ.get("AL129_CONCURRENCY_EVIDENCE_FILE")
            if evidence_path:
                Path(evidence_path).write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        def insert_on_independent_connection(worker: int) -> dict[str, object]:
            connection_id: int | None = None
            connected = False
            order_name = f"DCO-RECOVERY-RACE-{uuid4().hex[:12]}-{worker}"
            try:
                frappe.init(site=site)
                frappe.connect()
                connected = True
                frappe.set_user("Administrator")
                frappe.db.sql("START TRANSACTION")
                connection_id = int(frappe.db.sql("SELECT CONNECTION_ID()", pluck=True)[0])
                connection_ids[worker] = connection_id
                if worker == 1 and not first_insert_completed.wait(timeout=10):
                    raise TimeoutError("winner transaction did not reach its uncommitted insert")
                if worker == 1:
                    competitor_attempting_insert.set()
                frappe.db.sql(
                    insert_sql,
                    (
                        order_name,
                        "Administrator",
                        "Administrator",
                        token,
                        "Administrator",
                    ),
                )
                if worker == 0:
                    first_insert_completed.set()
                    if not allow_first_commit.wait(timeout=10):
                        raise TimeoutError("coordinator did not release the first insert transaction")
                    frappe.db.commit()
                else:
                    frappe.db.commit()
                return {
                    "worker": worker,
                    "connection_id": connection_id,
                    "kind": "inserted",
                    "name": order_name,
                }
            except Exception as error:
                if connected:
                    frappe.db.rollback()
                errno = None
                violated_index = None
                if isinstance(error, frappe_integrity_error):
                    try:
                        errno = int(error.args[0]) if error.args else None
                    except (TypeError, ValueError):
                        errno = None
                    detail = str(error.args[1] if len(error.args) > 1 else error)
                    key_match = re.search(
                        r"for key\s+[`'\"]([^`'\"]+)[`'\"]",
                        detail,
                        re.IGNORECASE,
                    )
                    violated_index = key_match.group(1) if key_match else None
                if errno == 1062 and violated_index == "recovery_creation_token":
                    kind = "unique_conflict"
                elif isinstance(error, TimeoutError):
                    kind = "coordination_timeout"
                else:
                    kind = "error"
                message = str(error).replace(token, "[redacted-creation-token]")
                return {
                    "worker": worker,
                    "connection_id": connection_id,
                    "kind": kind,
                    "error_type": type(error).__name__,
                    "error_type_module": type(error).__module__,
                    "error_args": [
                        str(argument).replace(token, "[redacted-creation-token]")
                        for argument in error.args
                    ],
                    "errno": errno,
                    "violated_index": violated_index,
                    "error": message,
                }
            finally:
                if connected:
                    frappe.destroy()

        observer_connection = None
        try:
            unique_indexes = frappe.db.sql(
                "SHOW INDEX FROM `tabDoor Cutting Order` "
                "WHERE Column_name = %s AND Non_unique = 0",
                ("recovery_creation_token",),
                as_dict=True,
            )
            index_names = sorted({str(row.Key_name) for row in unique_indexes})
            self.assertTrue(
                index_names,
                "the installed DCO schema must have a unique recovery_creation_token index",
            )
            evidence["unique_index_verified"] = True
            evidence["unique_index_names"] = index_names
            root_password = os.environ.get("AL129_DB_ROOT_PASSWORD")
            self.assertTrue(
                root_password,
                "the isolated MariaDB observer credential must be configured for this race test",
            )

            frappe.db.commit()
            observer_connection = pymysql.connect(
                host=os.environ.get("AL129_DB_HOST", "127.0.0.1"),
                port=int(os.environ.get("AL129_DB_PORT", "3306")),
                user=os.environ.get("AL129_DB_ROOT_USER", "root"),
                password=root_password,
                database=str(frappe.conf.db_name),
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
            )
            lock_wait_query = """
                SELECT requesting.trx_mysql_thread_id AS waiting_connection_id,
                       blocking.trx_mysql_thread_id AS blocking_connection_id,
                       requested.lock_table,
                       requested.lock_index
                  FROM information_schema.INNODB_LOCK_WAITS AS waits
                  JOIN information_schema.INNODB_TRX AS requesting
                    ON requesting.trx_id = waits.requesting_trx_id
                  JOIN information_schema.INNODB_TRX AS blocking
                    ON blocking.trx_id = waits.blocking_trx_id
                  JOIN information_schema.INNODB_LOCKS AS requested
                    ON requested.lock_id = waits.requested_lock_id
                 WHERE requesting.trx_mysql_thread_id = %s
            """
            outcomes: list[dict[str, object]] = []
            winner_reached_insert = False
            competitor_reached_insert = False
            observer_error: str | None = None
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(insert_on_independent_connection, worker) for worker in range(2)]
                try:
                    winner_reached_insert = first_insert_completed.wait(timeout=10)
                    competitor_reached_insert = competitor_attempting_insert.wait(timeout=10)
                    observed_wait = None
                    second_connection_id = connection_ids.get(1)
                    if winner_reached_insert and competitor_reached_insert and second_connection_id:
                        deadline = monotonic() + 10
                        while monotonic() < deadline:
                            with observer_connection.cursor() as cursor:
                                cursor.execute(lock_wait_query, (second_connection_id,))
                                observed_wait = cursor.fetchone()
                            if observed_wait:
                                break
                            sleep(0.025)
                    evidence["observed_unique_lock_wait"] = observed_wait
                except Exception as error:
                    observer_error = f"{type(error).__name__}: {error}"
                finally:
                    allow_first_commit.set()
                    for future in futures:
                        try:
                            outcomes.append(future.result(timeout=15))
                        except Exception as error:
                            outcomes.append(
                                {
                                    "kind": "worker_exception",
                                    "error_type": type(error).__name__,
                                    "error": str(error).replace(token, "[redacted-creation-token]"),
                                }
                            )
            evidence["outcomes"] = outcomes
            worker_connection_ids = [row.get("connection_id") for row in outcomes]
            evidence["connection_ids"] = worker_connection_ids
            evidence["winner_reached_insert"] = winner_reached_insert
            evidence["competitor_reached_insert"] = competitor_reached_insert
            evidence["observer_error"] = observer_error
            self.assertTrue(winner_reached_insert, "winner did not leave an uncommitted unique-key row")
            self.assertTrue(competitor_reached_insert, "competitor did not reach the SQL insert boundary")
            self.assertIsNone(observer_error, f"MariaDB lock observer failed: {observer_error}")
            self.assertTrue(
                all(worker_connection_ids) and len(set(worker_connection_ids)) == 2,
                f"workers must use two independent MariaDB connections: {outcomes}",
            )
            observed_wait = evidence["observed_unique_lock_wait"]
            self.assertIsInstance(
                observed_wait,
                dict,
                "the competitor must be observed waiting inside MariaDB before winner commit",
            )
            self.assertEqual(
                int(observed_wait["waiting_connection_id"]),
                int(connection_ids[1]),
            )
            self.assertEqual(
                int(observed_wait["blocking_connection_id"]),
                int(connection_ids[0]),
            )
            self.assertIn("tabDoor Cutting Order", str(observed_wait["lock_table"]))
            self.assertIn(
                str(observed_wait["lock_index"]),
                index_names,
                "the observed wait must be on the unique index containing the creation token",
            )
            self.assertCountEqual(
                [row["kind"] for row in outcomes],
                ["inserted", "unique_conflict"],
                f"The race must produce one committed insert and one native unique conflict; "
                f"timeouts, deadlocks, and barrier failures are test failures: {outcomes}",
            )
            winner = next(row for row in outcomes if row["kind"] == "inserted")
            winner_worker = int(winner["worker"])
            winner_connection_id = int(winner["connection_id"])
            evidence["winner_worker"] = winner_worker
            evidence["winner_connection_id"] = winner_connection_id
            self.assertEqual(
                winner_connection_id,
                connection_ids.get(winner_worker),
                "the committed insert outcome must retain its independent MariaDB connection identity",
            )
            self.assertEqual(
                str(winner["name"]).rsplit("-", 1)[-1],
                str(winner_worker),
                "the committed DCO name must identify the worker connection that won the race",
            )
            committed_names = frappe.db.sql(
                "SELECT name FROM `tabDoor Cutting Order` WHERE recovery_creation_token = %s",
                (token,),
                pluck=True,
            )
            evidence["committed_row_count"] = len(committed_names)
            name_matches_winner = (
                len(committed_names) == 1
                and str(committed_names[0]) == str(winner["name"])
            )
            evidence["committed_name_matches_winner"] = name_matches_winner
            self.assertEqual(
                len(committed_names),
                1,
                "exactly one competing insert may commit for a creation token",
            )
            self.assertTrue(
                name_matches_winner,
                "the only committed row must be the worker that won the unique-index race",
            )
            evidence["status"] = "PASS"
        except Exception as error:
            evidence["status"] = "FAIL"
            evidence["failure"] = (
                f"{type(error).__name__}: "
                f"{str(error).replace(token, '[redacted-creation-token]')}"
            )
            raise
        finally:
            allow_first_commit.set()
            try:
                frappe.db.rollback()
                frappe.db.sql(
                    "DELETE FROM `tabDoor Cutting Order` WHERE recovery_creation_token = %s",
                    (token,),
                )
                frappe.db.commit()
            except Exception as error:
                evidence["status"] = "FAIL"
                evidence["cleanup_error"] = (
                    f"{type(error).__name__}: {str(error).replace(token, '[redacted-creation-token]')}"
                )
                raise
            finally:
                if observer_connection is not None:
                    try:
                        observer_connection.close()
                    except Exception as error:
                        evidence["status"] = "FAIL"
                        evidence["observer_close_error"] = f"{type(error).__name__}: {error}"
                write_evidence()
