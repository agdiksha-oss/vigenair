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

"""Unit tests for audio service."""

import datetime
import os
import sys
import tempfile
import unittest
from unittest import mock

# Scoped mock for external dependencies during module import
with mock.patch.dict(sys.modules, {
    "config": mock.MagicMock(OUTPUT_SUBTITLES_TYPE="vtt"),
    "faster_whisper": mock.MagicMock(),
    "iso639": mock.MagicMock(),
    "pandas": mock.MagicMock(),
    "storage": mock.MagicMock(),
    "utils": mock.MagicMock(),
    "vertexai": mock.MagicMock(),
    "vertexai.generative_models": mock.MagicMock(),
}):
  project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
  if project_root not in sys.path:
    sys.path.insert(0, project_root)
  from service.audio import audio as audio_service


class AudioTest(unittest.TestCase):

  def test_parse_vtt_timestamp_without_milliseconds(self):
    self.assertEqual(
        audio_service._parse_vtt_timestamp("00:01:23"),
        datetime.timedelta(minutes=1, seconds=23),
    )

  def test_parse_vtt_timestamp_with_milliseconds(self):
    self.assertEqual(
        audio_service._parse_vtt_timestamp("01:23.456"),
        datetime.timedelta(minutes=1, seconds=23, milliseconds=456),
    )

  def test_parse_vtt_timestamp_supports_hours(self):
    self.assertEqual(
        audio_service._parse_vtt_timestamp("02:01:23.456"),
        datetime.timedelta(hours=2, minutes=1, seconds=23, milliseconds=456),
    )

  def test_parse_vtt_timestamp_invalid_format_raises(self):
    with self.assertRaises(ValueError):
      audio_service._parse_vtt_timestamp("invalid")

  def test_empty_vtt_does_not_raise_when_combining_subtitles(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      subtitles_path = os.path.join(temp_dir, "chunk.vtt")
      with open(subtitles_path, "w", encoding="utf-8") as subtitle_file:
        subtitle_file.write("WEBVTT\n\n")

      output_path = os.path.join(temp_dir, "combined.vtt")
      audio_service.combine_subtitle_files(temp_dir, output_path)

      with open(output_path, "r", encoding="utf-8") as output_file:
        self.assertEqual(output_file.read(), "WEBVTT\n\n")

  def test_format_vtt_timestamp_supports_hours(self):
    self.assertEqual(
        audio_service._format_vtt_timestamp(83.456),
        "00:01:23.456",
    )


if __name__ == "__main__":
  unittest.main()
