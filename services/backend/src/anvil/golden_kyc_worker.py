"""Dedicated Anvil Golden scheduler/grader; no provider or ordinary-worker reuse."""

import argparse
import os
from contextlib import contextmanager
from time import monotonic
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from anvil.golden_kyc_identity import enter as enter_runtime_role
from anvil.golden_kyc_runtime import process_one


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--max-commands", type=int, default=100)
    parser.add_argument(
        "--mode",
        choices=(
            "commands",
            "capture",
            "grade",
            "finish",
            "paid-capture",
            "paid-grade",
            "custom-tests",
            "reconcile-custom-grade",
            "governed-ai",
        ),
        default="commands",
    )
    parser.add_argument("--max-cells", type=int, default=2000)
    parser.add_argument("--reconcile-job", type=UUID)
    parser.add_argument("--dispose-unconfirmed", action="store_true")
    parser.add_argument(
        "--rationale", default="Inspect and consume retained private coordinator result"
    )
    args = parser.parse_args(argv)
    if (
        (
            os.environ.get("ANVIL_GOLDEN_KYC_ENABLED") != "true"
            and args.mode not in {"custom-tests", "governed-ai"}
        )
        or not 1 <= args.max_commands <= 1000
        or not 1 <= args.max_cells <= 2000
    ):
        raise RuntimeError("Explicit Golden admission and bounded work required")
    grading = args.mode in {"grade", "paid-grade", "reconcile-custom-grade"}
    if args.mode == "reconcile-custom-grade" and not args.reconcile_job:
        raise ValueError("One exact previously claimed private grading job is required")
    if args.mode == "custom-tests" and os.environ.get("ANVIL_CUSTOM_PYTHON_ENABLED") != "true":
        raise RuntimeError("Qualified custom Python worker must be explicitly enabled")
    if args.mode == "paid-capture":
        from anvil import pilot_environment
        from anvil.golden_kyc_paid_qualification import installed

        if (
            pilot_environment.current() != "qa"
            or os.environ.get("ANVIL_WORKER_BROKER_ROLE") != "worker"
            or os.environ.get("ANVIL_GOLDEN_KYC_PAID_WORKER_ENABLED") != "true"
            or not installed()["ready"]
        ):
            raise RuntimeError("Qualified dedicated QA paid scheduler required")
    role_name = "anvil_golden_grader" if grading else "anvil_golden_scheduler"
    dsn = os.environ.get(
        "ANVIL_GOLDEN_GRADER_DATABASE_URL" if grading else "ANVIL_GOLDEN_SCHEDULER_DATABASE_URL"
    )
    if not dsn:
        raise RuntimeError("Dedicated disjoint runtime connection required")
    if args.mode == "paid-capture":
        from anvil.golden_kyc_deadline_database import SchedulerConnections
        from anvil.golden_kyc_paid_worker import process_one as paid_one
        from anvil.project_input_provisioning import scheduler_once as populate_input

        for _ in range(args.max_commands):
            if populate_input(SchedulerConnections(str(args.project),monotonic()+600)) is None:
                break
        completed=0
        for _ in range(args.max_commands):
            connections=SchedulerConnections(str(args.project),monotonic()+600)
            if paid_one(connections) is None:
                break
            completed+=1
        print(f"Golden paid scheduler processed {completed} jobs; inspect exact broker ledger for spend/outcomes")
        return
    # Only two operator-owned connections, no per-tool TCP/auth startup. All
    # identity/scope settings and role changes are transaction-local.
    with ConnectionPool(
        dsn, min_size=1, max_size=2, timeout=10, kwargs={"row_factory": dict_row}
    ) as pool:

        @contextmanager
        def connections():
            with pool.connection() as c:
                enter_runtime_role(c, role_name, args.project)
                yield c

        if args.mode == "governed-ai":
            from anvil.governed_ai_runtime import worker_once

            completed = 0
            for _ in range(args.max_commands):
                if worker_once(connections) is None:
                    break
                completed += 1
            print(
                f"Governed AI jobs processed:{completed}; inspect retained per-call usage/unknown states and shared budget"
            )
            return
        if args.mode == "reconcile-custom-grade":
            from anvil.custom_python_grading import reconcile

            print(
                "Private grading status reconciliation:",
                reconcile(
                    connections,
                    os.environ["ANVIL_PRIVATE_PYTHON_GRADING_ROOT"],
                    str(args.reconcile_job),
                    abandon=args.dispose_unconfirmed,
                    rationale=args.rationale,
                ),
            )
            return
        if args.mode == "custom-tests":
            from anvil.custom_python_worker import scheduler_once

            completed = 0
            for _ in range(args.max_commands):
                if (
                    scheduler_once(connections, os.environ["ANVIL_CUSTOM_PYTHON_BRIDGE_ROOT"])
                    is None
                ):
                    break
                completed += 1
            print(f"Isolated custom Python tests processed:{completed}; no model calls")
            return
        if args.mode == "paid-grade":
            from anvil.golden_kyc_grader import grade_paid

            result = grade_paid(connections, str(args.project), max_cells=args.max_cells)
            if (
                result.get("pending_custom_cells")
                and os.environ.get("ANVIL_CUSTOM_PYTHON_SCORING_ENABLED") == "true"
            ):
                from anvil.custom_python_grading import grader_once

                for _ in range(args.max_commands):
                    if (
                        grader_once(connections, os.environ["ANVIL_PRIVATE_PYTHON_GRADING_ROOT"])
                        is None
                    ):
                        break
                result = grade_paid(connections, str(args.project), max_cells=args.max_cells)
            print(
                "Golden paid grading:",
                result,
            )
            if os.environ.get("ANVIL_CAMPAIGN_GRADING_ENABLED") == "true":
                from anvil.campaign_grader import grade_one as grade_campaign

                campaign_count = 0
                for _ in range(args.max_commands):
                    campaign_result = grade_campaign(connections, str(args.project))
                    if campaign_result is None:
                        break
                    if campaign_result.get("status") == "pending":
                        break
                    campaign_count += 1
                print("Campaign sealed episodes graded:", campaign_count)
            return
        if args.mode != "commands":
            from anvil.golden_kyc_orchestration import execute_phase

            result = execute_phase(
                connections, str(args.project), args.mode, max_cells=args.max_cells
            )
            print("Golden Anvil phase:", result or "no eligible job", "; paid calls off")
            return
        completed = 0
        for _ in range(args.max_commands):
            with connections() as c:
                result = process_one(c)
            if result is None:
                break
            completed += 1
        print(f"Golden scheduler processed {completed} commands; provider calls disabled")


if __name__ == "__main__":
    main()
