# Authentication and sessions

How people sign in to the panel and the field app, how a session stays alive, and how it ends.
AI assistants authenticate differently (personal API keys or OAuth): see
[MCP server and OAuth](mcp-and-oauth.md).

## Roles

A person is a row in `tenant_users` with one role (`backend/app/core/deps.py`):

| Role | Can |
|---|---|
| `super_admin` | Run the hosted service: create and suspend companies. Has no company (`tenant_id` is null; a check constraint allows that only for this role) |
| `tenant_admin` | Everything in their company: team, document types, channels, settings, AI keys |
| `approver` | Review, correct, approve, reject and resend reports |
| `viewer` | Read reports |
| `technician` | Capture reports in the field app and read and confirm their own, nothing else |

The route guards are small functions in `deps.py` (`require_tenant_member`, `require_company_user`,
`require_approver`, `require_capturer`, `require_tenant_admin`, `require_super_admin`,
`require_instance_admin`). `technician` is deliberately not in `TENANT_ROLES`, so every route
guarded by the panel roles refuses technicians without having to say so. Routes that admit
technicians (`require_company_user`, `require_capturer`) must still keep them to their own reports
(`visible_report`, `own_reports_only` in `backend/app/api/admin/reports.py`).

`require_instance_admin` is whoever runs the installation's settings: the company's
`tenant_admin` on a self-hosted server, the `super_admin` on the hosted service.

## Ways in

| Who | How | Endpoint | Lifetime |
|---|---|---|---|
| Panel users | Email and password (bcrypt, cost 12) | `POST /auth/login` | — |
| Technicians | Emailed link, or the same sign-in as an 8-character code typed in the installed app | `POST /auth/magic-link`, then `POST /auth/magic` | 15 minutes; an invitation 7 days |
| Anyone with a password | Reset link by email | `POST /auth/forgot-password`, `POST /auth/reset-password` | 1 hour |
| The first administrator of a self-hosted server | One-time setup code printed by the installer | `/setup/*` (`backend/app/api/setup.py`) | 24 hours |

All in `backend/app/api/auth.py` unless noted. Details that matter:

- **Technicians have no password.** `login` refuses the `technician` role even if the account
  still holds one from an earlier role. A technician on an iPhone may not be able to open the
  link in the installed app, which is why the email also carries the code.
- **Single-use tokens are stored as hashes.** Reset links, invitations and magic links live in
  `password_reset_tokens` as SHA-256 hashes with a `purpose` (`reset` or `magic`), so a reset link
  never signs anyone in and a sign-in link never sets a password. Issuing a new one invalidates
  every outstanding one for that person (`backend/app/services/notifications/tokens.py`).
- **The code alphabet** has no `0`, `O`, `1`, `I` or `L`; case, spaces and the dash don't matter
  when it is typed (`typed_code`, `hash_typed_code` in `backend/app/services/sender_invites.py`).
- **The same answer for everyone.** `forgot-password` and `magic-link` answer with the same message
  whether the address exists or not, and email failures don't change it. A technician who asks for
  a password reset gets a sign-in link instead.
- **The setup code** is 12 characters, stored as a hash, and required before anyone can create the
  first company and administrator on a fresh server (`backend/app/services/setup.py`). Without it,
  the first visitor of a just-installed server would become its administrator.

### Rate limits

Attempts are counted in Postgres (`rate_limit_hits`), so every API process and every restart share
one count (`AttemptLimiter` in `backend/app/core/rate_limit.py`):

| Limit | Key | Attempts | Window |
|---|---|---|---|
| Failed logins | email | 5 | 15 min (reset on success) |
| Failed logins | IP | 30 | 15 min |
| Password reset requests | email / IP | 5 / 20 | 1 hour |
| Magic-link requests | email / IP | 5 / 20 | 1 hour |
| Wrong typed codes | email | 5 | 15 min; the fifth also kills the code that is out there |
| Wrong setup codes | IP | 10 | 15 min |

A limit answers 429 with `Retry-After`. Check and record are separate statements, so a burst of
simultaneous attempts can overshoot a limit by a few (the `ponytail:` note on `AttemptLimiter`);
routes where overshooting costs money use `claim`, which serializes on an advisory lock.

## Tokens

A successful sign-in returns a pair of JWTs signed with `SECRET_KEY` (HS256,
`backend/app/core/security.py`; `tokens_for` in `auth.py`):

| Token | Claims | Lifetime |
|---|---|---|
| Access | `sub`, `role`, `tenant_id`, `ver`, `type=access`, `jti`, `iat`, `exp` | `ACCESS_TOKEN_EXPIRE_MINUTES` (60) |
| Refresh | `sub`, `ver`, `type=refresh`, `jti`, `iat`, `exp` | `REFRESH_TOKEN_EXPIRE_DAYS` (7); `TECHNICIAN_REFRESH_DAYS` (30) for technicians |

Technicians get the longer refresh token on purpose: signing in again in front of a site, gloves
on, is what the field app must spare them. Because refresh tokens rotate, "30 days" means 30 days
after the last use.

### What every request checks

`get_current_user` (`backend/app/core/deps.py`) accepts a request only when:

1. it carries `Authorization: Bearer <access token>` that decodes and has `type=access` (a refresh
   token can't be used as an access token);
2. the user exists and `can_sign_in` is true: the account is active and so is its company (a
   suspended company ends every session of its people at once);
3. the token's `ver` equals the user's current `token_version`;
4. for the read-only demo account (`DEMO_USER_EMAIL`), the method is `GET`, `HEAD` or `OPTIONS`.

The user and company are read from the database on every request, so a change takes effect on the
next request, not when the token expires.

### Refresh rotation

`POST /auth/refresh` with the refresh token in the body:

1. `_use_refresh_token` decodes it and inserts its `jti` into `used_refresh_tokens` with
   `ON CONFLICT DO NOTHING`. Only the first insert succeeds, so a refresh token works exactly once,
   even when two tabs refresh at the same moment.
2. The user must still match `ver` and pass `can_sign_in`.
3. A new pair is returned; the old refresh token is now spent.

`POST /auth/logout` spends the refresh token the same way, so signing out also ends the session on
the server. The worker deletes `used_refresh_tokens` rows once their token would have expired.

> **Note:** a spent refresh token presented again is refused, but the session it belonged to is not
> revoked. That differs from the OAuth refresh tokens issued to AI assistants, where reuse revokes
> the whole grant (see [MCP server and OAuth](mcp-and-oauth.md#token-lifecycle)).

## The session in the browser

The panel and field app keep both tokens in cookies, `reportai_token` and `reportai_refresh`,
written by the app with `SameSite=Strict` and `Secure` (unless the installation is reached over
plain HTTP and sets `NUXT_PUBLIC_SECURE_COOKIES=false`) (`frontend/app/composables/useApi.ts`).
The refresh cookie's `maxAge` is 400 days, the longest browsers keep a cookie: the server alone
decides when a session ends, and an expired token left in the cookie is simply refused.

The cookies are written by the app's own code, so they are not `HttpOnly`; the per-response nonce
in the Content Security Policy (`frontend/server/utils/securityHeaders.ts`) is what keeps an
injected script from running.

`useApi` attaches the access token to every request and, on a 401, renews once and retries:

- **One renewal at a time** per app instance (and per request during server-side rendering): a
  refresh token works once, so the several requests a page fires when the access token expires
  share a single refresh.
- **No coverage is not a signed-out session.** If the renewal gets no answer at all, the error
  propagates and the session is kept; ending it would send a technician in a basement back to their
  email for a new link.
- **Another tab may have renewed first.** On a refused renewal, the app re-reads the cookies; if
  they hold a different refresh token, another tab already rotated it and the request is retried
  with the new one.

The OAuth consent page (`/oauth/consent`) renders in the browser only (`nuxt.config.ts`,
`routeRules`): the AI assistant sends the browser there from its own site, and `SameSite=Strict`
cookies are not sent on that cross-site navigation, so the server-side render can't see the
session.

## Ending sessions

There is no session table. Every way of ending sessions works by incrementing
`tenant_users.token_version`, which invalidates every access and refresh token issued before:

| Action | Where | Also |
|---|---|---|
| Change password | `POST /auth/change-password` | This session gets a fresh pair |
| Reset password | `POST /auth/reset-password` | — |
| Change a member's role, or deactivate them | `PATCH /team/{member_id}` (`backend/app/api/admin/team.py`) | — |
| **Sign out everywhere** | `POST /team/{member_id}/sign-out` (company admin) | Revokes all their API keys and OAuth grants for good |
| `reportai password-link EMAIL` | `backend/app/cli.py` | A one-hour link; setting the new password signs the person out everywhere |

"Sign out everywhere" is for a lost or shared phone: the person can sign in again (a technician
with a new link), unlike deactivation. Their API keys and connected AI apps are revoked rather than
suspended, because a stolen session may have created them.

## Tests

`backend/tests/test_auth.py`, `backend/tests/test_magic_link.py`,
`backend/tests/test_password_reset.py`, `backend/tests/test_technician_role.py`,
`backend/tests/test_team.py`, `backend/tests/test_rate_limit.py`,
`backend/tests/test_tenant_suspension.py`; in the frontend, `frontend/tests/session.test.ts`.
