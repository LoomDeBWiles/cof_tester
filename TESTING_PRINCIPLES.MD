# Testing Best Practices for AI Agents

## Testing Philosophy

Tests exist to give you confidence to change code. A test that doesn't increase confidence is waste. A missing test that would catch real bugs is a liability.

**The goal is not maximum coverage—it's maximum confidence per line of test code.**

## Core Principles

- **Test Public Interfaces:** Only test the public API of a module. Testing private methods couples tests to implementation details.
- **Isolation:** Unit tests must not depend on external systems (network, DB, file system). Mock boundaries, not internals.
- **Determinism:** A test must pass or fail the same way every time.

## What to Test

### Always Test
- Core logic and calculations
- State transitions and workflows
- Edge cases you've actually encountered or can reasonably anticipate
- Integrations at boundaries (API contracts, database queries, external services)
- Security-sensitive paths (auth, permissions, input validation)

### Skip Testing
- Trivial getters/setters with no logic
- Framework code (test your code, not theirs)
- Implementation details that could change without affecting behavior

### Test Priority
Ask: "If this test didn't exist and the code broke, how bad would it be?"
- Catastrophic (data loss, security breach, money) → Must have tests
- Annoying (broken UI, wrong message) → Should have tests
- Trivial (formatting, logging) → Test if free, skip if not

## Bugs and Regression Tests

**When you find a bug, write a test that fails because of it before fixing it.** This ensures:
1. You understand the bug
2. Your fix actually works
3. It never regresses

Sometimes a regression test isn't worth it:
- A typo in UI copy or comments
- A one-time data correction with no logic change
- A bug in third-party code you can't control
- A scenario that can't be reproduced deterministically

## How to Write Tests

### Test Behavior, Not Implementation

```python
# Bad: testing implementation
def test_user_list_uses_cache():
    service.get_users()
    assert cache.get.called_once()

# Good: testing behavior
def test_get_users_returns_active_users_only():
    create_user(active=True, name="Alice")
    create_user(active=False, name="Bob")
    result = service.get_users()
    assert result == [{"name": "Alice"}]
```

### One Concept Per Test

Each test should verify one logical thing. If a test fails, you should know exactly what broke.

### Arrange-Act-Assert

Every test has three parts. Keep them visually distinct.

```python
def test_discount_applied_to_premium_members():
    # Arrange
    user = create_user(membership="premium")
    cart = create_cart(user, items=[{"price": 100}])
    
    # Act
    total = cart.calculate_total()
    
    # Assert
    assert total == 90  # 10% premium discount
```

### Naming

```python
# Vague
def test_user():

# Specific
def test_user_with_expired_subscription_cannot_access_premium_content():
```

### Keep Tests Simple

- **No logic in tests:** Avoid loops and conditionals. Logic in tests creates bugs in tests.
- **Hardcoded expected values:** Use `expected = 4` not `expected = 2 + 2`.
- **No shared mutable state:** Each test runs independently, in any order.

## The Testing Pyramid

Write more tests at the bottom, fewer at the top:

- **Unit tests**: Fast, isolated, test logic. Write lots of these.
- **Integration tests**: Test components working together. Database, APIs, file systems.
- **E2E tests**: Test full user flows. Slow, brittle. Only for critical paths.

When a bug could be caught at a lower level, add the test there instead.

### Property-Based Tests

For parsers, encoders, and transformations, example-based tests aren't enough:

```python
from hypothesis import given, strategies as st

@given(st.text())
def test_encode_decode_roundtrip(s):
    assert decode(encode(s)) == s
```

Use when: roundtrips should preserve data, sorting should stay sorted, idempotent operations should be idempotent.

## Avoiding Bloat

**Delete tests that don't earn their keep:** trivial tests, duplicate coverage, flaky tests.

**Use factories, not fixtures:**

```python
def create_user(membership="free", verified=False):
    return User(id=uuid4(), membership=membership, verified=verified)
```

**Parameterize similar tests:**

```python
@pytest.mark.parametrize("input,expected", [
    ("", False),
    ("short", False),
    ("validpassword123", True),
])
def test_password_validation(input, expected):
    assert is_valid_password(input) == expected
```

**If you're mocking everything, refactor the code.** If you need to mock 5 dependencies to test one function, that function has too many responsibilities.

**Mock at the boundary, not inside.** Mock external services, not your own classes. If you mock something, you should be able to describe the contract in one sentence.

**Prefer fakes over mocks when behavior matters.** Mocks verify calls were made. Fakes verify behavior works.

**Snapshot tests:** Use sparingly, only for large outputs hard to assert field by field. Avoid snapshotting volatile fields (timestamps, IDs).

## Flaky Tests

A flaky test is worse than no test—it provides unreliable signal and masks real failures.

Common fixes:
- **Timing issues**: Mock time, use explicit waits instead of sleeps
- **Shared state**: Isolate tests, clean up properly
- **External dependencies**: Mock them or use containers with known state
- **Race conditions**: Make deterministic or delete the test

## Checklist

- [ ] Each test verifies one behavior
- [ ] Test names describe what's being tested
- [ ] Tests are independent
- [ ] No implementation details tested
- [ ] Setup is minimal
- [ ] No flaky tests
- [ ] Bug fixes include regression tests