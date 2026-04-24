import { FirebaseApp, getApps, initializeApp } from "firebase/app";
import { Auth, getAuth } from "firebase/auth";

/**
 * Client-side Firebase — auth only. Data access goes through the FastAPI
 * backend (see src/lib/api.ts); we never read/write Firestore directly from
 * the browser, by design (firestore.rules denies it anyway).
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

export function getFirebaseApp(): FirebaseApp {
  if (app) return app;
  const existing = getApps()[0];
  app = existing ?? initializeApp(readConfig());
  return app;
}

export function firebaseAuth(): Auth {
  return getAuth(getFirebaseApp());
}
