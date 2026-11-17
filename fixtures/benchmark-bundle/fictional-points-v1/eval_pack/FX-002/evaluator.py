"""Original arithmetic fixture oracle; private, inert on import, not a production evaluator."""
def evaluate(rules, output):
    return {r["id"]: int(type(output.get(r["field"])) is int and output[r["field"]] == r["expected"])
            for r in rules}
