"""Published product-profile input recognition, never execution approval."""
import pytest
from fastapi import HTTPException

from anvil.golden_targets import family
from anvil.project_inputs import source_family


@pytest.mark.parametrize('product', ['individual', 'adult_joint', 'teen_joint', 'custodial'])
def test_product_profile_has_kyc_schema_without_authored_dataset(product):
    task = {'source': {'schema_version': 'anvil.praxis-authored-public-task.v1',
                       'template': {'profile_id': 'golden-kyc-application-type-v1'}},
            'case_selector': {'field': 'product', 'value': product}}
    assert family(task) == source_family({'content': {'tasks': [task]}}) == 'kyc'
    assert 'case_dataset' not in task


def test_unknown_profile_and_mixed_families_still_fail_closed():
    known = {'source': {'template': {'profile_id': 'golden-kyc-application-type-v1'}}}
    unknown = {'source': {'template': {'profile_id': 'golden-kyc-unqualified-v999'}}}
    marketing = {'source': {'template': {'profile_id': 'veyra-hush-one-launch-v1'}}}
    assert family(unknown) is None
    for tasks in ([unknown], [known, unknown], [known, marketing], []):
        with pytest.raises(HTTPException) as exc:
            source_family({'content': {'tasks': tasks}})
        assert exc.value.status_code == 409
