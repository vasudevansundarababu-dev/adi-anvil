"""Transaction-local entry from a disjoint runtime LOGIN to its NOLOGIN role."""


def enter(c, role_name, project):
    if role_name not in {"anvil_golden_scheduler", "anvil_golden_grader"}:
        raise ValueError("Fixed Golden runtime role required")
    grading = role_name == "anvil_golden_grader"
    role = c.execute(
        "SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolcanlogin,"
        "current_user=session_user AS original_login,"
        "pg_has_role(current_user,%s,'MEMBER') AS assigned FROM pg_roles WHERE rolname=current_user",
        (role_name,),
    ).fetchone()
    forbidden = c.execute(
        "SELECT has_table_privilege(current_user,%s,'SELECT') AS access",
        ("banking_private.scenarios" if grading else "banking_private.expectations",),
    ).fetchone()["access"]
    mixed = c.execute(
        "SELECT pg_has_role(current_user,'anvil_app','MEMBER') OR "
        "pg_has_role(current_user,'anvil_worker','MEMBER') OR "
        "pg_has_role(current_user,%s,'MEMBER') AS mixed",
        ("anvil_golden_scheduler" if grading else "anvil_golden_grader",),
    ).fetchone()["mixed"]
    if (
        not role
        or any(
            role[key]
            for key in (
                "rolsuper",
                "rolbypassrls",
                "rolcreatedb",
                "rolcreaterole",
                "rolreplication",
            )
        )
        or not role["rolcanlogin"]
        or not role["original_login"]
        or not role["assigned"]
        or forbidden
        or mixed
    ):
        raise RuntimeError("Dedicated non-owner disjoint Golden runtime login required")
    c.execute(
        "SET LOCAL ROLE anvil_golden_grader" if grading else "SET LOCAL ROLE anvil_golden_scheduler"
    )
    c.execute("SELECT set_config('anvil.project',%s,true)", (str(project),))
