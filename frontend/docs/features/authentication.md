# Authentication feature contract

Authentication lives outside the shell on /login, /signup, and /oidc-finish.
It uses one stock Card on the muted canvas; no navigation, PageBar, or Settings
presentation leaks into these routes.

Login has a generic sign-in failure message and a validated same-origin returnTo
so an expired session returns the reader to its Moment. Signup uses the same
safe return destination, validates required values/email/confirmation only,
registers then signs in through the existing session abstraction, and never
encourages duplicate registration after partial success.

Both routes read instance config. Do not show signup until config permits it;
configuration failure is retryable and fails closed. Password signup accepts any
non-empty password because the self-hosted backend does. OIDC can be mixed mode
or OIDC-only. Its normal browser navigation stores returnTo, and oidc-finish
exchanges the one-time ticket exactly once before replacing the route.

Do not expose raw backend detail, provider identity assumptions, or automatic
provisioning promises. Use generic single-sign-on wording. At compact widths,
top-align and tighten the Card for keyboard usability without changing its
hierarchy.

