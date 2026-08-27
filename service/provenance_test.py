# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import tempfile
import unittest

import provenance


class ProvenanceTest(unittest.TestCase):

  def test_unsigned_asset_has_disclosure_and_hash(self):
    with tempfile.NamedTemporaryFile(suffix='.png') as asset_file:
      asset_file.write(b'asset')
      asset_file.flush()
      os.environ.pop('CONFIG_C2PA_ENABLED', None)
      os.environ.pop('CONFIG_C2PA_REQUIRED', None)

      result = provenance.apply_provenance(asset_file.name)

    self.assertEqual(result['type'], 'none')
    self.assertEqual(result['status'], 'unsigned')
    self.assertEqual(len(result['sha256']), 64)
    self.assertTrue(result['disclosure'])

  def test_unsupported_asset_type_is_rejected(self):
    with tempfile.NamedTemporaryFile(suffix='.txt') as asset_file:
      with self.assertRaises(ValueError):
        provenance._mime_type(asset_file.name)

  def test_required_signing_rejects_unconfigured_signer(self):
    with tempfile.NamedTemporaryFile(suffix='.png') as asset_file:
      os.environ.pop('CONFIG_C2PA_ENABLED', None)
      os.environ['CONFIG_C2PA_REQUIRED'] = 'true'

      with self.assertRaisesRegex(RuntimeError, 'C2PA is required'):
        provenance.apply_provenance(asset_file.name)

    os.environ.pop('CONFIG_C2PA_REQUIRED', None)


if __name__ == '__main__':
  unittest.main()
