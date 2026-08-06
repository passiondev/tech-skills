# When to Mock

Mock at **system boundaries** only:

- External APIs — payment, email, anything over the network
- Time and randomness
- Databases — use a real test database where one exists, mock otherwise
- File system — use a temp directory where one will do, mock otherwise

## Designing for mockability

**Pass the boundary in.** A function that constructs its own `StripeClient` cannot be mocked at all; one that takes a `paymentClient` argument is mocked by passing a different one.

**Prefer SDK-style interfaces over generic fetchers.** One specific function per external operation, so each mock returns one shape and no mock has to branch on its arguments.

```typescript
// GOOD: each function is independently mockable
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: one mock has to branch on the endpoint
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```
