#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const profiles = {
  desktop: { width: 1920, height: 1080, fps: 30, seconds: 8, startAtFrame: 36, holdFrames: 36},
  tablet: { width: 1280, height: 720, fps: 30, seconds: 8, startAtFrame: 36, holdFrames: 36},
  mobile: { width: 720, height: 1280, fps: 24, seconds: 8, startAtFrame: 36, holdFrames: 36}
};

const profileName = process.argv[2] || "all";
const baseUrl = process.env.CITY_BAKE_URL || "http://127.0.0.1:8080";
const outRoot = path.resolve(process.cwd(), "tools", "city-bake");

async function main(){
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (error) {
    console.error("Missing dependency: playwright");
    console.error("Install it in this repo or globally, then run this script again.");
    process.exit(1);
  }

  const names = profileName === "all" ? Object.keys(profiles) : [profileName];
  for (const name of names) {
    if (!profiles[name]) {
      throw new Error(`Unknown profile "${name}". Use desktop, tablet, mobile, or all.`);
    }
  }

  const browser = await chromium.launch();
  try {
    for (const name of names) {
      await bakeProfile(browser, name, profiles[name]);
    }
  } finally {
    await browser.close();
  }
}

async function bakeProfile(browser, name, profile){
  const frames = profile.fps * profile.seconds;
  const outDir = path.join(outRoot, name);
  fs.mkdirSync(outDir, { recursive: true });

  const page = await browser.newPage({
    viewport: { width: profile.width, height: profile.height },
    deviceScaleFactor: 1
  });

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.addStyleTag({
    content: `
      site-navbar,
      .noise,
      .cursor,
      .cursor-dot,
      .progress,
      .city-bake-frame {
        display: none !important;
      }
    `
  });
  await page.evaluate(() => {
    document.documentElement.style.scrollBehavior = "auto";
    window.__CITY_BAKE_CAPTURE__ = true;
  });

  const metrics = await page.evaluate(() => {
    const section = document.getElementById("cityDescent");
    const top = section.getBoundingClientRect().top + window.scrollY;
    const max = Math.max(1, section.offsetHeight - window.innerHeight);
    return { top, max };
  });

  for (let i = 0; i < frames; i++) {
    const progress = progressForOutputFrame(i, frames, profile);
    await page.evaluate(({ y }) => window.scrollTo(0, y), {
      y: metrics.top + metrics.max * progress
    });
    await page.waitForTimeout(80);
    await page.locator("#cityDescent .orbital-neon-viewport").screenshot({
      path: path.join(outDir, `frame-${String(i + 1).padStart(4, "0")}.png`),
      animations: "disabled"
    });
  }

  await page.close();
  console.log(`${name}: captured ${frames} frames at ${profile.width}x${profile.height}`);
}

function progressForOutputFrame(outputIndex, totalFrames, profile){
  if (totalFrames <= 1) return 0;

  const startAtFrame = Math.max(1, profile.startAtFrame || 1);
  const holdFrames = Math.max(0, profile.holdFrames || 0);
  const startIndex = Math.min(totalFrames - 1, startAtFrame - 1);

  if (outputIndex < holdFrames) {
    return startIndex / (totalFrames - 1);
  }

  const sourceIndex = Math.min(
    totalFrames - 1,
    startIndex + (outputIndex - holdFrames)
  );
  return sourceIndex / (totalFrames - 1);
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
