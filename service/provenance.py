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

import functools
import hashlib
import json
import logging
import os
import pathlib
from typing import Any

_DEFAULT_DISCLOSURE = (
    'This asset was created with generative AI-assisted video editing and '
    'asset generation.'
)


def get_disclosure() -> str:
  """Returns the active AI disclosure configured for the runtime."""
  return os.environ.get('CONFIG_AI_DISCLOSURE', _DEFAULT_DISCLOSURE)


def _get_disclosure() -> str:
  """Backward-compatible alias for runtime disclosure lookup."""
  return get_disclosure()


def _c2pa_required() -> bool:
  """Returns whether C2PA signing is required for rendered assets."""
  return os.environ.get('CONFIG_C2PA_REQUIRED', 'false').lower() == 'true'


@functools.lru_cache(maxsize=None)
def _read_secret(name: str) -> str:
  """Reads a secret value from Secret Manager once per secret path."""
  from google.cloud import secretmanager

  client = secretmanager.SecretManagerServiceClient()
  response = client.access_secret_version(request={'name': name})
  return response.payload.data.decode('utf-8')


@functools.lru_cache(maxsize=None)
def _credential(value: str) -> str:
  """Resolves a secret reference to its value, or returns the literal value."""
  return _read_secret(value) if value.startswith('projects/') else value


def _sha256(file_path: str) -> str:
  """Returns the SHA-256 digest for the provided file."""
  digest = hashlib.sha256()
  with open(file_path, 'rb') as asset_file:
    for chunk in iter(lambda: asset_file.read(1024 * 1024), b''):
      digest.update(chunk)
  return digest.hexdigest()


def _mime_type(file_path: str) -> str:
  """Returns the MIME type for an asset based on its file extension."""
  suffix = pathlib.Path(file_path).suffix.lower()
  if suffix == '.mp4':
    return 'video/mp4'
  if suffix == '.png':
    return 'image/png'
  if suffix in ('.jpg', '.jpeg'):
    return 'image/jpeg'
  raise ValueError(f'Unsupported provenance asset type: {suffix}')


@functools.lru_cache(maxsize=None)
def _get_signer():
  """Lazy-loads and caches the C2PA signer for repeated asset signing."""
  # Lazy-imported to avoid requiring C2PA or Secret Manager in non-signing paths
  # and test runners that exercise provenance metadata without a signer.
  from c2pa import C2paSignerInfo, C2paSigningAlg, Signer

  certificate = _credential(os.environ['CONFIG_C2PA_CERTIFICATE'])
  private_key = _credential(os.environ['CONFIG_C2PA_PRIVATE_KEY'])
  tsa_url = os.environ.get('CONFIG_C2PA_TSA_URL') or None
  signer_info = C2paSignerInfo(
      C2paSigningAlg.ES256,
      certificate,
      private_key,
      tsa_url,
  )
  return Signer.from_info(signer_info)


def _sign(file_path: str, title: str, mime_type: str) -> bool:
  """Signs a media asset with C2PA metadata when configuration is available.

  Args:
    file_path: Path to the asset to sign.
    title: Human-readable title stored in the manifest.
    mime_type: MIME type of the asset.

  Returns:
    True when signing succeeds; False when signing fails and the failure is
    non-fatal.

  Raises:
    RuntimeError: If signing is required and fails.
  """
  disclosure = get_disclosure()
  try:
    from c2pa import Builder

    builder = Builder.from_json(json.dumps({
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
                            'description': disclosure,
                        }
                    ]
                },
            },
            {
                'label': 'stds.schema-org.CreativeWork',
                'data': {
                    '@context': 'https://schema.org',
                    '@type': 'CreativeWork',
                    'description': disclosure,
                },
            },
        ],
    }))
    signer = _get_signer()
    temporary_path = f'{file_path}.c2pa'
    try:
      builder.sign_file(file_path, temporary_path, signer)
      os.replace(temporary_path, file_path)
      return True
    finally:
      if os.path.exists(temporary_path):
        os.remove(temporary_path)
  except Exception as exc:  # pylint: disable=broad-exception-caught
    if _c2pa_required():
      raise RuntimeError(
          'C2PA signing failed while CONFIG_C2PA_REQUIRED is enabled.'
      ) from exc
    logging.exception(
        'C2PA signing failed for %s. Returning failed provenance status.',
        file_path,
    )
    return False


def apply_provenance(file_path: str) -> dict[str, Any]:
  """Signs an asset when configured and returns provenance details.

  Args:
    file_path: Path to the media asset to inspect or sign.

  Returns:
    A dictionary containing the provenance type, status, disclosure, and SHA-256
    digest of the asset.

  Raises:
    RuntimeError: If C2PA signing is marked as required but is disabled or fails.
    ValueError: If the asset extension is unsupported for signing.
  """
  signed = False
  disclosure = _get_disclosure()
  if os.environ.get('CONFIG_C2PA_ENABLED', 'false').lower() == 'true':
    signed = _sign(file_path, pathlib.Path(file_path).name, _mime_type(file_path))
  elif _c2pa_required():
    raise RuntimeError(
        'C2PA is required but CONFIG_C2PA_ENABLED is not true.'
    )

  status = 'signed' if signed else 'unsigned'
  if not signed and os.environ.get('CONFIG_C2PA_ENABLED', 'false').lower() == 'true':
    status = 'failed'

  return {
      'type': 'c2pa' if signed else 'none',
      'status': status,
      'disclosure': disclosure,
      'sha256': _sha256(file_path),
  }
