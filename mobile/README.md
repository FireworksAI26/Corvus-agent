# Corvus mobile (iOS + Android)

A native app built with [Expo](https://expo.dev) / React Native. It's a **client**
for the Corvus agent — the agent itself runs on your computer or server via
`corvus serve`, and this app talks to that HTTP API.

## Prerequisites

- Node 18+ and npm
- The Expo tooling: `npm install -g expo-cli eas-cli` (or use `npx`)
- Corvus running somewhere reachable: `corvus serve --host 0.0.0.0` with an
  `api_token` set (see the repo's `config.yaml` → `server:` block)

## Run in development

```bash
cd mobile
npm install
npm start          # opens Expo Dev Tools; press i (iOS sim) / a (Android)
```

Then in the app's **Connection** panel set:

- **API base URL** —
  - Android emulator → `http://10.0.2.2:8000` (the default; 10.0.2.2 is the host)
  - iOS simulator → `http://localhost:8000`
  - Physical phone → `http://<your-computer-LAN-ip>:8000` (same Wi‑Fi), or a
    tunnel (ngrok/Cloudflare Tunnel) if you're remote
- **API token** — whatever you set for `server.api_token` / `CORVUS_API_TOKEN`

## Build installable apps (App Store / Play Store)

This step must run on **your** machine — it can't be done in a sandbox (iOS
builds require Apple tooling). Expo's cloud builder handles both platforms:

```bash
eas login
eas build:configure
eas build -p ios        # produces an .ipa (needs an Apple Developer account)
eas build -p android    # produces an .aab / .apk
```

Then submit with `eas submit -p ios` / `eas submit -p android`, or install the
Android `.apk` directly for sideloading.

## Notes

- Set a real `bundleIdentifier` / `package` in `app.json` before building.
- Replace `extra.eas.projectId` with your own (created by `eas build:configure`).
- Add real `icon`/`splash` PNG assets and reference them in `app.json` for store builds.
- For production, tighten `server.cors_origins` and always serve the API over HTTPS.
