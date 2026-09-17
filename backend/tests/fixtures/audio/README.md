# Voice input fixture provenance

Task 4 intentionally does not check in a human operator recording. Unit tests use synthetic PCM16 arrays
created in `tests/unit/test_voice_input.py`; they exercise endpointing and adapter contracts without making
claims about a person's speech or microphone quality. The offline speech round-trip and real microphone
measurements belong to the Task 8 gate, where the operator can document consent, device, model assets, and
measured word error rate.
