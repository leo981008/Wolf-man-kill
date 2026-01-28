## 2026-01-28 - [Secure Randomness in Games]
**Vulnerability:** Weak PRNG (Mersenne Twister) used for critical game state (role assignment).
**Learning:** In games with hidden information (like Werewolf), predictable randomness allows cheating.
**Prevention:** Use `random.SystemRandom()` for all game logic affecting hidden state.
