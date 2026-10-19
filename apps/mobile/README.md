# Navis for Android and iOS

A Capacitor 8 shell around the hosted Navis web app. The app loads your production site
(`server.url`). Sign-in, sessions and the API stay on the server, so web, Android and iOS
always run the same version. The native side adds:

- push notifications for safety alerts and saved-event reminders;
- system-browser Google / Apple sign-in, which returns to the app through a deep link (`navis://auth/callback`);
- location and microphone permissions with clear explanations;
- splash screen, status bar, the Android back button, and an offline screen.

## 1. Deploy the backend and web app first

| Piece | Where | Notes |
|---|---|---|
| API (`apps/api`) | any container host | `Dockerfile` at the repo root; set the env from `apps/api/.env.example` |
| Postgres + Redis | managed services | required once you run more than one API instance |
| Web (`apps/web`) | Vercel / Node host | env from `apps/web/.env.example`; must be **HTTPS** |

Check: `https://<api>/ready` returns 200, and you can sign in on the website.

## 2. Configure the app

1. Pick a permanent app id you own, e.g. `com.yourcompany.navis`.
2. Point the shell at your site and sync:
   ```bash
   cd apps/mobile
   NAVIS_APP_URL=https://app.yourdomain.com NAVIS_APP_ID=com.yourcompany.navis npx cap sync
   ```
3. **iOS:**
   - In `ios/App/App/Info.plist`, replace `app.navis.example` under `WKAppBoundDomains` with your host.
   - In Xcode, add `ios/App/App/PrivacyInfo.xcprivacy` to the **App** target (drag it into the project, tick "App").
4. Icons and splash screens are generated from `assets/`. After changing the artwork, run `npm run assets`.
   Redraw the artwork with `node ../web/scripts/generate-icons.mjs`.

## 3. Sign-in providers

- **Google:** add the redirect URI `https://app.yourdomain.com/api/auth/google/callback`.
- **Apple (required on iOS because Google sign-in is offered):**
  - Enable *Sign in with Apple* for the app id.
  - Create a **Services ID** with return URL `https://app.yourdomain.com/api/auth/apple/callback`.
  - Create a key, then set the `APPLE_*` variables on the web server.

## 4. Push notifications

Navis sends two kinds, both opt-in per account under **Account & privacy**:
- **Safety alerts:** severe weather, disasters and strong earthquakes near the user's city.
- **Event reminders:** saved events starting within 24 hours.

**Android (Firebase Cloud Messaging)**
1. In the Firebase console, create a project and add an Android app with your app id. Download
   `google-services.json` to `android/app/` (git-ignored). The Gradle build picks it up automatically.
2. Go to Project settings → Service accounts → *Generate new private key*. Put the JSON in
   `FCM_SERVICE_ACCOUNT_JSON` (inline, or a file path) and the project id in `FCM_PROJECT_ID` on the API.

**iOS (APNs)**
1. On developer.apple.com, go to Keys → +, enable *Apple Push Notifications service (APNs)* and download the `.p8`.
2. On the API, set `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_PRIVATE_KEY` (the .p8 contents) and `APNS_BUNDLE_ID`
   (your app id). Use `APNS_USE_SANDBOX=true` only for builds run straight from Xcode.
3. In Xcode, under App target → Signing & Capabilities, confirm **Push Notifications** is listed.
   `App/App.entitlements` is already wired in, and Xcode switches it to production for App Store builds.

**Scheduling.** Something must call the jobs every ~15 minutes:
- **Kubernetes:** the `navis-push-jobs` CronJob in `apps/api/k8s/deployment.yaml`.
- **Anywhere else:** a cron running
  ```bash
  curl -X POST -H "X-Internal-Auth: $AUTH_INTERNAL_SECRET" https://<api>/v2/push/jobs/safety_alerts
  ```
  and the same for `event_reminders`.

**Check it works:**
- `GET /v2/push/status` (with the internal secret) shows which platforms are configured.
- In the app, Account & privacy → *Send a test notification*.

## 5. Build and submit

**Android (Play Console)**
1. `npx cap open android` opens Android Studio. Go to *Build → Generate Signed App Bundle*, then upload the `.aab`.
2. **Data safety form:**
   - Collected: email, name, approximate and precise location (app functionality, not shared and not sold), audio (processed, not stored), app interactions, device or other IDs (the push token, only when notifications are on).
   - Encrypted in transit: yes.
   - Users can request deletion in the app (Account & privacy) and on the website.
3. **Account deletion URL:** `https://app.yourdomain.com/support` (explains the in-app delete).
4. **Privacy policy URL:** `https://app.yourdomain.com/privacy`.

**iOS (App Store Connect)** — needs a Mac with Xcode
1. `npx cap open ios`. Set the signing team, bump the version, choose *Product → Archive*, then upload.
2. **App Privacy:** the same answers as `PrivacyInfo.xcprivacy` (no tracking).
3. **Review notes:** give a test account, and mention Sign in with Apple, location (nearby places, local emergency numbers) and the microphone (voice search).
4. **Guideline 4.2 (minimum functionality):** Apple rejects thin website wrappers. Navis brings native sign-in, location, voice, offline handling and live transit. Push alerts and reminders (section 4) are part of that native value; mention them in the review notes.

## Before the first store release

- [ ] Real support email in `NEXT_PUBLIC_SUPPORT_EMAIL`, and have someone qualified review `/privacy` and `/terms`.
- [ ] Restrict the MapTiler key to your domains (MapTiler dashboard → Allowed HTTP origins).
- [ ] Screenshots: phone sizes 6.7"/6.5" (iOS) and phone + 7" tablet (Play).
- [ ] Push credentials set on the API, and the job schedule running (see section 4).
- [ ] Optional: Android App Links / iOS Universal Links (`/.well-known/assetlinks.json`, `apple-app-site-association`).
