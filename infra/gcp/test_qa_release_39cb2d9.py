"""Rollback must never treat a familiar name/revision as ownership."""

import copy
import unittest

from infra.gcp import qa_release_39cb2d9 as release


class Ownership(unittest.TestCase):
    def info(self, candidate=False):
        labels = {"com.docker.compose.project": "anvil-qa-v1", "com.docker.compose.service": "api",
                  "org.opencontainers.image.revision": release.REVISION if candidate else "08d45ff8eeb515561fbcd50916d6a7adb8fca42c"}
        if candidate:
            labels["io.adi.forge.release_intent"] = release.INTENT_LABEL
        return {"Id": "f" * 64 if candidate else release.OLD_IDS["api"], "Name": "/anvil-qa-v1-api-1",
                "Config": {"Image": "candidate-image" if candidate else "old-image", "Labels": labels}}

    def test_exact_old_id_or_attempt_bound_candidate_only(self):
        self.assertEqual(release.owned_kind(self.info(), "api", "candidate-image", "old-image"), "old")
        self.assertEqual(release.owned_kind(self.info(True), "api", "candidate-image", "old-image"), "candidate")

    def test_stopped_foreign_old_revision_is_not_safe_to_recreate(self):
        info = self.info()
        info.update(Id="e" * 64, State={"Running": False, "Pid": 0})
        with self.assertRaises(ValueError):
            release.owned_kind(info, "api", "candidate-image", "old-image")

    def test_wrong_scope_image_revision_and_missing_attempt_label_are_refused(self):
        for field, value in (("com.docker.compose.project", "foreign"), ("com.docker.compose.service", "worker"),
                             ("org.opencontainers.image.revision", "other"), ("io.adi.forge.release_intent", "foreign")):
            with self.subTest(field=field):
                info = self.info(True)
                info["Config"]["Labels"][field] = value
                with self.assertRaises(ValueError):
                    release.owned_kind(info, "api", "candidate-image", "old-image")
        for patch in ({"Image": "foreign"}, {"Labels": {}}):
            info = copy.deepcopy(self.info(True))
            info["Config"].update(patch)
            with self.assertRaises(ValueError):
                release.owned_kind(info, "api", "candidate-image", "old-image")


if __name__ == "__main__":
    unittest.main()
