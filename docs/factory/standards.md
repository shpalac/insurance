# Engineering standards

Use minimal, modular changes and deterministic tests; do not modify unrelated modules. Add focused negative-path coverage, input validation, and useful error diagnostics. Apply project tooling declared in the repository adapter once a product stack exists.

Do not remove or skip passing tests to make CI green. Never reduce security policies or check requirements in a Developer PR. Protected-path changes require separate maintainer review and authorization.
