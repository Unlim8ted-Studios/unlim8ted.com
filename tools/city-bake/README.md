# City Descent Bake

The homepage looks for these baked files:

- `frontend/resources/video/city-descent-desktop.webm`
- `frontend/resources/video/city-descent-tablet.webm`
- `frontend/resources/video/city-descent-mobile.webm`

Run a static server from `frontend` first:

```powershell
python -m http.server 8080 -d frontend
```

Capture frames:

```powershell
node tools/city-bake/bake-city.js all
```

Desktop timing is adjusted in `tools/city-bake/bake-city.js`: output frames 1-36 hold the scroll position that previously produced frame 36, then frame 37 continues forward from there.

Encode:

```powershell
New-Item -ItemType Directory -Force -Path frontend/resources/video

ffmpeg -y -framerate 30 -i tools/city-bake/desktop/frame-%04d.png `
  -c:v libvpx-vp9 -pix_fmt yuv420p -b:v 0 -crf 28 -g 1 `
  frontend/resources/video/city-descent-desktop.webm

ffmpeg -y -framerate 30 -i tools/city-bake/tablet/frame-%04d.png `
  -c:v libvpx-vp9 -pix_fmt yuv420p -b:v 0 -crf 30 -g 1 `
  frontend/resources/video/city-descent-tablet.webm

ffmpeg -y -framerate 24 -i tools/city-bake/mobile/frame-%04d.png `
  -c:v libvpx-vp9 -pix_fmt yuv420p -b:v 0 -crf 32 -g 1 `
  frontend/resources/video/city-descent-mobile.webm
```

Use `CITY_BAKE_URL` if the local server runs somewhere else:

```powershell
$env:CITY_BAKE_URL="http://127.0.0.1:5173"; node tools/city-bake/bake-city.js desktop
```
