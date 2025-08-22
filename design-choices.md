# Design Choices

## Authentication Implementation Decision

I evaluated various auth implementation. Build your own oauth server vs using third party vendors. After spending an hour researching through various choices, using third party vendors seems to be the right option. Reasons:

1. Auth is hard. If done wrong it is catastrophic.
2. Auth is not the core service of this business. It's better to reduce code that is not related to your business logic.
3. Adding new auth features (if at all we get there) is even harder (think SCIM, SSO, 2FA, recovery email, etc).
4. For the expected number of users, Auth0 is cheap. If and when we expand to millions of users, we may need to reevaluate using third party vendors. Until then third party vendors are fast.
5. As they say, friends don't let friends roll out user management services.  Having led development of Identity Infra at Grammarly, I fully subscribe to this saying.
