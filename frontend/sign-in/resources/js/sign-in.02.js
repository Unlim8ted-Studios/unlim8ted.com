import { initializeApp } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  sendPasswordResetEmail,
  sendEmailVerification,
  setPersistence,
  browserLocalPersistence,
  browserSessionPersistence,
  onAuthStateChanged,
  signOut,
} from "https://www.gstatic.com/firebasejs/9.22.2/firebase-auth.js";

import {
  getFirestore,
  doc,
  setDoc,
  serverTimestamp,
} from "https://www.gstatic.com/firebasejs/9.22.2/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyC8rw6kaFhJ2taebKRKKEA7iLqBvak_Dbc",
  authDomain: "auth.unlim8ted.com",
  projectId: "unlim8ted-db",
  storageBucket: "unlim8ted-db.appspot.com",
  messagingSenderId: "1059428499872",
  appId: "1:1059428499872:web:855308683718237de6e4c5",
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

const DEFAULT_AFTER_LOGIN = "https://unlim8ted.com/profile";
const VERIFY_EMAIL_COOLDOWN_MS = 60_000;

let isCreateMode = false;
let modalResolver = null;
let verificationCooldownUntil = 0;
let authReadyHandled = false;

function getRedirectTarget(){
  const params = new URLSearchParams(window.location.search);
  const redirect = params.get("redirect");

  if (!redirect) return DEFAULT_AFTER_LOGIN;

  try{
    const url = new URL(redirect, window.location.origin);
    if (url.origin === window.location.origin) return url.href;
  }catch(e){
    console.warn("Invalid redirect param:", redirect, e);
  }

  return DEFAULT_AFTER_LOGIN;
}

function redirectAfterLogin(){
  window.location.href = getRedirectTarget();
}

function setStatus(message, tone = ""){
  const status = document.getElementById("auth-status");
  if (!status) return;

  status.textContent = message || "";
  status.className = `auth-status${tone ? ` ${tone}` : ""}`;
}

function getFirebaseErrorMessage(err, fallback){
  const code = err?.code || "";

  const messages = {
    "auth/invalid-email": "That email address does not look valid.",
    "auth/user-disabled": "This account has been disabled.",
    "auth/user-not-found": "No account was found with that email.",
    "auth/wrong-password": "The password is incorrect.",
    "auth/invalid-credential": "The email or password is incorrect.",
    "auth/email-already-in-use": "An account already exists with that email.",
    "auth/weak-password": "Password should be at least 6 characters.",
    "auth/popup-closed-by-user": "The Google sign-in popup was closed before finishing.",
    "auth/cancelled-popup-request": "Another sign-in popup was already open.",
    "auth/network-request-failed": "Network error. Check your connection and try again.",
    "auth/too-many-requests": "Too many attempts. Please wait before trying again.",
    "auth/requires-recent-login": "Please sign in again before doing that.",
  };

  return messages[code] || fallback || "Something went wrong. Please try again.";
}

function openModal({
  title = "Notice",
  message = "",
  icon = "!",
  confirmText = "OK",
  cancelText = "Cancel",
  showCancel = false,
  fields = [],
} = {}){
  const backdrop = document.getElementById("auth-modal-backdrop");
  const titleEl = document.getElementById("modal-title");
  const messageEl = document.getElementById("modal-message");
  const iconEl = document.getElementById("modal-icon");
  const fieldsEl = document.getElementById("modal-fields");
  const confirmBtn = document.getElementById("modal-confirm");
  const cancelBtn = document.getElementById("modal-cancel");

  if (!backdrop || !titleEl || !messageEl || !iconEl || !fieldsEl || !confirmBtn || !cancelBtn){
    console.warn("Auth modal elements are missing.");
    return Promise.resolve({ confirmed: false, values: {} });
  }

  titleEl.textContent = title;
  messageEl.textContent = message;
  iconEl.textContent = icon;
  confirmBtn.textContent = confirmText;
  cancelBtn.textContent = cancelText;
  cancelBtn.hidden = !showCancel;

  fieldsEl.innerHTML = "";

  for (const field of fields){
    const label = document.createElement("label");
    label.htmlFor = field.id;
    label.textContent = field.label;

    const input = document.createElement("input");
    input.id = field.id;
    input.type = field.type || "text";
    input.placeholder = field.placeholder || "";
    input.value = field.value || "";
    input.autocomplete = field.autocomplete || "off";

    fieldsEl.appendChild(label);
    fieldsEl.appendChild(input);
  }

  backdrop.hidden = false;

  const firstInput = fieldsEl.querySelector("input");
  setTimeout(() => {
    if (firstInput) firstInput.focus();
    else confirmBtn.focus();
  }, 0);

  return new Promise((resolve) => {
    modalResolver = resolve;
  });
}

function closeModal(result){
  const backdrop = document.getElementById("auth-modal-backdrop");
  const fieldsEl = document.getElementById("modal-fields");
  const values = {};

  if (fieldsEl){
    fieldsEl.querySelectorAll("input").forEach((input) => {
      values[input.id] = input.value;
    });
  }

  if (backdrop) backdrop.hidden = true;

  if (modalResolver){
    modalResolver({
      confirmed: Boolean(result),
      values,
    });
    modalResolver = null;
  }
}

async function showNotice(title, message, icon = "✓"){
  return openModal({
    title,
    message,
    icon,
    confirmText: "OK",
    showCancel: false,
  });
}

async function showError(title, message){
  return openModal({
    title,
    message,
    icon: "!",
    confirmText: "OK",
    showCancel: false,
  });
}

async function showConfirm(title, message, confirmText = "Continue"){
  const result = await openModal({
    title,
    message,
    icon: "?",
    confirmText,
    cancelText: "Cancel",
    showCancel: true,
  });

  return result.confirmed;
}

async function addUserToFirestore(user){
  await user.reload();
  await user.getIdToken(true);

  console.log("Passed-in UID:", user.uid);
  console.log("Current user:", auth.currentUser);
  console.log("Current UID:", auth.currentUser?.uid);
  console.log("ID token:", await auth.currentUser?.getIdToken());

  const liveUser = auth.currentUser;
  if (!liveUser) throw new Error("No authenticated Firebase user before Firestore write.");

  const userRef = doc(db, "users", liveUser.uid);

  await setDoc(userRef, {
    email: liveUser.email || "",
    name: liveUser.displayName || "",
    profilePicture: liveUser.photoURL || "",
  });
}
async function applyPersistenceFromCheckbox(){
  const remember = document.getElementById("rememberMe")?.checked ?? true;

  await setPersistence(
    auth,
    remember ? browserLocalPersistence : browserSessionPersistence
  );
}

async function resendVerificationEmail(user){
  if (!user) return false;

  const now = Date.now();

  if (now < verificationCooldownUntil){
    const seconds = Math.ceil((verificationCooldownUntil - now) / 1000);

    await showNotice(
      "Wait a Moment",
      `Please wait ${seconds} seconds before requesting another verification email.`,
      "⏳"
    );

    return false;
  }

  await sendEmailVerification(user, {
    url: "https://unlim8ted.com/sign-in",
    handleCodeInApp: false,
  });

  verificationCooldownUntil = Date.now() + VERIFY_EMAIL_COOLDOWN_MS;
  return true;
}

async function requireVerifiedUser(user){
  if (!user) return false;

  try{
    await user.reload();
  }catch(err){
    console.warn("Could not reload user before verification check:", err);
  }

  const freshUser = auth.currentUser;

  if (freshUser?.emailVerified) return true;

  const result = await openModal({
    title: "Verify Your Email",
    message: "Your account exists, but your email is not verified yet. Check your inbox, then sign in again after verifying.",
    icon: "✉",
    confirmText: "Resend Email",
    cancelText: "Sign Out",
    showCancel: true,
  });

  if (result.confirmed){
    try{
      const sent = await resendVerificationEmail(freshUser || user);

      if (sent){
        await showNotice(
          "Verification Email Sent",
          "Check your inbox for the verification link. After verifying, come back and sign in again.",
          "✓"
        );
      }
    }catch(err){
      console.error("Verification email failed:", err);

      await showError(
        "Could Not Send Email",
        getFirebaseErrorMessage(err, "Could not send the verification email. Please wait and try again.")
      );
    }
  }

  await signOut(auth);
  return false;
}

async function handleGoogleSignIn(){
  const ok = await showConfirm(
    isCreateMode ? "Create Account with Google?" : "Continue with Google?",
    "A secure Google sign-in popup will open. After signing in, you’ll be sent back to Unlim8ted.",
    isCreateMode ? "Create with Google" : "Open Google Sign-In"
  );

  if (!ok) return;

  const provider = new GoogleAuthProvider();

  try{
    setStatus("Opening Google sign-in...", "");
    await applyPersistenceFromCheckbox();

    const result = await signInWithPopup(auth, provider);
    await addUserToFirestore(result.user);

    setStatus("Signed in. Redirecting...", "success");
    redirectAfterLogin();
  }catch(err){
    console.error("Google Sign-In error:", err);

    const message = getFirebaseErrorMessage(err, "Failed to sign in with Google.");
    setStatus(message, "error");

    await showError("Google Sign-In Failed", message);
  }
}

async function handleEmailSignIn(email, password){
  await applyPersistenceFromCheckbox();

  setStatus("Signing in...", "");

  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  await addUserToFirestore(userCredential.user);

  const verified = await requireVerifiedUser(userCredential.user);

  if (!verified){
    setStatus("Please verify your email before signing in.", "error");
    return;
  }

  setStatus("Signed in. Redirecting...", "success");
  redirectAfterLogin();
}

async function handleAccountCreation(email, password, confirmPassword){
  if (password.length < 6){
    await showError("Password Too Short", "Your password must be at least 6 characters long.");
    return;
  }

  if (password !== confirmPassword){
    await showError("Passwords Do Not Match", "Please make sure both password fields match.");
    return;
  }

  const ok = await showConfirm(
    "Create Account?",
    `Create a new Unlim8ted account for ${email}?`,
    "Create Account"
  );

  if (!ok) return;

  await applyPersistenceFromCheckbox();

  setStatus("Creating account...", "");

  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  await addUserToFirestore(userCredential.user);

  try{
    await resendVerificationEmail(userCredential.user);
  }catch(err){
    console.error("Initial verification email failed:", err);

    await showError(
      "Account Created, Email Not Sent",
      getFirebaseErrorMessage(
        err,
        "Your account was created, but the verification email could not be sent. Try signing in and resending it."
      )
    );

    await signOut(auth);
    setMode(false);
    setStatus("Account created. Sign in later to resend verification.", "success");
    return;
  }

  await showNotice(
    "Check Your Email",
    "Your account was created. We sent you a verification email. Verify your email before signing in.",
    "✉"
  );

  await signOut(auth);

  setMode(false);
  setStatus("Account created. Check your email to verify it.", "success");
}

async function handlePasswordReset(){
  const currentEmail = document.getElementById("email").value.trim();

  const result = await openModal({
    title: "Reset Password",
    message: "Enter your account email and we’ll send you a secure password reset link.",
    icon: "↺",
    confirmText: "Send Reset Link",
    cancelText: "Cancel",
    showCancel: true,
    fields: [
      {
        id: "reset-email",
        label: "Email address",
        type: "email",
        placeholder: "you@example.com",
        value: currentEmail,
        autocomplete: "email",
      },
    ],
  });

  if (!result.confirmed) return;

  const email = result.values["reset-email"]?.trim();

  if (!email){
    await showError("Email Required", "Enter your email address to receive a reset link.");
    return;
  }

  try{
    setStatus("Sending password reset email...", "");

    await sendPasswordResetEmail(auth, email, {
      url: "https://unlim8ted.com/sign-in",
      handleCodeInApp: false,
    });

    setStatus("Password reset email sent. Check your inbox.", "success");

    await showNotice(
      "Reset Email Sent",
      "Check your inbox for the password reset link. It may take a minute to arrive.",
      "✓"
    );
  }catch(err){
    console.error("Password reset error:", err);

    const message = getFirebaseErrorMessage(
      err,
      "Could not send the reset email. Verify the address and try again."
    );

    setStatus(message, "error");
    await showError("Reset Failed", message);
  }
}

function setMode(createMode){
  isCreateMode = createMode;

  const formMode = document.getElementById("form-mode");
  const submit = document.getElementById("form-submit");
  const toggle = document.getElementById("toggle-text");
  const forgot = document.getElementById("forgot-password-btn");
  const confirmWrap = document.getElementById("confirm-password-wrap");
  const confirmInput = document.getElementById("confirm-password");
  const passwordInput = document.getElementById("password");
  const googleBtn = document.getElementById("google-signin-btn");

  if (googleBtn) {
    const img = googleBtn.querySelector("img");

    // Remove every text node
    [...googleBtn.childNodes]
      .filter(node => node.nodeType === Node.TEXT_NODE)
      .forEach(node => node.remove());

    // Insert one text node after the image
    img.after(
      document.createTextNode(
        createMode
          ? " Create account with Google"
          : " Sign in with Google"
      )
    );
  }

  formMode.textContent = createMode ? "Create Account" : "Sign In";
  submit.textContent = createMode ? "Create Account" : "Sign In";

  toggle.textContent = createMode
    ? "Already have an account? Sign In."
    : "Don't have an account? Create one.";

  forgot.hidden = createMode;
  confirmWrap.hidden = !createMode;

  confirmInput.required = createMode;
  passwordInput.autocomplete = createMode ? "new-password" : "current-password";

  setStatus("");
}

function toggleMode(){
  setMode(!isCreateMode);
}

onAuthStateChanged(auth, async (user) => {
  if (authReadyHandled) return;
  authReadyHandled = true;

  if (!user) return;

  try{
    await user.reload();
  }catch(err){
    console.warn("Could not reload existing user:", err);
  }

  if (auth.currentUser?.emailVerified){
    redirectAfterLogin();
  }
});

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("google-signin-btn")
    .addEventListener("click", handleGoogleSignIn);

  document.getElementById("toggle-text")
    .addEventListener("click", toggleMode);

  document.getElementById("forgot-password-btn")
    .addEventListener("click", handlePasswordReset);

  document.getElementById("modal-close")
    .addEventListener("click", () => closeModal(false));

  document.getElementById("modal-cancel")
    .addEventListener("click", () => closeModal(false));

  document.getElementById("modal-confirm")
    .addEventListener("click", () => closeModal(true));

  document.getElementById("auth-modal-backdrop")
    .addEventListener("click", (e) => {
      if (e.target.id === "auth-modal-backdrop") closeModal(false);
    });

  document.addEventListener("keydown", (e) => {
    const backdrop = document.getElementById("auth-modal-backdrop");
    if (!backdrop || backdrop.hidden) return;

    if (e.key === "Escape") closeModal(false);
    if (e.key === "Enter") closeModal(true);
  });

  document.getElementById("email-signin-form")
    .addEventListener("submit", async (e) => {
      e.preventDefault();

      const email = document.getElementById("email").value.trim();
      const password = document.getElementById("password").value;
      const confirmPassword = document.getElementById("confirm-password").value;

      try{
        if (isCreateMode){
          await handleAccountCreation(email, password, confirmPassword);
        }else{
          await handleEmailSignIn(email, password);
        }
      }catch(err){
        console.error("Auth error:", err);

        const message = getFirebaseErrorMessage(
          err,
          isCreateMode
            ? "Failed to create account. Try again."
            : "Sign-in failed. Check your email and password."
        );

        setStatus(message, "error");
        await showError(isCreateMode ? "Account Creation Failed" : "Sign-In Failed", message);
      }
    });

  setMode(false);

  const y = new Date().getFullYear();
  document.getElementById("footer-text").innerHTML =
    `&copy; 2019-${y} Unlim8ted Studio Productions. All rights reserved.`;
});