# Structured handoffs

The future dispatcher must persist a parseable checkpoint containing role, issue/PR, lease epoch, branch, commit SHA, successful checks, failing checks, retry history, and next required action. Receiving agents verify the checkpoint against GitHub and current lease ownership before continuing.

Handoffs must not rely on another worker's chat memory or a mutable copy of a report.
