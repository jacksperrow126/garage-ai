import { FirebaseApp, getApps, initializeApp } from "firebase/app";
import { Auth, connectAuthEmulator, getAuth } from "firebase/auth";

/**
 * Client-side Firebase — auth only. Data access goes through the FastAPI
 * backend (see src/lib/api.ts); we never read/write Firestore directly from
 * the browser, by design (firestore.rules denies it anyway).
 *
 * In local dev set NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST=localhost:9099
 * (see .env.local.example) and we wire the SDK to the emulator. In prod,
 * leave it unset — the SDK then uses the real Identity Platform backend.
 */

function readConfig() {
  return {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  };
}

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

function getFirebaseApp(): FirebaseApp {
  if (app) return app;
  app = getApps()[0] ?? initializeApp(readConfig());
  return app;
}

export function firebaseAuth(): Auth {
  if (auth) return auth;
  auth = getAuth(getFirebaseApp());
  const emulator = process.env.NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST;
  if (emulator) {
    connectAuthEmulator(auth, `http://${emulator}`, { disableWarnings: true });
  }
  return auth;
}
