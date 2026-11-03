import unittest
from unittest.mock import Mock, patch

from scripts import release_state as release

IMAGE = "ghcr.io/example/relay"
DIGEST = "sha256:" + "a" * 64
INDEX = {"manifests": [{"platform": {"os": "linux", "architecture": arch}} for arch in ("amd64", "arm64")]}


class ReleaseStateTests(unittest.TestCase):
    def registry(self, version_manifest=(DIGEST, INDEX), latest_manifest=(DIGEST, INDEX)):
        return Mock(manifest=Mock(side_effect=[version_manifest, latest_manifest]))

    def test_complete_multiarch_release_is_published(self):
        self.assertTrue(release.published(self.registry(), "1.104.5"))

    def test_missing_version_tag_requires_retry(self):
        registry = self.registry(version_manifest=None)
        self.assertFalse(release.published(registry, "1.104.5"))
        registry.manifest.assert_called_once_with("1.104.5")

    def test_missing_or_stale_latest_tag_requires_retry(self):
        for latest in [None, ("sha256:" + "b" * 64, INDEX)]:
            with self.subTest(latest=latest):
                self.assertFalse(release.published(self.registry(latest_manifest=latest), "1.104.5"))

    def test_single_architecture_or_non_index_requires_retry(self):
        for index in [{}, {"manifests": INDEX["manifests"][:1]}]:
            with self.subTest(index=index):
                self.assertFalse(release.published(self.registry(version_manifest=(DIGEST, index)), "1.104.5"))

    def test_attestation_manifest_does_not_count_as_target_platform(self):
        index = {"manifests": [INDEX["manifests"][0], {"platform": {"os": "unknown", "architecture": "unknown"}}]}
        self.assertFalse(release.published(self.registry(version_manifest=(DIGEST, index)), "1.104.5"))

    def test_new_release_does_not_require_existing_registry_artifact(self):
        with patch.object(release, "Registry", side_effect=AssertionError("must not query")):
            self.assertTrue(release.needs_update("1.102.5", "1.104.5", IMAGE))

    def test_equal_source_version_retries_missing_publication(self):
        with patch.object(release, "Registry", return_value=self.registry(version_manifest=None)):
            self.assertTrue(release.needs_update("1.104.5", "1.104.5", IMAGE))

    def test_equal_source_version_and_complete_artifact_are_current(self):
        with patch.object(release, "Registry", return_value=self.registry()):
            self.assertFalse(release.needs_update("1.104.5", "1.104.5", IMAGE))

    def test_registry_outage_is_an_error_not_a_healthy_noop(self):
        registry = Mock(manifest=Mock(side_effect=RuntimeError("HTTP 503")))
        with patch.object(release, "Registry", return_value=registry):
            with self.assertRaisesRegex(RuntimeError, "503"):
                release.needs_update("1.104.5", "1.104.5", IMAGE)

    def test_downgrades_and_invalid_versions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "downgrade"):
            release.needs_update("1.104.5", "1.102.5", IMAGE)
        for value in ["latest", "v1.104.5", "1.105.0-beta", "1.104.5/other"]:
            with self.subTest(version=value), self.assertRaises(ValueError):
                release.version_parts(value)


if __name__ == "__main__":
    unittest.main()
