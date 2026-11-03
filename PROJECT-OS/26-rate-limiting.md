# RATE LIMITING

The application must respect the limits of every external service it talks to.

Handle: `429` responses, `Retry-After` headers, provider-specific limit headers.

Use: backoff, jitter, local request throttling / queuing.

Never build a mechanism intended to bypass or evade a provider's rate limits or terms of service.
