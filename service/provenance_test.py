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

import datetime
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# Some runtime dependencies are not installed in the local shell, so provide the
# minimal stubs required for importing the audio module under test.
config_module = types.ModuleType('config')
config_module.OUTPUT_SUBTITLES_TYPE = 'vtt'
config_module.OUTPUT_SPEECH_FILE = 'speech.wav'
config_module.OUTPUT_MUSIC_FILE = 'music.wav'
config_module.GENERATE_ASSETS_PROMPT = ''
config_module.GENERATE_ASSETS_SEPARATOR = '|'
config_module.GENERATE_ASSETS_PATTERN = ''
config_module.CONFIG_DEFAULT_SAFETY_CONFIG = {}
config_module.KEY_FRAMES_PROMPT = ''
config_module.OUTPUT_COMBINATION_ASSETS_DIR = 'assets'
config_module.DEVICE = 'cpu'
config_module.CONFIG_TRANSCRIPTION_MODEL_WHISPER_GCS_BUCKET = ''
config_module.CONFIG_TRANSCRIPTION_MODEL_WHISPER = ''
config_module.OUTPUT_SUBTITLES_TYPE = 'vtt'
sys.modules.setdefault('config', config_module)

utils_module = types.ModuleType('utils')
utils_module.execute_subprocess_commands = lambda *args, **kwargs: ''
utils_module.get_media_duration = lambda *args, **kwargs: 0

class _DummyTranscriptionService:  # pragma: no cover - test stub only
  GEMINI = 'gemini'
  WHISPER = 'whisper'

utils_module.TranscriptionService = _DummyTranscriptionService
sys.modules.setdefault('utils', utils_module)

storage_module = types.ModuleType('storage')
storage_module.download_gcs_dir = lambda *args, **kwargs: 0
storage_module.upload_gcs_dir = lambda *args, **kwargs: None
sys.modules.setdefault('storage', storage_module)

vertexai_module = types.ModuleType('vertexai')
vertexai_module.generative_models = types.ModuleType('vertexai.generative_models')
vertexai_module.generative_models.GenerativeModel = object
vertexai_module.generative_models.Part = object
sys.modules.setdefault('vertexai', vertexai_module)
sys.modules.setdefault('vertexai.generative_models', vertexai_module.generative_models)

faster_whisper_module = types.ModuleType('faster_whisper')
faster_whisper_module.WhisperModel = object
sys.modules.setdefault('faster_whisper', faster_whisper_module)

iso639_module = types.ModuleType('iso639')
iso639_module.languages = types.SimpleNamespace(get=lambda alpha2: types.SimpleNamespace(name='English'))
sys.modules.setdefault('iso639', iso639_module)

pandas_module = types.ModuleType('pandas')
pandas_module.DataFrame = object
sys.modules.setdefault('pandas', pandas_module)

import provenance

import audio.audio as audio_service


class ProvenanceTest(unittest.TestCase):

  def test_unsigned_asset_has_disclosure_and_hash(self):
    with tempfile.NamedTemporaryFile(suffix='.png') as asset_file:
      asset_file.write(b'asset')
      asset_file.flush()
      with patch.dict(os.environ, {}, clear=False):
        os.environ.pop('CONFIG_C2PA_ENABLED', None)
        os.environ.pop('CONFIG_C2PA_REQUIRED', None)

        result = provenance.apply_provenance(asset_file.name)

    self.assertEqual(result['type'], 'none')
    self.assertEqual(result['status'], 'unsigned')
    self.assertEqual(len(result['sha256']), 64)
    self.assertTrue(result['disclosure'])

  def test_parse_vtt_timestamp_without_milliseconds(self):
    self.assertEqual(
        audio_service._parse_vtt_timestamp('00:01:23'),
        datetime.timedelta(minutes=1, seconds=23),
    )

  def test_empty_vtt_does_not_raise_when_combining_subtitles(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      subtitles_path = os.path.join(temp_dir, 'chunk.vtt')
      with open(subtitles_path, 'w', encoding='utf-8') as subtitle_file:
        subtitle_file.write('WEBVTT\n\n')

      output_path = os.path.join(temp_dir, 'combined.vtt')
      audio_service.combine_subtitle_files(temp_dir, output_path)

      with open(output_path, 'r', encoding='utf-8') as output_file:
        self.assertEqual(output_file.read(), 'WEBVTT\n\n')

  def test_unsupported_asset_type_is_rejected(self):
    with tempfile.NamedTemporaryFile(suffix='.txt') as asset_file:
      with self.assertRaises(ValueError):
        provenance._mime_type(asset_file.name)

  def test_required_signing_rejects_unconfigured_signer(self):
    with tempfile.NamedTemporaryFile(suffix='.png') as asset_file:
      with patch.dict(os.environ, {'CONFIG_C2PA_REQUIRED': 'true'}, clear=False):
        with self.assertRaisesRegex(RuntimeError, 'C2PA is required'):
          provenance.apply_provenance(asset_file.name)

  def test_runtime_disclosure_is_resolved_from_environment(self):
    with tempfile.NamedTemporaryFile(suffix='.png') as asset_file:
      asset_file.write(b'asset')
      asset_file.flush()
      with patch.dict(os.environ, {'CONFIG_AI_DISCLOSURE': 'runtime disclosure'}, clear=False):
        self.assertEqual(
            provenance.apply_provenance(asset_file.name)['disclosure'],
            'runtime disclosure',
        )

  def test_format_vtt_timestamp_supports_hours(self):
    self.assertEqual(
        audio_service._format_vtt_timestamp(83.456),
        '00:01:23.456',
    )


if __name__ == '__main__':
  unittest.main()
