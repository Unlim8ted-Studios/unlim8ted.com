import {
  onAuthStateChanged,
  signOut,
  sendEmailVerification,
  deleteUser,
} from "https://www.gstatic.com/firebasejs/9.22.2/firebase-auth.js";

import {
  doc,
  getDoc,
  setDoc,
  deleteDoc,
} from "https://www.gstatic.com/firebasejs/9.22.2/firebase-firestore.js";

import { getFirebase } from "/components/firebase-init.js";

const { auth, db } = getFirebase();
const $ = (id) => document.getElementById(id);

const MAX_USERNAME_LEN = 80;
const MAX_PIC_LEN = 600;
const SIGNIN_URL = "https://unlim8ted.com/sign-in";
const HOME_URL = "https://unlim8ted.com";
const PRODUCTS_URL = "https://unlim8ted.com/products";
const VERIFY_COOLDOWN_MS = 60_000;

let currentUserData = {};
let modalResolver = null;
let verifyCooldownUntil = 0;

const displayNameEl = $("displayName");
const emailEl = $("email");
const profilePicEl = $("profilePic");
const avatarFallbackEl = $("avatarFallback");
const usernameEl = $("username");
const photoUrlEl = $("photoUrl");
const statusEl = $("status");
const nameHintEl = $("nameHint");
const urlHintEl = $("urlHint");
const verifiedBadgeEl = $("verifiedBadge");
const verifyTextEl = $("verifyText");

function setStatus(msg, isError = false){
  statusEl.textContent = msg || "";
  statusEl.style.color = isError ? "rgba(255,120,120,.95)" : "rgba(233,231,255,.72)";
}

function basicSanitize(s){
  return (s || "").trim().replace(/\s+/g, " ");
}

function clampText(s, max){
  s = (s || "").trim();
  return s.length > max ? s.slice(0, max) : s;
}

function getInitial(nameOrEmail){
  const s = String(nameOrEmail || "U").trim();
  return (s[0] || "U").toUpperCase();
}

function setAvatarFallback(label){
  avatarFallbackEl.textContent = getInitial(label);
}

function setProfileImage(url, fallbackLabel){
  setAvatarFallback(fallbackLabel);

  profilePicEl.classList.remove("broken");

  if (!url){
    profilePicEl.removeAttribute("src");
    profilePicEl.classList.add("broken");
    return;
  }

  profilePicEl.src = url;
}

profilePicEl.addEventListener("error", () => {
  profilePicEl.classList.add("broken");
});

profilePicEl.addEventListener("load", () => {
  profilePicEl.classList.remove("broken");
});

function isValidHttpUrl(url){
  if (!url) return true;
  if (url.length > MAX_PIC_LEN) return false;

  try{
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:";
  }catch{
    return false;
  }
}

function updateHints(){
  nameHintEl.textContent = `${(usernameEl.value || "").length}/${MAX_USERNAME_LEN}`;
  urlHintEl.textContent = `${(photoUrlEl.value || "").length}/${MAX_PIC_LEN}`;
}

function getFirebaseErrorMessage(err, fallback){
  const code = err?.code || "";

  const messages = {
    "auth/requires-recent-login": "For security, please log out and sign in again before deleting your account.",
    "auth/too-many-requests": "Too many requests. Please wait and try again.",
    "auth/network-request-failed": "Network error. Check your connection and try again.",
    "permission-denied": "Permission denied. Check your Firestore rules.",
  };

  return messages[code] || fallback || "Something went wrong.";
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
  $("modalTitle").textContent = title;
  $("modalMessage").textContent = message;
  $("modalIcon").textContent = icon;
  $("modalConfirm").textContent = confirmText;
  $("modalCancel").textContent = cancelText;
  $("modalCancel").hidden = !showCancel;

  const fieldsEl = $("modalFields");
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

  $("modalBackdrop").hidden = false;

  setTimeout(() => {
    const firstInput = fieldsEl.querySelector("input");
    if (firstInput) firstInput.focus();
    else $("modalConfirm").focus();
  }, 0);

  return new Promise((resolve) => {
    modalResolver = resolve;
  });
}

function closeModal(confirmed){
  const values = {};

  $("modalFields").querySelectorAll("input").forEach((input) => {
    values[input.id] = input.value;
  });

  $("modalBackdrop").hidden = true;

  if (modalResolver){
    modalResolver({ confirmed: Boolean(confirmed), values });
    modalResolver = null;
  }
}

async function showNotice(title, message, icon = "✓"){
  return openModal({ title, message, icon, confirmText: "OK" });
}

async function showError(title, message){
  return openModal({ title, message, icon: "!", confirmText: "OK" });
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

function updateVerificationUI(user){
  if (!user){
    verifiedBadgeEl.textContent = "Signed out";
    verifiedBadgeEl.className = "badge muted";
    verifyTextEl.textContent = "Not signed in.";
    return;
  }

  if (user.emailVerified){
    verifiedBadgeEl.textContent = "Verified email";
    verifiedBadgeEl.className = "badge";
    verifyTextEl.textContent = "Your email is verified.";
    $("verifyBtn").disabled = true;
    $("verifyBtn").textContent = "Verified";
  }else{
    verifiedBadgeEl.textContent = "Email not verified";
    verifiedBadgeEl.className = "badge unverified";
    verifyTextEl.textContent = "Verify your email to unlock protected account features.";
    $("verifyBtn").disabled = false;
    $("verifyBtn").textContent = "Send Email";
  }
}

function fillUI(user, data){
  currentUserData = data || {};

  const username = (data?.username || "").toString().trim();
  const name = (data?.name || "").toString().trim();
  const title = username || name || user.displayName || "User";
  const email = user.email || data?.email || "—";
  const pic = (data?.profilePicture || user.photoURL || "").toString().trim();

  displayNameEl.textContent = title;
  emailEl.textContent = email;

  usernameEl.value = username;
  photoUrlEl.value = (data?.profilePicture || "").toString();

  setProfileImage(pic, title || email);
  updateVerificationUI(user);
  updateHints();
}

async function ensureUserDocExists(user){
  const ref = doc(db, "users", user.uid);
  const snap = await getDoc(ref);

  if (!snap.exists()){
    const payload = {
      name: clampText(basicSanitize(user.displayName || ""), 80),
      email: (user.email || "").trim().slice(0, 254),
      profilePicture: clampText((user.photoURL || "").trim(), MAX_PIC_LEN),
    };

    await setDoc(ref, payload);
  }

  const snap2 = await getDoc(ref);
  return snap2.data() || {};
}

async function refreshUser(){
  const user = auth.currentUser;
  if (!user) return null;

  await user.reload();
  updateVerificationUI(auth.currentUser);

  return auth.currentUser;
}

async function sendVerification(){
  const user = auth.currentUser;
  if (!user) return;

  await refreshUser();

  if (auth.currentUser?.emailVerified){
    await showNotice("Already Verified", "Your email is already verified.", "✓");
    return;
  }

  const now = Date.now();

  if (now < verifyCooldownUntil){
    const seconds = Math.ceil((verifyCooldownUntil - now) / 1000);
    await showNotice("Wait a Moment", `Please wait ${seconds} seconds before sending another verification email.`, "⏳");
    return;
  }

  try{
    setStatus("Sending verification email…");

    await sendEmailVerification(auth.currentUser, {
      url: "https://unlim8ted.com/sign-in",
      handleCodeInApp: false,
    });

    verifyCooldownUntil = Date.now() + VERIFY_COOLDOWN_MS;

    setStatus("Verification email sent.");
    await showNotice("Verification Email Sent", "Check your inbox for the verification link.", "✉");
  }catch(e){
    console.error("Verification email error:", e);
    setStatus("Could not send verification email.", true);
    await showError("Verification Failed", getFirebaseErrorMessage(e, "Could not send verification email."));
  }
}

async function saveProfile(){
  const user = auth.currentUser;
  if (!user) return;

  const username = clampText(basicSanitize(usernameEl.value), MAX_USERNAME_LEN);
  const profilePicture = clampText(photoUrlEl.value.trim(), MAX_PIC_LEN);

  if (!isValidHttpUrl(profilePicture)){
    setStatus("Profile photo URL must be http(s) and within limits.", true);
    return;
  }

  try{
    setStatus("Saving…");

    await setDoc(
      doc(db, "users", user.uid),
      {
        username: username || "",
        profilePicture: profilePicture || "",
      },
      { merge: true }
    );

    const snap = await getDoc(doc(db, "users", user.uid));
    fillUI(user, snap.data());

    setStatus("Saved");
    setTimeout(() => setStatus(""), 1200);
  }catch(e){
    console.error("Profile save error:", e);
    setStatus("Failed to save profile. Check Firestore rules.", true);

    await showError(
      "Profile Save Failed",
      "Your current Firestore update rule may have a typo: it allows the key `username`, but validates `request.resource.data.name`. Fix that rule if saving username fails."
    );
  }
}

async function deleteAccount(){
  const user = auth.currentUser;
  if (!user) return;

  const firstConfirm = await showConfirm(
    "Delete Account?",
    "This permanently deletes your login account. This cannot be undone.",
    "Continue"
  );

  if (!firstConfirm) return;

  const result = await openModal({
    title: "Confirm Deletion",
    message: "Type DELETE to permanently delete your account.",
    icon: "!",
    confirmText: "Delete Account",
    cancelText: "Cancel",
    showCancel: true,
    fields: [
      {
        id: "delete-confirm",
        label: "Type DELETE",
        type: "text",
        placeholder: "DELETE",
        autocomplete: "off",
      },
    ],
  });

  if (!result.confirmed) return;

  if ((result.values["delete-confirm"] || "").trim() !== "DELETE"){
    await showError("Deletion Cancelled", "You must type DELETE exactly to delete your account.");
    return;
  }

  try{
    setStatus("Deleting account…");

    try{
      await deleteDoc(doc(db, "users", user.uid));
    }catch(e){
      console.warn("User Firestore doc delete failed. Continuing with Auth delete:", e);
    }

    await deleteUser(user);

    await showNotice("Account Deleted", "Your account has been deleted.", "✓");
    window.location.href = HOME_URL;
  }catch(e){
    console.error("Delete account error:", e);

    const message = getFirebaseErrorMessage(
      e,
      "Could not delete account. You may need to log out, sign back in, and try again."
    );

    setStatus(message, true);
    await showError("Delete Failed", message);
  }
}

usernameEl.addEventListener("input", () => {
  usernameEl.value = clampText(basicSanitize(usernameEl.value), MAX_USERNAME_LEN);
  updateHints();
});

photoUrlEl.addEventListener("input", () => {
  photoUrlEl.value = clampText(photoUrlEl.value.trim(), MAX_PIC_LEN);
  updateHints();

  const url = photoUrlEl.value.trim();

  if (url && isValidHttpUrl(url)){
    setProfileImage(url, usernameEl.value || emailEl.textContent);
  }

  if (!url){
    setProfileImage("", usernameEl.value || emailEl.textContent);
  }
});

onAuthStateChanged(auth, async (user) => {
  if (!user){
    window.location.href = SIGNIN_URL;
    return;
  }

  try{
    setStatus("Loading profile…");

    await user.reload();

    const data = await ensureUserDocExists(auth.currentUser);
    fillUI(auth.currentUser, data);

    setStatus("");
  }catch(e){
    console.error("Profile load error:", e);
    setStatus("Could not load profile.", true);
  }
});

$("saveBtn").addEventListener("click", saveProfile);

$("resetPhotoBtn").addEventListener("click", () => {
  photoUrlEl.value = "";
  setProfileImage("", usernameEl.value || emailEl.textContent);
  updateHints();
});

$("verifyBtn").addEventListener("click", sendVerification);

$("productsBtn").addEventListener("click", () => {
  window.location.href = PRODUCTS_URL;
});

$("logoutBtn").addEventListener("click", async () => {
  try{
    await signOut(auth);
    window.location.href = HOME_URL;
  }catch(e){
    console.error(e);
    setStatus("Logout failed.", true);
  }
});

$("deleteBtn").addEventListener("click", deleteAccount);

$("modalClose").addEventListener("click", () => closeModal(false));
$("modalCancel").addEventListener("click", () => closeModal(false));
$("modalConfirm").addEventListener("click", () => closeModal(true));

$("modalBackdrop").addEventListener("click", (e) => {
  if (e.target.id === "modalBackdrop") closeModal(false);
});

document.addEventListener("keydown", (e) => {
  const backdrop = $("modalBackdrop");
  if (!backdrop || backdrop.hidden) return;

  if (e.key === "Escape") closeModal(false);
  if (e.key === "Enter") closeModal(true);
});

const y = new Date().getFullYear();
$("footerText").innerHTML = `&copy; 2019-${y} Unlim8ted Studio Productions. All rights reserved.`;