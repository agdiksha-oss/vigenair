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

"""C2PA signing and provenance metadata for generated assets."""

import hashlib
import json
import os
import pathlib
import shutil
import tempfile
from typing import Dict, Optional


DISCLOSURE = os.environ.get(
    'CONFIG_AI_DISCLOSURE',
    'This asset was created with generative AI-assisted video editing and '
    'asset generation.',
)

def _c2pa_required() -> bool:
  return os.environ.get('CONFIG_C2PA_REQUIRED', 'false').lower() == 'true'


def _read_secret(name: str) -> str:
  from google.cloud import secretmanager

  client = secretmanager.SecretManagerServiceClient()
  response = client.access_secret_version(request={'name': name})
  return response.payload.data.decode('utf-8')


def _credential(value: str) -> str:
  return _read_secret(value) if value.startswith('projects/') else value


def _sha256(file_path: str) -> str:
  digest = hashlib.sha256()
  with open(file_path, 'rb') as asset_file:
    for chunk in iter(lambda: asset_file.read(1024 * 1024), b''):
      digest.update(chunk)
  return digest.hexdigest()


def _mime_type(file_path: str) -> str:
  suffix = pathlib.Path(file_path).suffix.lower()
  if suffix == '.mp4':
    return 'video/mp4'
  if suffix == '.png':
    return 'image/png'
  if suffix in ('.jpg', '.jpeg'):
    return 'image/jpeg'
  raise ValueError(f'Unsupported provenance asset type: {suffix}')


def _sign(file_path: str, title: str, mime_type: str) -> None:
  from c2pa import Builder, C2paSignerInfo, C2paSigningAlg, Signer

  certificate = _credential(os.environ['CONFIG_C2PA_CERTIFICATE'])
  private_key = _credential(os.environ['CONFIG_C2PA_PRIVATE_KEY'])
  tsa_url = os.environ.get('CONFIG_C2PA_TSA_URL') or None
  manifest = {
      'claim_generator': 'ViGenAiR',
      'title': title,
      'format': mime_type,
      'assertions': [
          {
              'label': 'c2pa.actions',
              'data': {
                  'actions': [
                      {
                          'action': 'c2pa.edited',
                          'softwareAgent': 'ViGenAiR',
                          'description': DISCLOSURE,
                      }
                  ]
              },
          },
          {
              'label': 'stds.schema-org.CreativeWork',
              'data': {
                  '@context': 'https://schema.org',
                  '@type': 'CreativeWork',
                  'description': DISCLOSURE,
              },
          },
      ],
  }
  signer_info = C2paSignerInfo(
      C2paSigningAlg.ES256,
      certificate,
      private_key,
      tsa_url,
  )
  signer = Signer.from_info(signer_info)
  builder = Builder.from_json(json.dumps(manifest))
  temporary_path = f'{file_path}.c2pa'
  try:
    builder.sign_file(file_path, temporary_path, signer)
    os.replace(temporary_path, file_path)
  finally:
    if os.path.exists(temporary_path):
      os.remove(temporary_path)


def apply_provenance(file_path: str) -> Dict[str, str]:
  """Signs an asset when configured and returns its verifiable status."""
  signed = False
  if os.environ.get('CONFIG_C2PA_ENABLED', 'false').lower() == 'true':
    _sign(file_path, pathlib.Path(file_path).name, _mime_type(file_path))
    signed = True
  elif _c2pa_required():
    raise RuntimeError(
        'C2PA is required but CONFIG_C2PA_ENABLED is not true.'
    )

  return {
      'type': 'c2pa' if signed else 'none',
      'status': 'signed' if signed else 'unsigned',
      'disclosure': DISCLOSURE,
      'sha256': _sha256(file_path),
  }
