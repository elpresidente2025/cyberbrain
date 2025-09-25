# Naver Login Integration (Clean Flow)

This project implements a clean, deterministic Naver OAuth2 login and registration flow that matches the six rules requested.

## Summary

- Login button → Redirects to Naver OAuth (name, gender, age, profile_image scopes).
- Callback page calls Cloud Function to determine membership by `naverUserId`.
- Existing member → Dashboard.
- New member → Register page with Naver consent popup and name prefilled.
- After registration → Redirect to Login page to sign in via Naver again.
- Account deletion → Deletes user profile, posts, bio. (Username mapping can be deleted if desired — see note.)

## Environment Setup

Frontend (`frontend/.env`):

```
VITE_NAVER_CLIENT_ID=_E0OZLvkgp61fV7MFtND
# Optional: override, otherwise defaults to `${origin}/auth/naver/callback`
VITE_NAVER_REDIRECT_URI=https://your-domain/auth/naver/callback
```

Cloud Functions secrets (prefer secrets over .env):

```
firebase functions:secrets:set NAVER_CLIENT_ID
firebase functions:secrets:set NAVER_CLIENT_SECRET
```

Or for local emulators, set environment variables:

```
set NAVER_CLIENT_ID=_E0OZLvkgp61fV7MFtND
set NAVER_CLIENT_SECRET=GZStmR1dwa
```

## Endpoints

- `POST naverLoginHTTP` (Cloud Function)
  - Request: `{ accessToken }` OR `{ code, state }`
  - Response:
    - Existing: `{ result: { success: true, registrationRequired: false, user, naver } }`
    - New: `{ result: { success: true, registrationRequired: true, user: null, naver } }`

- `POST naverCompleteRegistration` (Cloud Function)
  - Request: `{ naverUserData: { id, name, ... }, profileData: { name, position, regionMetro, regionLocal, electoralDistrict, ... } }`
  - Creates Firestore `users/{uid}` with `naverUserId` and `provider='naver'`
  - Returns success; frontend redirects to `/login` for final Naver sign-in

## Frontend Flow

1) User clicks Naver login → SDK opens Naver consent and redirects to `/auth/naver/callback`.
2) Naver callback page parses `access_token` or `code` and calls `naverLoginHTTP`.
3) If `registrationRequired=true` → navigate to `/register` with `naverUserData` and show consent popup; prefill name.
4) Submit registration → call `naverCompleteRegistration` → show success → redirect to `/login` → user clicks Naver login again.
5) If existing user → save minimal session info in `localStorage` and redirect to `/dashboard`.

## Deletion Behavior

`deleteUserAccount` removes:
- Firestore `posts` by `userId`
- Firestore `bio` by `userId`
- Firestore `usernames/{username}` mapping (if owned by the user)
- Firestore `users/{uid}` document

## Local Development

- CORS allows `http://localhost:5173` (Vite), `http://127.0.0.1:5173`, and `http://localhost:3000`.
- Ensure `VITE_NAVER_CLIENT_ID` is set in `frontend/.env` and Functions secrets or env vars are set.

## Mapping to the 6 Rules

1. Existing member → `naverLoginHTTP` finds `users` by `naverUserId` → Dashboard.
2. New member → Naver consent (SDK scope) → `registrationRequired=true` → Register page, consent popup.
3. Register → Name is prefilled from `naverUserData.name`.
4. After signup → Redirect to `/login` → User logs in via Naver.
5. Account deletion → All user data removed as above (extendable to username mapping).
6. Re-join → Flow always checks only existence of `naverUserId` on login.
