// Render video/index.html frame by frame and encode it with the soundtrack.
//
//   node tools/render.mjs                    full render → out/<name>.mp4
//   node tools/render.mjs --layout landscape 16:9 version (1920×1080)
//   node tools/render.mjs --stills 3,12.5    PNG stills → build/stills/
//   node tools/render.mjs --cues             only write build/cues.json
//
// Frames are deterministic: the page exposes seek(t), and each frame is a
// screenshot after seeking, so the result does not depend on render speed.
import { spawn } from "node:child_process";
import { createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = resolve(fileURLToPath(import.meta.url), "../..");
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i < 0 ? d : args[i + 1]; };
const FPS = +opt("--fps", 30);
const LAYOUT = opt("--layout", "portrait");
const [W, H] = LAYOUT === "landscape" ? [1920, 1080] : [1080, 1920];
const OUT = opt("--out", join(ROOT, "out", `leo-explains-rea-${LAYOUT}.mp4`));

const TYPES = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json",
  ".png": "image/png", ".webp": "image/webp", ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml" };

function serve() {
  const server = createServer((req, res) => {
    const path = normalize(join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname)));
    if (!path.startsWith(ROOT) || !existsSync(path) || statSync(path).isDirectory()) {
      res.writeHead(404).end(); return;
    }
    res.writeHead(200, { "content-type": TYPES[extname(path)] || "application/octet-stream" });
    createReadStream(path).pipe(res);
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

const server = await serve();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
page.on("pageerror", (e) => { console.error("page error:", e); process.exitCode = 1; });
await page.goto(`http://127.0.0.1:${server.address().port}/video/index.html?layout=${LAYOUT}`);
await page.evaluate(() => window.ready);
const duration = await page.evaluate(() => window.DURATION);
writeFileSync(join(ROOT, "build", "cues.json"), JSON.stringify(await page.evaluate(() => window.CUES)));

async function frame(t, type = "jpeg") {
  await page.evaluate(async (t) => { window.seek(t); await document.fonts.ready; }, t);
  return page.screenshot(type === "jpeg" ? { type, quality: 94 } : { type });
}

if (args.includes("--stills")) {
  mkdirSync(join(ROOT, "build", "stills"), { recursive: true });
  for (const t of opt("--stills").split(",").map(Number)) {
    writeFileSync(join(ROOT, "build", "stills", `${LAYOUT}-t${t.toFixed(2)}.png`), await frame(t, "png"));
  }
  console.log("stills written");
} else if (!args.includes("--cues")) {
  mkdirSync(resolve(OUT, ".."), { recursive: true });
  const audio = join(ROOT, "build", "soundtrack.wav");
  const ff = spawn("ffmpeg", [
    "-y", "-loglevel", "error",
    "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    ...(existsSync(audio) ? ["-i", audio, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest"] : []),
    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
    "-movflags", "+faststart", OUT,
  ], { stdio: ["pipe", "inherit", "inherit"] });
  const total = Math.ceil(duration * FPS);
  const t0 = Date.now();
  for (let i = 0; i < total; i++) {
    const buf = await frame(i / FPS);
    if (!ff.stdin.write(buf)) await new Promise((ok) => ff.stdin.once("drain", ok));
    if (i % (FPS * 5) === 0) console.log(`frame ${i}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end();
  await new Promise((ok, bad) => ff.on("close", (c) => (c ? bad(new Error("ffmpeg " + c)) : ok())));
  console.log("wrote", OUT);
}

await browser.close();
server.close();
