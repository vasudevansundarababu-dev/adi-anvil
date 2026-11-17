"""One isolated conditional decision/data/finance successor for API custody.

This is not a database commit. Only the guarded private API may publish a
receipt after atomically persisting the complete returned successor.
"""

from anvil.marketing_task2_persistence import freeze
from anvil.marketing_world_activation_definition import ActivationWorldDefinition, decode_sources
from anvil.marketing_world_authority import PREFIX
from anvil.marketing_world_authority import prepare as prepare_authority
from anvil.marketing_world_finance_transition import prepare as prepare_finance
from anvil.marketing_world_financial_records import prepare_projection
from anvil.marketing_world_opening_definition import OpeningWorldDefinition
from anvil.marketing_world_population_definition import PopulationWorldDefinition
from anvil.marketing_world_report_activation import prepare as prepare_reports
from anvil.praxis_generic_contract import digest


def prepare(controller, world, execution, node, inputs):
    if type(world) not in (ActivationWorldDefinition, OpeningWorldDefinition, PopulationWorldDefinition) or world.case_id != controller.case_id:
        raise ValueError("Exact source-validated complete activation-world v4 required")
    baseline = world.finance_book
    successor, public, private = prepare_authority(controller, execution, node, inputs, world.service_contract, baseline)
    if successor is None:
        return None, public, "timeout"
    selected, reports = world.selected_programs(controller._outcome)
    successor = prepare_finance(successor, baseline, selected, controller._clock)
    successor = prepare_reports(successor, reports)
    documents = decode_sources(world.case_id, world.activation_source_documents)
    projection = prepare_projection(successor, world.finance_source_documents, documents, selected, private)
    successor._initial.update(projection)
    guards = [key for key in successor._controller_keys if key.startswith(PREFIX) and ":" not in key[len(PREFIX):]]
    if len(guards) != 1:
        raise ValueError("Exactly one private combined transition required")
    slot = guards[0]
    proof = successor._controller_keys[slot][1]
    proof.update(financial_projection_sha256=digest(projection), activation_world_sha256=digest(world.model_dump(mode="json")))
    successor._controller_keys[slot] = (digest(proof), proof)
    # Validate the complete existing serialization bounds before the API may
    # attempt any mutation. All prior intermediate clones remain private.
    freeze(successor)
    return successor, public, "responded"
