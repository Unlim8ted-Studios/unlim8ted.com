#!/usr/bin/env python3
"""
Unlim8ted Movie Timeline Editor
===============================

Run this file, then choose any HTML movie with "Load from HTML":

    python movie_editor.py

The editor opens in its own desktop window. HTML is an IMPORT FORMAT ONLY. Importing an
HTML movie converts it into a structured JSON project containing scenes, assets,
node trees, text layers, camera motion, camera-rumble effects, animation clips,
and keyframes. The original HTML source is not embedded in the project JSON and
is not required after the first import.

The editor UI is HTML/CSS/JavaScript hosted inside a pywebview desktop window.
If pywebview is missing, the script installs it on first run unless --no-auto-install is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

APP_VERSION = "1.3.0"
PROJECT_FORMAT = "unlim8ted-movie-project"
ROOT = Path(__file__).resolve().parent
APP_ICON = ROOT / "editor-icon.svg"
APP_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#17191f"/>
<path d="M12 18h40v28H12z" fill="#2a2f3a" stroke="#d7aa4a" stroke-width="3"/>
<path d="M18 24h9v16h-9zM31 24h15v5H31zM31 35h15v5H31z" fill="#d7aa4a"/>
<path d="M11 48h42" stroke="#8fb8ff" stroke-width="4" stroke-linecap="round"/>
</svg>
"""


EDITOR_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="/app-icon.svg" type="image/svg+xml">
<title>Unlim8ted Movie Editor 1.3.0</title>
<style>
:root {
    --bg:#16181d;
    --panel:#20232a;
    --panel2:#282c34;
    --panel3:#313641;
    --line:#3c424d;
    --text:#eef1f5;
    --muted:#9ca5b3;
    --accent:#d7aa4a;
    --accent2:#8fb8ff;
    --danger:#e96a6a;
    --ok:#71c68c;
    --timeline-label:220px;
    --row-h:34px;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Arial,sans-serif;overflow:hidden}
button,input,select,textarea{font:inherit;color:inherit}
button{border:1px solid var(--line);background:var(--panel3);border-radius:6px;padding:7px 10px;cursor:pointer}
button:hover{background:#3a404c}
button.primary{background:#765d2b;border-color:#a98742}
button.primary:hover{background:#876d35}
button.danger{color:#ffdede;border-color:#6f3b3b;background:#432a2a}
button.icon{width:34px;height:32px;padding:0;display:grid;place-items:center}
input,select,textarea{background:#17191e;border:1px solid var(--line);border-radius:5px;padding:6px 7px;min-width:0}
input[type=number]{width:88px}
input[type=range]{padding:0}
hr{border:0;border-top:1px solid var(--line);margin:10px 0}
.hidden{display:none!important}
.muted{color:var(--muted)}
.spacer{flex:1}
.badge{display:inline-flex;align-items:center;gap:4px;font-size:11px;border:1px solid var(--line);border-radius:999px;padding:2px 6px;color:var(--muted)}
#app{height:100%;display:grid;grid-template-rows:46px minmax(0,1fr) 310px}
#toolbar{display:flex;align-items:center;gap:8px;padding:6px 9px;background:#1c1f25;border-bottom:1px solid var(--line);white-space:nowrap;overflow:auto}
#toolbar .brand{font-weight:800;margin-right:10px;letter-spacing:.02em;display:flex;align-items:center;gap:7px}
.toolbarGroup{display:flex;align-items:center;gap:4px;padding:3px;border:1px solid var(--line);background:#15181d;border-radius:7px}
.toolbarGroup button{padding:5px 8px}
.toolbarGroupLabel{font-size:10px;color:var(--muted);padding:0 5px;text-transform:uppercase;letter-spacing:.08em}
.buildBadge{font-size:10px;color:#17191d;background:var(--accent);border-radius:999px;padding:2px 7px;font-weight:900;letter-spacing:.04em}
.shortcutHint{font-size:10px;color:var(--muted);border-left:1px solid var(--line);padding-left:8px;margin-left:2px}
#toolbar .spacer{flex:1}
#dirtyDot{width:8px;height:8px;border-radius:50%;background:transparent}
#dirtyDot.dirty{background:var(--accent)}
#workspace{min-height:0;display:grid;grid-template-columns:250px minmax(420px,1fr) 300px}
.panel{background:var(--panel);min-width:0;min-height:0}
#assetsPanel{border-right:1px solid var(--line);display:grid;grid-template-rows:auto auto minmax(0,1fr)}
#inspectorPanel{border-left:1px solid var(--line);display:grid;grid-template-rows:auto minmax(0,1fr)}
.panelTitle{height:38px;display:flex;align-items:center;gap:7px;padding:0 9px;border-bottom:1px solid var(--line);font-size:13px;font-weight:800}
.panelTitle .spacer{flex:1}
#assetSearchWrap{padding:7px;border-bottom:1px solid var(--line)}
#assetSearch{width:100%}
#assetList{overflow:auto;padding:6px}
.assetCard{display:grid;grid-template-columns:78px minmax(0,1fr) auto;gap:8px;align-items:center;padding:6px;border-radius:6px;border:1px solid transparent;cursor:pointer}
.assetCard:hover,.assetCard.selected{background:var(--panel2);border-color:var(--line)}
.assetCard.selected{border-color:var(--accent)}
.assetThumb{width:76px;height:58px;border:1px solid var(--line);border-radius:5px;background:#13151a;display:block;position:relative;overflow:hidden;color:var(--accent)}
.assetPreviewRoot{position:absolute!important;left:50%!important;top:50%!important;margin:0!important;transform-origin:50% 50%!important;pointer-events:none!important}
.assetBigPreview{height:190px;border:1px solid var(--line);border-radius:7px;background:#121419;position:relative;overflow:hidden;margin:8px 0}
.animClipCard{border:1px solid var(--line);border-radius:6px;padding:7px;margin:6px 0;background:#1a1d23}
.animClipHead{display:flex;gap:6px;align-items:center}.animClipHead b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.animHelp{font-size:11px;color:var(--muted);line-height:1.4;padding:7px;border-left:2px solid var(--accent);background:#191b20;margin:6px 0 9px}
.trackDelete{width:22px;height:22px;padding:0;border:0;background:transparent;color:var(--muted);opacity:.35}.trackLabel:hover .trackDelete{opacity:1}.trackDelete:hover{color:#fff;background:#5a3030}
.assetName{font-size:12px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.assetMeta{font-size:10px;color:var(--muted)}
#center{min-width:0;min-height:0;display:grid;grid-template-rows:minmax(0,1fr) 42px;background:#0f1115}
#previewWrap{position:relative;overflow:hidden;background:#0e1014;display:grid;place-items:center}
#previewStage{position:relative;background:#ece8de;box-shadow:0 0 0 1px #444,0 20px 70px #0008;transform-origin:center center;overflow:hidden}
#previewCamera{position:absolute;inset:0;transform-origin:50% 50%}
.layerWrapper{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform,opacity}
.layerWrapper.selected::after{content:"";position:absolute;inset:-4px;border:1px dashed var(--accent2);pointer-events:none;z-index:999999}
.layerWrapper.locked{pointer-events:none}
.editorNode{box-sizing:border-box}
.editorPseudo{pointer-events:none}
.subtitleOverlay{position:absolute;left:10%;right:10%;bottom:5%;min-height:48px;display:grid;place-items:center;text-align:center;pointer-events:none;z-index:999999}
.subtitleBox{max-width:100%;padding:8px 12px;border-radius:6px;background:#080a0dcc;color:#fff;font:700 28px/1.25 system-ui,sans-serif;text-shadow:0 1px 2px #000;box-shadow:0 0 0 1px #ffffff22}
.subtitleBox:empty{display:none}
.subtitleCueEditor{display:grid;gap:8px;margin-top:8px}
.subtitleCueRow{border:1px solid var(--line);border-radius:6px;background:#181b21;padding:8px;display:grid;gap:7px}
.subtitleCueGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.subtitleCueGrid label{display:grid;gap:3px;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.subtitleCueText{width:100%;min-height:42px;resize:vertical}
#previewHud{position:absolute;left:10px;top:10px;display:flex;gap:6px;pointer-events:none}
#previewHud span{background:#111c;border:1px solid #ffffff22;border-radius:4px;padding:4px 7px;font-size:11px}
#emptyPreview{position:absolute;inset:0;display:grid;place-items:center;color:var(--muted);font-size:14px}
#transport{display:flex;align-items:center;gap:7px;padding:5px 9px;background:#191c22;border-top:1px solid var(--line)}
#transport input[type=range]{flex:1}
#timeReadout{font-variant-numeric:tabular-nums;width:120px;text-align:center;font-size:12px}
#inspectorBody{overflow:auto;padding:9px}
.sectionTitle{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:800;margin:9px 0 6px}
.propGrid{display:grid;grid-template-columns:78px minmax(0,1fr);gap:6px;align-items:center;font-size:12px}
.propGrid label{color:var(--muted)}
.inline2{display:grid;grid-template-columns:1fr 1fr;gap:5px}
#keyframeList{display:flex;flex-direction:column;gap:4px}
.kfRow{display:grid;grid-template-columns:48px 1fr 60px 28px;gap:4px;align-items:center;font-size:11px}
.kfRow input{padding:4px}
.kfRow button{padding:3px}
#timeline{min-height:0;border-top:1px solid var(--line);background:#17191f;display:grid;grid-template-rows:64px minmax(0,1fr)}
#sceneStrip{display:grid;grid-template-columns:var(--timeline-label) minmax(0,1fr);border-bottom:1px solid var(--line);min-width:0}
#sceneStripLabel{padding:8px;border-right:1px solid var(--line);display:flex;align-items:center;gap:6px;font-size:12px;font-weight:800}
#sceneBlocksWrap{overflow:auto;position:relative}
#sceneBlocks{height:63px;display:flex;align-items:stretch;min-width:max-content}
.sceneBlock{height:48px;margin:7px 2px 7px 0;min-width:80px;border:1px solid var(--line);background:#292d35;position:relative;padding:5px 7px;cursor:pointer;overflow:hidden;border-radius:4px}
.sceneBlock.active{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.sceneBlock .num{font-size:9px;color:var(--muted)}
.sceneBlock .name{font-size:11px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#trackArea{min-height:0;overflow:auto;position:relative}
#trackContent{position:relative;min-width:100%}
.trackRow{height:var(--row-h);display:grid;grid-template-columns:var(--timeline-label) minmax(0,1fr);border-bottom:1px solid #2a2e36;font-size:11px}
.trackLabel{display:flex;align-items:center;gap:6px;padding:0 7px;border-right:1px solid var(--line);overflow:hidden;cursor:pointer}
.trackLabel.selected{background:#2f3540}
.trackLabel .typeIcon{width:18px;text-align:center;color:var(--accent)}
.trackLabel .name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
.trackLane{position:relative;background-image:linear-gradient(to right,#ffffff08 1px,transparent 1px);background-size:10% 100%;cursor:pointer}
.trackLane::after{content:"";position:absolute;left:var(--playhead,0%);top:0;bottom:0;width:1px;background:#ef6f6f99;pointer-events:none}
.timelineBar{position:absolute;left:6px;right:6px;top:7px;height:20px;border:1px solid #0006;border-radius:4px;background:#3a4250;color:#dfe6ef;overflow:hidden;pointer-events:none;box-shadow:inset 0 1px 0 #ffffff18}
.timelineBar::before{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,#ffffff16,transparent 55%,#0000001f)}
.timelineBar.selected{outline:1px solid var(--accent);box-shadow:0 0 0 1px #d7aa4a44,inset 0 1px 0 #ffffff18}
.timelineBar.camera{background:#3f596c}.timelineBar.effect{background:#574c68}.timelineBar.animation{background:#66542a}.timelineBar.text{background:#476145}.timelineBar.asset{background:#454f66}
.timelineBar.hiddenLayer{opacity:.35}
.timelineBarLabel{position:relative;z-index:1;display:block;padding:2px 7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:10px;line-height:15px}
.timelineFade{position:absolute;top:0;width:18px;height:100%;z-index:2;pointer-events:none}
.timelineFade.in{left:0;clip-path:polygon(0 100%,100% 100%,0 0);background:#0f111588}
.timelineFade.out{right:0;clip-path:polygon(0 0,100% 0,100% 100%);background:#0f111588}
.timelineClipBlock{position:absolute;top:6px;height:22px;border:1px solid #1b1407;border-radius:4px;background:#83652b;color:#fff1c5;overflow:hidden;pointer-events:none;box-shadow:inset 0 1px 0 #ffffff22}
.timelineClipBlock.selected{outline:1px solid var(--accent);box-shadow:0 0 0 1px #d7aa4a44,inset 0 1px 0 #ffffff22}
.timelineClipBlock.disabled{opacity:.35}
.timelineClipBlock.hiddenLayer{opacity:.35}
.timelineClipBlock::after{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,#ffffff1c,transparent 55%,#00000024)}
.timelineClipName{position:relative;z-index:1;display:block;padding:3px 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:10px;line-height:14px}
.kfDiamond{position:absolute;top:50%;width:9px;height:9px;background:var(--accent);border:1px solid #1a1a1a;transform:translate(-50%,-50%) rotate(45deg);cursor:pointer;z-index:3}
.kfDiamond:hover{background:#ffcf63}
.kfDiamond.selected{background:var(--accent2);box-shadow:0 0 0 2px #8fb8ff44}
#timelineRuler{height:22px;display:grid;grid-template-columns:var(--timeline-label) 1fr;position:sticky;top:0;z-index:5;background:#1d2026;border-bottom:1px solid var(--line)}
#rulerLabel{border-right:1px solid var(--line)}
#rulerLane{position:relative;background:repeating-linear-gradient(to right,#ffffff14 0 1px,transparent 1px 10%)}
#playheadHandle{position:absolute;top:0;bottom:-1000px;width:1px;background:#ef6f6f;left:0;pointer-events:none;z-index:20}
#playheadHandle::before{content:"";position:absolute;left:-5px;top:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:8px solid #ef6f6f}
.modalBackdrop{position:fixed;inset:0;background:#0009;z-index:10000;display:grid;place-items:center}
.modal{width:min(560px,90vw);max-height:80vh;overflow:auto;background:var(--panel);border:1px solid var(--line);box-shadow:0 30px 100px #000b;border-radius:10px}
.modalHeader{padding:12px 14px;font-weight:800;border-bottom:1px solid var(--line)}
.modalBody{padding:14px}
.modalFooter{padding:10px 14px;border-top:1px solid var(--line);display:flex;justify-content:flex-end;gap:7px}
.modal textarea{width:100%;min-height:130px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;resize:vertical}
.fileList{display:flex;flex-direction:column;gap:5px}
.fileChoice{padding:9px;border:1px solid var(--line);border-radius:6px;cursor:pointer;background:#1b1e24}
.fileChoice:hover,.fileChoice.active{border-color:var(--accent);background:#29271f}
.progressBox{padding:12px;border:1px solid var(--line);background:#17191e;border-radius:7px}
.progressBar{height:8px;background:#0e1013;border-radius:999px;overflow:hidden;margin-top:8px}
.progressBar>div{height:100%;width:0;background:var(--accent)}
.toast{position:fixed;right:12px;bottom:12px;z-index:20000;background:#222832;border:1px solid var(--line);padding:9px 12px;border-radius:7px;box-shadow:0 10px 35px #0008;font-size:12px}
#projectViewer{position:fixed;inset:0;z-index:9000;background:#0d0f13;display:grid;grid-template-rows:48px minmax(0,1fr) 54px}
#projectViewer.hidden{display:none!important}
#viewerTop,#viewerTransport{display:flex;align-items:center;gap:8px;padding:8px 12px;background:#191c22;border-bottom:1px solid var(--line)}
#viewerTransport{border-top:1px solid var(--line);border-bottom:0}
#viewerTitle{font-weight:800}
#viewerSceneName{color:var(--muted);font-size:12px}
#viewerFrameWrap{min-height:0;display:grid;place-items:center;overflow:hidden;background:#0b0d10}
#viewerStage{position:relative;background:#ece8de;box-shadow:0 0 0 1px #444,0 26px 90px #000a;overflow:hidden;transform-origin:center center}
#viewerCamera{position:absolute;inset:0;transform-origin:50% 50%}
#viewerProgress{flex:1}
#viewerTime{width:150px;text-align:center;font-size:12px;font-variant-numeric:tabular-nums;color:var(--muted)}
@media(max-width:1000px){#workspace{grid-template-columns:210px minmax(340px,1fr) 260px}:root{--timeline-label:190px}}
</style>
</head>
<body>
<div id="app">
    <div id="toolbar">
        <div class="brand">Unlim8ted Movie Editor <span class="buildBadge">v1.3.0</span></div>
        <div class="toolbarGroup"><span class="toolbarGroupLabel">Project</span><button id="newProjectBtn">New</button><button id="loadHtmlBtn" class="primary">Import HTML</button><button id="mergeReferenceBtn">Merge Ref Animations</button><button id="loadProjectBtn">Open</button><button id="saveBtn">Save</button><button id="saveAsBtn">Save As...</button></div>
        <div class="toolbarGroup"><span class="toolbarGroupLabel">Edit</span><button id="undoBtn" title="Undo (Ctrl+Z)">Undo</button><button id="redoBtn" title="Redo (Ctrl+Y / Ctrl+Shift+Z)">Redo</button><button id="lipSyncBtn">Lip Sync</button><label class="muted" style="display:flex;align-items:center;gap:5px;font-size:11px;padding:0 5px"><input id="autoKeyframeToggle" type="checkbox" checked> Auto keyframe</label></div>
        <div class="toolbarGroup"><span class="toolbarGroupLabel">View</span><button id="projectViewerBtn">Full Project</button></div>
        <span id="dirtyDot"></span>
        <span id="projectName" class="muted">No project</span>
        <span class="shortcutHint">Ctrl+Z Undo - Ctrl+Y Redo - Delete Layer</span>
        <div class="spacer"></div>
        <div class="toolbarGroup"><span class="toolbarGroupLabel">Scene</span><button id="addSceneBtn">+ Scene</button><button id="deleteSceneBtn" class="danger">Delete Scene</button></div>
        <div class="toolbarGroup"><span class="toolbarGroupLabel">Layer</span><button id="deleteLayerBtn" class="danger" title="Delete selected layer (Delete / Backspace)">Delete Layer</button></div>
    </div>

    <div id="workspace">
        <aside id="assetsPanel" class="panel">
            <div class="panelTitle">Assets <span class="badge">LIVE PREVIEWS</span><span class="spacer"></span><button id="newAssetBtn" class="icon" title="New Asset">+</button></div>
            <div id="assetSearchWrap"><input id="assetSearch" placeholder="Search assets..."></div>
            <div id="assetList"></div>
        </aside>

        <main id="center">
            <div id="previewWrap">
                <div id="previewStage">
                    <div id="previewCamera"></div>
                </div>
                <div id="emptyPreview">Load an HTML movie or JSON project.</div>
                <div id="previewHud"><span id="sceneHud">No scene</span><span id="selectionHud">Nothing selected</span></div>
            </div>
            <div id="transport">
                <button id="jumpStartBtn" class="icon"><<</button>
                <button id="playBtn" class="icon">Play</button>
                <button id="jumpEndBtn" class="icon">>></button>
                <input id="timeSlider" type="range" min="0" max="1000" value="0">
                <div id="timeReadout">0.00 / 0.00 s</div>
                <label class="muted" style="font-size:11px">Speed <select id="playSpeed"><option>.25</option><option>.5</option><option selected>1</option><option>2</option></select></label>
            </div>
        </main>

        <aside id="inspectorPanel" class="panel">
            <div class="panelTitle">Inspector</div>
            <div id="inspectorBody"><div class="muted">Select a layer or asset.</div></div>
        </aside>
    </div>

    <section id="timeline">
        <div id="sceneStrip">
            <div id="sceneStripLabel">Scenes <span class="spacer"></span><span id="sceneCount" class="badge">0</span></div>
            <div id="sceneBlocksWrap"><div id="sceneBlocks"></div></div>
        </div>
        <div id="trackArea">
            <div id="timelineRuler"><div id="rulerLabel"></div><div id="rulerLane"><div id="playheadHandle"></div></div></div>
            <div id="trackContent"></div>
        </div>
    </section>
</div>

<iframe id="importFrame" style="position:fixed;left:-20000px;top:0;width:1280px;height:720px;border:0;visibility:hidden"></iframe>
<input id="htmlFileInput" type="file" accept="text/html,.html,.htm" class="hidden">
<input id="projectFileInput" type="file" accept="application/json,.json" class="hidden">
<input id="referenceFileInput" type="file" accept="text/html,.html,.htm" class="hidden">
<input id="audioFileInput" type="file" accept="audio/*" class="hidden">

<section id="projectViewer" class="hidden">
    <div id="viewerTop"><div id="viewerTitle">Project Viewer</div><div id="viewerSceneName"></div><div class="spacer"></div><button id="viewerCloseBtn">Close</button></div>
    <div id="viewerFrameWrap"><div id="viewerStage"><div id="viewerCamera"></div></div></div>
    <div id="viewerTransport"><button id="viewerJumpStartBtn" class="icon"><<</button><button id="viewerPlayBtn" class="icon">Play</button><input id="viewerProgress" type="range" min="0" max="1000" value="0"><div id="viewerTime">0.00 / 0.00 s</div></div>
</section>

<script>
'use strict';

const FORMAT = 'unlim8ted-movie-project';
const FORMAT_VERSION = 1;
const DEFAULT_IMPORT_SAMPLES = 121;
const STYLE_PROPS = [
    'position','display','boxSizing','left','right','top','bottom','width','height','minWidth','minHeight','maxWidth','maxHeight',
    'margin','marginLeft','marginRight','marginTop','marginBottom','padding','paddingLeft','paddingRight','paddingTop','paddingBottom',
    'overflow','overflowX','overflowY','zIndex','visibility','pointerEvents',
    'background','backgroundColor','backgroundImage','backgroundSize','backgroundPosition','backgroundRepeat',
    'border','borderTop','borderRight','borderBottom','borderLeft','borderRadius','boxShadow','outline',
    'color','font','fontFamily','fontSize','fontWeight','fontStyle','lineHeight','letterSpacing','textAlign','textDecoration','textShadow','whiteSpace',
    'opacity','transform','transformOrigin','translate','scale','rotate','filter','clipPath','mixBlendMode',
    'gridTemplateColumns','gridTemplateRows','gap','rowGap','columnGap','placeItems','alignItems','justifyItems','justifyContent','alignContent',
    'flexDirection','flexWrap','flexGrow','flexShrink','flexBasis','alignSelf','justifySelf','objectFit','objectPosition'
];

const state = {
    project: null,
    fileName: '',
    filePath: '',
    currentSceneIndex: 0,
    selectedLayerId: null,
    selectedAssetId: null,
    selectedKeyframe: null,
    selectedKeyframes: [],
    keyframeClipboard: [],
    selectedPartPath: null,
    playhead: 0,
    autoKeyframe: true,
    playing: false,
    lastFrameTime: 0,
    dirty: false,
    drag: null,
    renderCache: new Map(),
    animationCache: new WeakMap(),
    viewer: {open:false, playing:false, sceneIndex:0, time:0, lastFrameTime:0, renderCache:new Map(), animationCache:new WeakMap()},
    assetPreviewAnimations: [],
    history: {undo:[], redo:[], current:null, saved:null, suspended:false, batchBase:null}
};

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const clamp = (v,a,b) => Math.max(a,Math.min(b,v));
const lerp = (a,b,t) => a+(b-a)*t;
const uid = prefix => `${prefix}_${Math.random().toString(36).slice(2,8)}_${Date.now().toString(36)}`;
const deepClone = obj => JSON.parse(JSON.stringify(obj));
const fmt = n => Number.isFinite(+n) ? (+n).toFixed(2).replace(/\.00$/,'') : '0';
const escapeHtml = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function toast(msg, ms=2200){
    const el=document.createElement('div');el.className='toast';el.textContent=msg;document.body.appendChild(el);setTimeout(()=>el.remove(),ms);
}
function projectSnapshot(){return state.project?JSON.stringify(state.project):null}
function updateDirtyIndicator(){
    const snap=projectSnapshot();
    state.dirty=!!state.project && state.history.saved!==snap;
    $('#dirtyDot').classList.toggle('dirty',state.dirty);
    $('#undoBtn').disabled=!state.history.undo.length;
    $('#redoBtn').disabled=!state.history.redo.length;
}
function resetHistory(saved=true){
    const snap=projectSnapshot();
    state.history.undo=[];state.history.redo=[];state.history.current=snap;state.history.saved=saved?snap:null;state.history.suspended=false;state.history.batchBase=null;
    updateDirtyIndicator();
}
function beginHistoryBatch(){
    if(!state.project||state.history.suspended)return;
    state.history.suspended=true;state.history.batchBase=state.history.current??projectSnapshot();
}
function endHistoryBatch(){
    if(!state.history.suspended)return;
    state.history.suspended=false;
    const before=state.history.batchBase,after=projectSnapshot();state.history.batchBase=null;
    if(before!==after){if(before!==null)state.history.undo.push(before);if(state.history.undo.length>120)state.history.undo.shift();state.history.redo=[];state.history.current=after}
    updateDirtyIndicator();
}
function markDirty(v=true){
    if(!state.project){state.dirty=false;$('#dirtyDot').classList.remove('dirty');return}
    if(!v){const snap=projectSnapshot();state.history.current=snap;state.history.saved=snap;updateDirtyIndicator();return}
    if(state.history.suspended){state.dirty=true;$('#dirtyDot').classList.add('dirty');return}
    const after=projectSnapshot(),before=state.history.current;
    if(before!==after){if(before!==null)state.history.undo.push(before);if(state.history.undo.length>120)state.history.undo.shift();state.history.redo=[];state.history.current=after}
    updateDirtyIndicator();
}
function restoreHistorySnapshot(snap){
    state.project=JSON.parse(snap);state.history.current=snap;state.renderCache.clear();state.animationCache=new WeakMap();
    const scene=currentScene();if(!scene){state.currentSceneIndex=0;state.selectedLayerId=null}else if(!scene.layers.some(l=>l.id===state.selectedLayerId))state.selectedLayerId=scene.layers[0]?.id||null;
    state.selectedAssetId=state.selectedAssetId&&state.project.assets[state.selectedAssetId]?state.selectedAssetId:null;
    updateDirtyIndicator();renderAll();
}
function undo(){
    if(!state.history.undo.length)return;const current=projectSnapshot();const prev=state.history.undo.pop();if(current!==null)state.history.redo.push(current);restoreHistorySnapshot(prev);toast('Undo');
}
function redo(){
    if(!state.history.redo.length)return;const current=projectSnapshot();const next=state.history.redo.pop();if(current!==null)state.history.undo.push(current);restoreHistorySnapshot(next);toast('Redo');
}
function currentScene(){return state.project?.scenes?.[state.currentSceneIndex]||null;}
function currentLayer(){const s=currentScene();return s?.layers?.find(l=>l.id===state.selectedLayerId)||null;}
function currentAsset(){return state.project?.assets?.[state.selectedAssetId]||null;}

function emptyProject(name='Untitled Movie'){
    return {
        format: FORMAT,
        version: FORMAT_VERSION,
        meta: {name, createdAt:new Date().toISOString(), modifiedAt:new Date().toISOString(), viewport:{width:1280,height:720}, source:null},
        assets: {},
        animationLibrary: {},
        scenes: [],
        editor: {samples:DEFAULT_IMPORT_SAMPLES}
    };
}
function defaultScene(id=uid('scene'),name='Scene 1'){
    return {id,name,duration:5,layers:[{id:`${id}_camera`,type:'camera',name:'Camera',base:{x:0,y:0,zoom:1,rotation:0,opacity:1},tracks:{},locked:false,hidden:false},{id:`${id}_rumble`,type:'effect',effect:'camera-rumble',name:'Camera Rumble',targetLayerId:`${id}_camera`,base:{x:0,y:0},tracks:{},enabled:true,locked:false,hidden:true}],background:'#ece8de',notes:''};
}

async function api(path, options={}){
    const res=await fetch(path,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
    if(!res.ok){throw new Error((await res.text())||`${res.status}`)}
    const ct=res.headers.get('content-type')||'';
    return ct.includes('application/json')?res.json():res.text();
}

function showModal(title, bodyHtml, buttons=[]){
    return new Promise(resolve=>{
        const back=document.createElement('div');back.className='modalBackdrop';
        back.innerHTML=`<div class="modal"><div class="modalHeader">${escapeHtml(title)}</div><div class="modalBody">${bodyHtml}</div><div class="modalFooter"></div></div>`;
        const footer=back.querySelector('.modalFooter');
        buttons.forEach(b=>{const btn=document.createElement('button');btn.textContent=b.label;btn.className=b.primary?'primary':'';btn.onclick=()=>{if(b.keep){b.onClick?.(back,resolve)}else{back.remove();resolve(b.value)}};footer.appendChild(btn)});
        back.addEventListener('mousedown',e=>{if(e.target===back){back.remove();resolve(null)}});
        document.body.appendChild(back);
    });
}

async function chooseServerFile(kind){
    const data=await api(`/api/files?kind=${encodeURIComponent(kind)}`);
    if(!data.files.length){toast(kind==='html'?'No HTML files found beside the script.':'No saved projects found beside the script.');return null;}
    const body=`<div class="fileList">${data.files.map((f,i)=>`<div class="fileChoice" data-name="${escapeHtml(f.name)}"><b>${escapeHtml(f.name)}</b><div class="muted" style="font-size:11px">${(f.size/1024).toFixed(1)} KB - ${escapeHtml(f.modified)}</div></div>`).join('')}</div>`;
    return new Promise(resolve=>{
        showModal(kind==='html'?'Load from HTML':'Open Project',body,[{label:'Cancel',value:null},{label:'Open',primary:true,keep:true,onClick:(back,res)=>{
            const active=back.querySelector('.fileChoice.active');if(!active){toast('Choose a file.');return}back.remove();res(active.dataset.name);
        }}]).then(resolve);
        setTimeout(()=>$$('.fileChoice').forEach(el=>el.onclick=()=>{$$('.fileChoice').forEach(x=>x.classList.remove('active'));el.classList.add('active')}),0);
    });
}

function progressModal(title){
    const back=document.createElement('div');back.className='modalBackdrop';
    back.innerHTML=`<div class="modal"><div class="modalHeader">${escapeHtml(title)}</div><div class="modalBody"><div class="progressBox"><div id="importStatus">Preparing...</div><div class="progressBar"><div id="importBar"></div></div><div id="importDetail" class="muted" style="font-size:11px;margin-top:7px"></div></div></div></div>`;
    document.body.appendChild(back);
    return {back,set:(pct,msg,detail='')=>{back.querySelector('#importBar').style.width=`${clamp(pct,0,100)}%`;back.querySelector('#importStatus').textContent=msg;back.querySelector('#importDetail').textContent=detail},close:()=>back.remove()};
}

function simpleHash(str){let h=2166136261;for(let i=0;i<str.length;i++){h^=str.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(36)}
function safeName(s){return (s||'').replace(/^seq-/,'').replace(/([a-z0-9])([A-Z])/g,'$1 $2').replace(/[-_]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase()).trim()||'Scene'}

function parseMatrix(str){
    if(!str||str==='none')return{x:0,y:0,scaleX:1,scaleY:1,rotation:0};
    const m=str.match(/matrix\(([^)]+)\)/);
    if(m){const [a,b,c,d,e,f]=m[1].split(',').map(Number);return{x:e||0,y:f||0,scaleX:Math.hypot(a,b)||1,scaleY:Math.hypot(c,d)||1,rotation:Math.atan2(b,a)*180/Math.PI}}
    const m3=str.match(/matrix3d\(([^)]+)\)/);
    if(m3){const v=m3[1].split(',').map(Number);return{x:v[12]||0,y:v[13]||0,scaleX:Math.hypot(v[0],v[1])||1,scaleY:Math.hypot(v[4],v[5])||1,rotation:Math.atan2(v[1],v[0])*180/Math.PI}}
    return{x:0,y:0,scaleX:1,scaleY:1,rotation:0};
}
function parseTranslate(str){
    if(!str||str==='none')return{x:0,y:0};
    const nums=str.match(/-?\d*\.?\d+(?:e[-+]?\d+)?/ig)?.map(Number)||[];
    return{x:nums[0]||0,y:nums[1]||0};
}

function styleObject(win, el, pseudo=null){
    const cs=win.getComputedStyle(el,pseudo);
    const out={};
    STYLE_PROPS.forEach(p=>{let v=cs[p];if(v!==undefined&&v!==''&&v!=='normal'&&v!=='none'&&v!=='0px 0px 0px rgba(0, 0, 0, 0)')out[p]=v});
    const stroke=cs.getPropertyValue('-webkit-text-stroke');if(stroke&&stroke!=='0px rgb(0, 0, 0)')out.WebkitTextStroke=stroke;
    const paint=cs.getPropertyValue('paint-order');if(paint&&paint!=='normal')out.paintOrder=paint;
    return out;
}
function directText(el){return [...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.nodeValue).join('').replace(/\s+/g,' ').trim()}
function isPseudoVisible(win,el,pseudo){
    const cs=win.getComputedStyle(el,pseudo);const content=cs.content;
    if(content==='none'||content===undefined)return false;
    return content==='""'||content==="''"||content.length>0;
}
function cleanPseudoContent(s){if(!s||s==='none')return'';return s.replace(/^['"]|['"]$/g,'')}

function serializeNode(win, el, path='0', isRoot=false){
    const style=styleObject(win,el);
    if(isRoot){
        delete style.left;delete style.right;delete style.top;delete style.bottom;delete style.margin;delete style.marginLeft;delete style.marginRight;delete style.marginTop;delete style.marginBottom;
        delete style.transform;delete style.translate;delete style.rotate;delete style.scale;delete style.opacity;delete style.zIndex;
        style.position='relative';
    }
    const cs=win.getComputedStyle(el);
    const animNames=(cs.animationName||'').split(',').map(s=>s.trim()).filter(s=>s&&s!=='none');
    const node={tag:(el.tagName||'div').toLowerCase(),path,classes:[...el.classList],style,text:directText(el),children:[]};
    if(animNames.length){
        delete node.style.transform;delete node.style.translate;delete node.style.rotate;delete node.style.scale;
        node.nativeAnimations={names:animNames,duration:cs.animationDuration,delay:cs.animationDelay,iterationCount:cs.animationIterationCount,direction:cs.animationDirection,timingFunction:cs.animationTimingFunction};
    }
    [...el.children].forEach((c,i)=>node.children.push(serializeNode(win,c,`${path}.${i}`,false)));
    for(const pseudo of ['::before','::after']){
        if(isPseudoVisible(win,el,pseudo)){
            const ps=styleObject(win,el,pseudo);node.children.push({tag:'div',path:`${path}.${pseudo==='::before'?'b':'a'}`,classes:['editorPseudo',pseudo==='::before'?'before':'after'],style:ps,text:cleanPseudoContent(win.getComputedStyle(el,pseudo).content),pseudo:pseudo.slice(2),children:[]});
        }
    }
    return node;
}

function normalizeAssetForHash(node){
    const n=deepClone(node);
    const transientClasses=new Set(['walking','running','shown','gone','scroll-beat']);
    function walk(x,root=true){
        if(x.style){
            ['transform','translate','scale','rotate','opacity'].forEach(k=>delete x.style[k]);
            if(root)['left','right','top','bottom','zIndex'].forEach(k=>delete x.style[k]);
        }
        if(Array.isArray(x.classes))x.classes=x.classes.filter(c=>!transientClasses.has(c));
        delete x.nativeAnimations;
        delete x.path;
        x.children?.forEach(c=>walk(c,false));
    }
    walk(n,true);return n;
}

function inferAssetName(el, kind){
    const preferred=[...el.classList].filter(c=>!['person','walking','scroll-beat','shown','gone','layer'].includes(c));
    let raw=preferred[0]||el.id||kind||'asset';
    raw=raw.replace(/^p\d+-/,'').replace(/^pace-/,'');
    return safeName(raw);
}
function classifyRoot(el){
    if(el.matches('.speech,.caption,.sound,.chapter-mark'))return'text';
    const hasHead=!!el.querySelector('.head,.face-cover');
    const hasLeg=!!el.querySelector('.leg,.shoe');
    if(el.matches('.person')||(hasHead&&hasLeg))return'character';
    return'asset';
}

function captureElementSample(win,el,stageRect){
    const r=el.getBoundingClientRect();
    const cs=win.getComputedStyle(el);const m=parseMatrix(cs.transform);
    return {x:r.left-stageRect.left,y:r.top-stageRect.top,width:r.width,height:r.height,rotation:m.rotation,scaleX:m.scaleX,scaleY:m.scaleY,opacity:parseFloat(cs.opacity)||0,z:parseFloat(cs.zIndex)||0,visible:cs.visibility!=='hidden'&&cs.display!=='none'};
}
function capturePartSample(win,el){
    const cs=win.getComputedStyle(el);const m=parseMatrix(cs.transform);
    return{x:m.x,y:m.y,scaleX:m.scaleX,scaleY:m.scaleY,rotation:m.rotation,opacity:parseFloat(cs.opacity)||0};
}
function numberClose(a,b,tol){return Math.abs((a||0)-(b||0))<=tol}
function simplifyScalar(points,tol){
    if(points.length<=2)return points;
    const keep=new Set([0,points.length-1]);
    function rec(a,b){
        const p0=points[a],p1=points[b];let best=-1,bestErr=tol;
        for(let i=a+1;i<b;i++){
            const t=(points[i].t-p0.t)/Math.max(1e-9,p1.t-p0.t);const expected=lerp(p0.value,p1.value,t);const err=Math.abs(points[i].value-expected);
            if(err>bestErr){bestErr=err;best=i}
        }
        if(best>=0){keep.add(best);rec(a,best);rec(best,b)}
    }
    rec(0,points.length-1);return [...keep].sort((a,b)=>a-b).map(i=>points[i]);
}
function buildTracks(samples, tolerances={x:.55,y:.55,width:.5,height:.5,rotation:.15,scaleX:.004,scaleY:.004,opacity:.008}){
    const out={};
    for(const prop of Object.keys(tolerances)){
        const pts=samples.map(s=>({t:s.t,value:Number(s[prop]??0),ease:'linear'}));
        const first=pts[0]?.value??0;const varying=pts.some(p=>!numberClose(p.value,first,tolerances[prop]));
        if(varying||prop==='x'||prop==='y'||prop==='opacity')out[prop]=simplifyScalar(pts,tolerances[prop]);
    }
    return out;
}
function tracksVary(tracks){return Object.values(tracks||{}).some(a=>a.length>2||(a.length===2&&Math.abs(a[0].value-a[1].value)>.0001))}

function extractKeyframeLibrary(doc){
    const lib={};
    for(const sheet of [...doc.styleSheets]){
        let rules;try{rules=sheet.cssRules}catch{continue}
        if(!rules)continue;
        for(const rule of [...rules]){
            if(rule.type===7 || rule.constructor?.name==='CSSKeyframesRule'){
                lib[rule.name]={name:rule.name,frames:[...rule.cssRules].map(fr=>{const style={};for(const p of fr.style){style[p]=fr.style.getPropertyValue(p)}return{offset:fr.keyText,style}})};
            }
        }
    }
    return lib;
}

function collectNativeAnimationNames(node,set=new Set()){node.nativeAnimations?.names?.forEach(n=>set.add(n));node.children?.forEach(c=>collectNativeAnimationNames(c,set));return [...set]}
function splitCssList(value){return String(value||'').split(',').map(x=>x.trim())}
function timeToSeconds(value,def=1){const s=String(value||'').trim();if(!s)return def;if(s.endsWith('ms'))return(parseFloat(s)||0)/1000;if(s.endsWith('s'))return parseFloat(s)||0;return parseFloat(s)||def}
const ANIMATION_GROUPS={
    Walking:new Set(['legForward','legBack','armForward','armBack','walkBob']),
    Running:new Set(['runLegA','runLegB','runArmA','runArmB','runBob'])
};
function animationClipNameFor(name){
    for(const [group,names] of Object.entries(ANIMATION_GROUPS))if(names.has(name))return group;
    return name;
}
function collectAssetAnimationClips(node){
    const clips=new Map();
    (function walk(n){
        if(n.nativeAnimations?.names?.length){
            const durs=splitCssList(n.nativeAnimations.duration),delays=splitCssList(n.nativeAnimations.delay),iters=splitCssList(n.nativeAnimations.iterationCount),dirs=splitCssList(n.nativeAnimations.direction),timings=splitCssList(n.nativeAnimations.timingFunction);
            n.nativeAnimations.names.forEach((name,i)=>{
                const clipName=animationClipNameFor(name),duration=timeToSeconds(durs[i]||durs[0],1);
                if(!clips.has(clipName))clips.set(clipName,{id:`clip_${simpleHash(clipName)}`,name:clipName,keyframeNames:[],duration,delay:timeToSeconds(delays[i]||delays[0],0),iterations:(iters[i]||iters[0]||'infinite'),direction:dirs[i]||dirs[0]||'normal',timing:timings[i]||timings[0]||'linear',source:'css-keyframes'});
                const clip=clips.get(clipName);if(!clip.keyframeNames.includes(name))clip.keyframeNames.push(name);clip.duration=Math.max(clip.duration,duration);
            });
        }
        n.children?.forEach(walk);
    })(node);
    return [...clips.values()];
}
function addAnimationClipFromMeta(clips,name,meta,i){
    const durs=splitCssList(meta.duration),delays=splitCssList(meta.delay),iters=splitCssList(meta.iterationCount),dirs=splitCssList(meta.direction),timings=splitCssList(meta.timingFunction);
    const clipName=animationClipNameFor(name),duration=timeToSeconds(durs[i]||durs[0],1);
    if(!clips.has(clipName))clips.set(clipName,{id:`clip_${simpleHash(clipName)}`,name:clipName,keyframeNames:[],duration,delay:timeToSeconds(delays[i]||delays[0],0),iterations:(iters[i]||iters[0]||'infinite'),direction:dirs[i]||dirs[0]||'normal',timing:timings[i]||timings[0]||'linear',source:'css-keyframes'});
    const clip=clips.get(clipName);if(!clip.keyframeNames.includes(name))clip.keyframeNames.push(name);clip.duration=Math.max(clip.duration,duration);
}
function collectAnimationClipsFromPathMeta(nativeByPath){
    const clips=new Map();
    for(const meta of nativeByPath?.values?.()||[])for(const [i,name] of (meta.names||[]).entries())addAnimationClipFromMeta(clips,name,meta,i);
    return [...clips.values()];
}
function nativeAnimationMeta(win,el){
    const cs=win.getComputedStyle(el),names=(cs.animationName||'').split(',').map(s=>s.trim()).filter(s=>s&&s!=='none');
    if(!names.length)return null;
    return {names,duration:cs.animationDuration,delay:cs.animationDelay,iterationCount:cs.animationIterationCount,direction:cs.animationDirection,timingFunction:cs.animationTimingFunction};
}
function mergeAnimationMeta(existing,meta){
    if(!existing)return deepClone(meta);
    const out=deepClone(existing),durations=splitCssList(out.duration),delays=splitCssList(out.delay),iters=splitCssList(out.iterationCount),dirs=splitCssList(out.direction),timings=splitCssList(out.timingFunction);
    const nd=splitCssList(meta.duration),nl=splitCssList(meta.delay),ni=splitCssList(meta.iterationCount),nr=splitCssList(meta.direction),nt=splitCssList(meta.timingFunction);
    meta.names.forEach((name,i)=>{if(out.names.includes(name))return;out.names.push(name);durations.push(nd[i]||nd[0]||'1s');delays.push(nl[i]||nl[0]||'0s');iters.push(ni[i]||ni[0]||'infinite');dirs.push(nr[i]||nr[0]||'normal');timings.push(nt[i]||nt[0]||'linear')});
    out.duration=durations.join(', ');out.delay=delays.join(', ');out.iterationCount=iters.join(', ');out.direction=dirs.join(', ');out.timingFunction=timings.join(', ');return out;
}
function mergeNativeAnimationMeta(node,path,meta){
    const target=findAssetNode(node,path);if(!target||!meta?.names?.length)return;
    if(!target.nativeAnimations){target.nativeAnimations={names:[],duration:'',delay:'',iterationCount:'',direction:'',timingFunction:''}}
    const durations=splitCssList(target.nativeAnimations.duration),delays=splitCssList(target.nativeAnimations.delay),iters=splitCssList(target.nativeAnimations.iterationCount),dirs=splitCssList(target.nativeAnimations.direction),timings=splitCssList(target.nativeAnimations.timingFunction);
    const nd=splitCssList(meta.duration),nl=splitCssList(meta.delay),ni=splitCssList(meta.iterationCount),nr=splitCssList(meta.direction),nt=splitCssList(meta.timingFunction);
    meta.names.forEach((name,i)=>{
        if(target.nativeAnimations.names.includes(name))return;
        target.nativeAnimations.names.push(name);durations.push(nd[i]||nd[0]||'1s');delays.push(nl[i]||nl[0]||'0s');iters.push(ni[i]||ni[0]||'infinite');dirs.push(nr[i]||nr[0]||'normal');timings.push(nt[i]||nt[0]||'linear');
    });
    target.nativeAnimations.duration=durations.join(', ');target.nativeAnimations.delay=delays.join(', ');target.nativeAnimations.iterationCount=iters.join(', ');target.nativeAnimations.direction=dirs.join(', ');target.nativeAnimations.timingFunction=timings.join(', ');
}
function booleanSamplesToKeyframes(samples){
    const out=[];let last=null;
    const sorted=[...samples].sort((a,b)=>a.t-b.t);
    if(sorted.length&&sorted[0].t>.0005&&sorted[0].value)out.push({t:0,value:false,ease:'hold'});
    for(const s of sorted){const value=!!s.value;if(last===null||value!==last){out.push({t:s.t,value,ease:'hold'});last=value}}
    return out;
}
function groupAssetAnimationList(animations){
    const grouped=new Map();
    for(const anim of animations||[]){
        const name=animationClipNameFor(anim.name),rawNames=anim.keyframeNames?.length?anim.keyframeNames:[anim.name];
        if(!grouped.has(name))grouped.set(name,{...deepClone(anim),id:`clip_${simpleHash(name)}`,name,keyframeNames:[],duration:0});
        const target=grouped.get(name);target.duration=Math.max(target.duration||0,anim.duration||1);
        for(const raw of rawNames)if(raw&&!target.keyframeNames.includes(raw))target.keyframeNames.push(raw);
    }
    return [...grouped.values()].map(anim=>{if(anim.keyframeNames.length===1&&anim.keyframeNames[0]===anim.name)delete anim.keyframeNames;return anim});
}
function mergeBooleanClipKeyframes(samples){
    const byTime=new Map();
    for(const k of samples||[]){const t=Math.round((+k.t||0)*1000000)/1000000;byTime.set(t,(byTime.get(t)||false)||!!k.value)}
    return booleanSamplesToKeyframes([...byTime.entries()].map(([t,value])=>({t,value})));
}
function normalizeSceneClipList(clips,asset=null){
    const metaByName=new Map((asset?.animations||[]).flatMap(a=>[[a.name,a],...(a.keyframeNames||[]).map(n=>[n,a])])),grouped=new Map();
    for(const clip of clips||[]){
        const name=animationClipNameFor(clip.name),meta=metaByName.get(name)||metaByName.get(clip.name);
        if(!grouped.has(name))grouped.set(name,{...deepClone(clip),clipId:meta?.id||`clip_${simpleHash(name)}`,name,keyframeNames:[],_activeSamples:[]});
        const target=grouped.get(name),rawNames=clip.keyframeNames?.length?clip.keyframeNames:[clip.name];
        for(const raw of rawNames)if(raw&&!target.keyframeNames.includes(raw))target.keyframeNames.push(raw);
        if(clip.activeKeyframes?.length)target._activeSamples.push(...clip.activeKeyframes);
        target.enabled=target.enabled!==false||clip.enabled!==false;
    }
    return [...grouped.values()].map(clip=>{
        if(clip._activeSamples.length)clip.activeKeyframes=mergeBooleanClipKeyframes(clip._activeSamples);
        delete clip._activeSamples;if(clip.keyframeNames.length===1&&clip.keyframeNames[0]===clip.name)delete clip.keyframeNames;
        return clip;
    });
}
function ensureLayerHasAssetClips(layer,asset){
    if(!layer||!asset?.animations?.length)return;
    const normalized=normalizeSceneClipList(layer.clips||[],asset),byName=new Map(normalized.map(c=>[c.name,c]));
    for(const anim of asset.animations)if(!byName.has(anim.name))byName.set(anim.name,{clipId:anim.id,name:anim.name,keyframeNames:anim.keyframeNames,speed:1,offset:0,loop:true,enabled:true,activeKeyframes:[{t:0,value:false,ease:'hold'}]});
    layer.clips=[...byName.values()];
}
function parseReferenceAssetRegistry(text){
    const source=String(text||''),startDecl=source.search(/\b(?:const|let|var)\s+ASSETS\s*=/);
    if(startDecl<0)return[];
    const start=source.indexOf('[',startDecl);if(start<0)return[];
    let depth=0,inString=false,quote='',escape=false;
    for(let i=start;i<source.length;i++){
        const ch=source[i];
        if(inString){
            if(escape){escape=false;continue}
            if(ch==='\\'){escape=true;continue}
            if(ch===quote){inString=false;quote=''}
            continue;
        }
        if(ch==='"'||ch==="'"){inString=true;quote=ch;continue}
        if(ch==='[')depth++;
        else if(ch===']'){
            depth--;
            if(depth===0){
                const raw=source.slice(start,i+1);
                try{return JSON.parse(raw)}catch(err){console.warn('Reference ASSETS parse failed',err);return[]}
            }
        }
    }
    return[];
}
async function loadReferenceAssetRegistry(sourceText){
    const embedded=parseReferenceAssetRegistry(sourceText);if(embedded.length)return embedded;
    try{const res=await fetch('detective-crumb-asset-reference.html');if(res.ok)return parseReferenceAssetRegistry(await res.text())}catch{}
    return[];
}
function pickReferenceRegistryFile(){
    return new Promise(resolve=>{
        const input=$('#referenceFileInput');if(!input){resolve([]);return}
        input.onchange=async e=>{
            const f=e.target.files?.[0];e.target.value='';
            if(!f){resolve([]);return}
            try{
                const registry=parseReferenceAssetRegistry(await f.text());
                if(!registry.length)alert('That file did not contain a readable ASSETS registry.');
                resolve(registry);
            }catch(err){alert(`Could not read reference file:\n${err.message}`);resolve([])}
        };
        input.click();
    });
}
function directCameraChild(camera,node){let cur=node;while(cur&&cur.parentElement!==camera)cur=cur.parentElement;return cur&&cur.parentElement===camera?cur:null}
function findReferenceAssetForRoot(registry,sceneId,camera,root){
    let best=null,bestScore=-1;
    for(const asset of registry||[]){
        if(!asset.selector)continue;
        let matches=[];try{matches=[...camera.querySelectorAll(asset.selector)]}catch{continue}
        if(!matches.some(node=>directCameraChild(camera,node)===root))continue;
        let score=asset.scene===sceneId?10:0;
        if(asset.kind==='character')score+=3;
        if(root.id&&asset.id&&root.id.toLowerCase().includes(asset.id.toLowerCase()))score+=2;
        if(score>bestScore){best=asset;bestScore=score}
    }
    return best;
}
function resolveReferenceMotion(label){
    const text=String(label||'bob').toLowerCase();
    if(/open|uncover|expand/.test(text))return'open';
    if(/close|retract|shut/.test(text))return'close';
    if(/knock|strike|hit/.test(text))return'knock';
    if(/run|sprint|chase/.test(text))return'run';
    if(/walk|drive|approach|travel|track|glide|roll|search/.test(text))return'walk';
    if(/spin|wheel|dial|washer|turn/.test(text))return'spin';
    if(/shake|impact|snap|honk|jolt|chaos|tug/.test(text))return'shake';
    if(/steam|smoke/.test(text))return'steam';
    if(/ring|tick|voice|sound|wave/.test(text))return'ring';
    if(/reveal|present|appear|pop|eject|in$|slide-in|focus/.test(text))return'reveal';
    if(/fly|flight|scatter|drop|fall|tumble/.test(text))return /fall|tumble|drop/.test(text)?'fall':'fly';
    if(/swing|sway|wobble|tilt|lean/.test(text))return'sway';
    if(/bounce|hop|jump|rebound|recoil|vault/.test(text))return'bounce';
    if(/pulse|flash|flicker|lightning/.test(text))return /flash|flicker|lightning/.test(text)?'flicker':'pulse';
    if(/float|sheet|paper|newspaper/.test(text))return'float';
    if(/point|gesture|reach|grab/.test(text))return'point';
    if(/nod|head/.test(text))return'nod';
    if(/lift|rise/.test(text))return'lift';
    if(/slide|trace|sweep|draw/.test(text))return'slide';
    if(/inspect|read|measure|examine/.test(text))return'inspect';
    return'bob';
}
const REFERENCE_MOTIONS={
    bob:{duration:.9,frames:[{offset:'0%',style:{transform:'translateY(0)'}},{offset:'50%',style:{transform:'translateY(-9px)'}},{offset:'100%',style:{transform:'translateY(0)'}}]},
    walk:{duration:1.15,frames:[{offset:'0%',style:{transform:'translateX(-9px)'}},{offset:'50%',style:{transform:'translateX(9px) translateY(-4px)'}},{offset:'100%',style:{transform:'translateX(-9px)'}}]},
    run:{duration:.55,frames:[{offset:'0%',style:{transform:'translateX(-14px) skewX(-3deg)'}},{offset:'50%',style:{transform:'translateX(14px) translateY(-7px) skewX(3deg)'}},{offset:'100%',style:{transform:'translateX(-14px) skewX(-3deg)'}}]},
    nod:{duration:.8,frames:[{offset:'0%',style:{transform:'rotate(0deg) translateY(0)'}},{offset:'45%',style:{transform:'rotate(3deg) translateY(7px)'}},{offset:'100%',style:{transform:'rotate(0deg) translateY(0)'}}]},
    sway:{duration:1.1,frames:[{offset:'0%',style:{transform:'rotate(-3deg)'}},{offset:'50%',style:{transform:'rotate(3deg)'}},{offset:'100%',style:{transform:'rotate(-3deg)'}}]},
    shake:{duration:.42,frames:[{offset:'0%',style:{transform:'translateX(-3px) rotate(-1deg)'}},{offset:'50%',style:{transform:'translateX(3px) rotate(1deg)'}},{offset:'100%',style:{transform:'translateX(-3px) rotate(-1deg)'}}]},
    spin:{duration:1.1,frames:[{offset:'0%',style:{transform:'rotate(0deg)'}},{offset:'100%',style:{transform:'rotate(360deg)'}}]},
    bounce:{duration:.75,frames:[{offset:'0%',style:{transform:'translateY(0) scale(1)'}},{offset:'45%',style:{transform:'translateY(-16px) scale(1.03,.97)'}},{offset:'100%',style:{transform:'translateY(0) scale(1)'}}]},
    fall:{duration:.7,frames:[{offset:'0%',style:{transform:'translateY(-18px) rotate(-6deg)'}},{offset:'100%',style:{transform:'translateY(18px) rotate(8deg)'}}]},
    fly:{duration:1,frames:[{offset:'0%',style:{transform:'translate(-15px,10px) rotate(-4deg)'}},{offset:'50%',style:{transform:'translate(5px,-14px) rotate(4deg)'}},{offset:'100%',style:{transform:'translate(18px,8px) rotate(-2deg)'}}]},
    flicker:{duration:.55,frames:[{offset:'0%',style:{opacity:'.45'}},{offset:'20%',style:{opacity:'1'}},{offset:'55%',style:{opacity:'.2'}},{offset:'100%',style:{opacity:'1'}}]},
    pulse:{duration:.8,frames:[{offset:'0%',style:{transform:'scale(.96)',opacity:'.75'}},{offset:'50%',style:{transform:'scale(1.05)',opacity:'1'}},{offset:'100%',style:{transform:'scale(.96)',opacity:'.75'}}]},
    steam:{duration:1.4,frames:[{offset:'0%',style:{transform:'translateY(8px) scale(.9)',opacity:'.35'}},{offset:'60%',style:{transform:'translateY(-12px) scale(1.08)',opacity:'.9'}},{offset:'100%',style:{transform:'translateY(-20px) scale(1.15)',opacity:'0'}}]},
    ring:{duration:.45,frames:[{offset:'0%',style:{transform:'scale(1) rotate(-2deg)'}},{offset:'50%',style:{transform:'scale(1.04) rotate(2deg)'}},{offset:'100%',style:{transform:'scale(1) rotate(-2deg)'}}]},
    reveal:{duration:.7,frames:[{offset:'0%',style:{transform:'translateY(12px) scale(.94)',opacity:'0'}},{offset:'100%',style:{transform:'translateY(0) scale(1)',opacity:'1'}}]},
    point:{duration:.75,frames:[{offset:'0%',style:{transform:'rotate(0deg)'}},{offset:'50%',style:{transform:'rotate(-4deg) translateX(8px)'}},{offset:'100%',style:{transform:'rotate(0deg)'}}]},
    lift:{duration:1,frames:[{offset:'0%',style:{transform:'translateY(12px)'}},{offset:'100%',style:{transform:'translateY(-12px)'}}]},
    slide:{duration:1,frames:[{offset:'0%',style:{transform:'translateX(-16px)'}},{offset:'100%',style:{transform:'translateX(16px)'}}]},
    inspect:{duration:1.2,frames:[{offset:'0%',style:{transform:'translateX(-6px) scale(1)'}},{offset:'50%',style:{transform:'translateX(6px) scale(1.03)'}},{offset:'100%',style:{transform:'translateX(-6px) scale(1)'}}]},
    open:{duration:.8,frames:[{offset:'0%',style:{transform:'scaleX(.92)',opacity:'.75'}},{offset:'100%',style:{transform:'scaleX(1)',opacity:'1'}}]},
    close:{duration:.8,frames:[{offset:'0%',style:{transform:'scaleX(1)',opacity:'1'}},{offset:'100%',style:{transform:'scaleX(.92)',opacity:'.75'}}]}
};
function ensureReferenceMotionLibrary(project,motion){
    const key=`refMotion_${motion}`,def=REFERENCE_MOTIONS[motion]||REFERENCE_MOTIONS.bob;
    project.animationLibrary[key]??={name:key,frames:def.frames};
    return {key,duration:def.duration};
}
function applyReferenceAssetMetadata(asset,refAsset,project){
    if(!asset||!refAsset)return;
    asset.reference={id:refAsset.id,selector:refAsset.selector,scene:refAsset.scene,variants:refAsset.variants||[],animations:refAsset.animations||[]};
    asset.name=refAsset.name||asset.name;asset.kind=refAsset.kind||asset.kind;asset.subtype=refAsset.subtype||asset.subtype;
    const root=asset.node;if(!root.nativeAnimations)root.nativeAnimations={names:[],duration:'',delay:'',iterationCount:'',direction:'',timingFunction:''};
    const durs=splitCssList(root.nativeAnimations.duration),delays=splitCssList(root.nativeAnimations.delay),iters=splitCssList(root.nativeAnimations.iterationCount),dirs=splitCssList(root.nativeAnimations.direction),timings=splitCssList(root.nativeAnimations.timingFunction);
    const existing=new Map((asset.animations||[]).map(a=>[a.name,a]));
    for(const label of refAsset.animations||[]){
        const motion=resolveReferenceMotion(label),meta=ensureReferenceMotionLibrary(project,motion),animName=meta.key;
        if(!root.nativeAnimations.names.includes(animName)){root.nativeAnimations.names.push(animName);durs.push(`${meta.duration}s`);delays.push('0s');iters.push('infinite');dirs.push('normal');timings.push('ease-in-out')}
        if(!existing.has(label))existing.set(label,{id:`clip_${simpleHash(label)}`,name:label,keyframeNames:[animName],duration:meta.duration,delay:0,iterations:'infinite',direction:'normal',timing:'ease-in-out',source:'asset-reference'});
    }
    root.nativeAnimations.duration=durs.join(', ');root.nativeAnimations.delay=delays.join(', ');root.nativeAnimations.iterationCount=iters.join(', ');root.nativeAnimations.direction=dirs.join(', ');root.nativeAnimations.timingFunction=timings.join(', ');
    asset.animations=groupAssetAnimationList([...existing.values()]);asset.nativeAnimations=asset.animations.map(a=>a.name);asset.tags=[...(asset.tags||[]),refAsset.id,'asset-reference'].filter(Boolean);
}
function selectorTokens(selector){
    return [...String(selector||'').matchAll(/\.([A-Za-z0-9_-]+)/g)].map(m=>m[1].toLowerCase());
}
function referenceMatchScore(asset,refAsset){
    if(!asset||!refAsset)return 0;
    let score=0,id=String(asset.id||'').toLowerCase(),refId=String(refAsset.id||'').toLowerCase(),name=String(asset.name||'').toLowerCase(),refName=String(refAsset.name||'').toLowerCase();
    if(asset.reference?.id===refAsset.id)score+=100;
    if(id===`ref_${refId}`||id===refId)score+=80;
    if((asset.tags||[]).map(t=>String(t).toLowerCase()).includes(refId))score+=35;
    if(name&&refName&&(name===refName||name.includes(refName)||refName.includes(name)))score+=30;
    const classes=new Set(asset.node?.classes?.map(c=>String(c).toLowerCase())||[]);
    const tokenHits=selectorTokens(refAsset.selector).filter(t=>classes.has(t)).length;score+=tokenHits*10;
    if(asset.kind&&refAsset.kind&&asset.kind===refAsset.kind)score+=4;
    return score;
}
function findProjectAssetForReference(refAsset){
    let best=null,bestScore=0;
    for(const asset of Object.values(state.project?.assets||{})){
        const score=referenceMatchScore(asset,refAsset);
        if(score>bestScore){best=asset;bestScore=score}
    }
    return bestScore>=20?best:null;
}
async function mergeReferenceAnimations(){
    if(!state.project){toast('Open or import a project first.');return}
    let registry=await loadReferenceAssetRegistry('');
    if(!registry.length){
        if(!confirm('Could not automatically load detective-crumb-asset-reference.html. Select the reference HTML file manually?'))return;
        registry=await pickReferenceRegistryFile();
    }
    if(!registry.length){alert('Could not load or parse the reference ASSETS registry.');return}
    let merged=0;
    beginHistoryBatch();
    for(const refAsset of registry){
        const asset=findProjectAssetForReference(refAsset);if(!asset)continue;
        const before=(asset.animations||[]).length;applyReferenceAssetMetadata(asset,refAsset,state.project);
        for(const scene of state.project.scenes||[])for(const layer of scene.layers||[])if(layer.assetId===asset.id)ensureLayerHasAssetClips(layer,asset);
        if((asset.animations||[]).length!==before||asset.reference?.id===refAsset.id)merged++;
    }
    endHistoryBatch();
    renderAll();
    if(!merged){alert('No matching project assets were found for the reference registry. Reimport ChapterOne.html or rename/select assets closer to the reference IDs/names.');return}
    toast(`Merged reference animations into ${merged} asset${merged===1?'':'s'}.`,3200);
}

function transformImportSource(source){
    let text=String(source||'');
    text=text.replace(/<script\b[^>]*\btype\s*=\s*(["'])module\1[^>]*>.*?<\/script\s*>/gis,'');
    text=text.replace(/<script\b[^>]*\btype\s*=\s*(["'])module\1[^>]*\/\s*>/gis,'');
    let exposed=false;
    text=text.replace(/\bconst\s+sequences\s*=\s*\[/,()=>{exposed=true;return'const sequences = window.__editorSequences = ['});
    const freeze=`<style id="__movie_editor_import_freeze">html{scroll-behavior:auto!important}*,*::before,*::after{animation-play-state:paused!important;transition-duration:0s!important;transition-delay:0s!important}site-navbar,.mobile-landscape{display:none!important}</style><script>window.__MOVIE_EDITOR_IMPORT__=true;${exposed?'':'window.__editorSequences=[];'}<\/script>`;
    const lower=text.toLowerCase(),idx=lower.lastIndexOf('</head>');
    return idx>=0?text.slice(0,idx)+freeze+text.slice(idx):freeze+text;
}

async function requestImportSettings(fileName){
    const body=`
        <div class="animHelp">HTML is used only for this import. The resulting project contains structured scenes, assets and keyframes-not a copy of the HTML.</div>
        <div class="propGrid" style="grid-template-columns:155px minmax(0,1fr)">
            <label>Duration multiplier</label><input id="impScale" type="number" min="0.05" step="0.05" value="1">
            <label>Target total minutes</label><input id="impTarget" type="number" min="0" step="0.25" placeholder="optional">
            <label>Minimum scene seconds</label><input id="impMin" type="number" min="0.1" step="0.1" value="2.5">
            <label>Maximum scene seconds</label><input id="impMax" type="number" min="1" step="0.5" value="20">
            <label>Auto retime dialogue</label><input id="impDialogueTiming" type="checkbox" checked>
            <label>Dialogue speed WPM</label><input id="impDialogueWpm" type="number" min="80" max="260" step="5" value="150">
            <label>Motion sampling</label><select id="impSamples"><option value="65">Standard - 65 samples</option><option value="121" selected>Detailed - 121 samples</option><option value="181">Maximum - 181 samples</option></select>
        </div>
        <div class="muted" style="font-size:11px;margin-top:10px;line-height:1.45">Dialogue retiming estimates scene length from speech plus narrator/caption text, then applies multiplier, target runtime, and min/max limits.</div>`;
    return new Promise(resolve=>{
        showModal(`Import ${fileName}`,body,[{label:'Cancel',value:null},{label:'Import',primary:true,keep:true,onClick:(back,res)=>{
            const scale=Math.max(.05,+back.querySelector('#impScale').value||1),targetMinutes=Math.max(0,+back.querySelector('#impTarget').value||0),minSeconds=Math.max(.1,+back.querySelector('#impMin').value||2.5),maxSeconds=Math.max(minSeconds,+back.querySelector('#impMax').value||20),samples=clamp(Math.round(+back.querySelector('#impSamples').value||DEFAULT_IMPORT_SAMPLES),33,241),dialogueTiming=!!back.querySelector('#impDialogueTiming')?.checked,dialogueWpm=clamp(+back.querySelector('#impDialogueWpm').value||150,80,260);
            back.remove();res({scale,targetMinutes,minSeconds,maxSeconds,samples,dialogueTiming,dialogueWpm});
        }}]).then(resolve);
    });
}

function collectDialogueText(seq){
    const selectors=['.speech','.caption','.chapter-mark','.narrator','[data-speaker="narrator"]','[data-role="narrator"]'];
    const nodes=[
        ...seq.querySelectorAll(selectors.join(',')),
        ...[...seq.querySelectorAll('[aria-label]')].filter(el=>(el.getAttribute('aria-label')||'').toLowerCase().includes('narrator'))
    ].filter(el=>!el.closest('script,style'));
    const seen=new Set(),parts=[];
    for(const el of nodes){
        if(seen.has(el))continue;seen.add(el);
        const text=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
        if(text)parts.push(text);
    }
    return parts.join(' ');
}
function isSubtitleSourceElement(el){
    return !!el?.matches?.('.speech,.caption,.narrator,[data-speaker="narrator"],[data-role="narrator"]')||((el?.getAttribute?.('aria-label')||'').toLowerCase().includes('narrator'));
}
function subtitleKind(el){
    if(el.matches?.('.speech'))return 'speech';
    if(el.matches?.('.caption'))return 'caption';
    return 'narrator';
}
function collectSubtitleEntries(seq){
    const selectors=['.speech','.caption','.narrator','[data-speaker="narrator"]','[data-role="narrator"]'];
    const nodes=[
        ...seq.querySelectorAll(selectors.join(',')),
        ...[...seq.querySelectorAll('[aria-label]')].filter(el=>(el.getAttribute('aria-label')||'').toLowerCase().includes('narrator'))
    ].filter(el=>!el.closest('script,style'));
    const seen=new Set(),entries=[];
    for(const el of nodes){
        if(seen.has(el))continue;seen.add(el);
        const text=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
        if(text)entries.push({text,kind:subtitleKind(el),sourceId:el.id||'',speaker:el.getAttribute?.('data-speaker')||'',side:el.classList?.contains('right')?'right':'left',show:parseNormalizedTime(el.getAttribute?.('data-show')),hide:parseNormalizedTime(el.getAttribute?.('data-hide'))});
    }
    return entries;
}
function parseNormalizedTime(value){
    if(value===undefined||value===null||value==='')return null;
    const n=Number(value);return Number.isFinite(n)?clamp(n,0,1):null;
}
function subtitleCuesForScene(seq,sceneDuration,settings){
    const entries=collectSubtitleEntries(seq);if(!entries.length)return[];
    if(entries.some(e=>e.show!==null||e.hide!==null)){
        return entries.map((entry,i)=>{
            const fallbackStart=i/entries.length,fallbackEnd=(i+1)/entries.length;
            const start=entry.show!==null?entry.show:fallbackStart,end=entry.hide!==null?entry.hide:fallbackEnd;
            return{start:clamp(start,0,.999),end:clamp(Math.max(end,start+.02),.001,1),text:entry.text,kind:entry.kind,speaker:entry.speaker,side:entry.side,sourceId:entry.sourceId};
        }).filter(c=>c.end>c.start).sort((a,b)=>a.start-b.start);
    }
    const weights=entries.map(e=>Math.max(.8,estimateDialogueDuration(e.text,settings))),total=weights.reduce((a,b)=>a+b,0)||1,gap=Math.min(.025,.35/Math.max(1,sceneDuration));
    let cursor=.03;const usable=Math.max(.1,.94-gap*Math.max(0,entries.length-1));
    return entries.map((entry,i)=>{
        const span=usable*(weights[i]/total),start=clamp(cursor,0,.98),end=clamp(cursor+span,Math.min(start+.02,1),1);
        cursor=end+gap;return{start,end,text:entry.text,kind:entry.kind,speaker:entry.speaker,side:entry.side,sourceId:entry.sourceId};
    });
}
function estimateDialogueDuration(text,settings){
    const clean=String(text||'').replace(/\s+/g,' ').trim();if(!clean)return 0;
    const words=clean.split(/\s+/).filter(Boolean).length,wpm=clamp(+settings.dialogueWpm||150,80,260);
    const sentencePauses=(clean.match(/[.!?;:]/g)||[]).length,shortPauses=(clean.match(/[,\u2013\u2014-]/g)||[]).length;
    return Math.max(.05,(words/(wpm/60))+sentencePauses*.35+shortPauses*.12+1.1);
}
function retimeDurations(raw,settings,dialogue=[]){
    let values=raw.map((v,i)=>{
        const base=settings.dialogueTiming&&dialogue[i]>0?dialogue[i]:v;
        return Math.max(.05,base)*settings.scale;
    });
    if(settings.targetMinutes>0){const total=values.reduce((a,b)=>a+b,0)||1;const factor=(settings.targetMinutes*60)/total;values=values.map(v=>v*factor)}
    return values.map(v=>Math.round(clamp(v,settings.minSeconds,settings.maxSeconds)*100)/100);
}

const PART_STYLE_PROPS=['left','right','top','bottom','width','height','backgroundPositionX','backgroundPositionY','borderRadius'];
function numericStyleValue(value){
    if(value===undefined||value===null)return null;const s=String(value).trim();if(!s||s==='auto'||s==='none'||s==='normal')return null;
    const m=s.match(/^(-?\d*\.?\d+(?:e[-+]?\d+)?)(.*)$/i);if(!m)return null;return{value:+m[1],unit:m[2]||''};
}
function captureRichPartSample(win,el,pseudo=null){
    const cs=win.getComputedStyle(el,pseudo);const m=parseMatrix(cs.transform);const styles={};
    for(const prop of PART_STYLE_PROPS){const parsed=numericStyleValue(cs[prop]);if(parsed)styles[prop]=parsed}
    const custom={};
    if(!pseudo){for(const prop of [...el.style])if(prop.startsWith('--')){const parsed=numericStyleValue(el.style.getPropertyValue(prop));if(parsed)custom[prop]=parsed}}
    return{x:m.x,y:m.y,scaleX:m.scaleX,scaleY:m.scaleY,rotation:m.rotation,opacity:parseFloat(cs.opacity)||0,styles,custom};
}
function friendlyPartName(el,pseudo=null){
    const generic=new Set(['editorNode','person','layer','walking','scroll-beat','shown','gone']);let raw=el.id||[...el.classList].find(c=>!generic.has(c))||el.tagName?.toLowerCase()||'part';raw=safeName(raw);return pseudo?`${raw} ${pseudo==='::before'?'Before':'After'}`:raw;
}
function collectPartDescriptors(win,root){
    const list=[];
    function addElement(el,path,includeSelf=true){
        if(includeSelf)list.push({el,path,pseudo:null,label:friendlyPartName(el)});
        for(const pseudo of ['::before','::after'])if(isPseudoVisible(win,el,pseudo))list.push({el,path:`${path}.${pseudo==='::before'?'b':'a'}`,pseudo,label:friendlyPartName(el,pseudo)});
        [...el.children].filter(x=>!x.matches('script,style')).forEach((child,i)=>addElement(child,`${path}.${i}`,true));
    }
    [...root.children].filter(x=>!x.matches('script,style')).forEach((child,i)=>addElement(child,`0.${i}`,true));
    for(const pseudo of ['::before','::after'])if(isPseudoVisible(win,root,pseudo))list.push({el:root,path:`0.${pseudo==='::before'?'b':'a'}`,pseudo,label:friendlyPartName(root,pseudo)});
    return list;
}
function buildNumericPropertyTracks(samples,bucket,tol=.15){
    const names=new Set();samples.forEach(s=>Object.keys(s[bucket]||{}).forEach(k=>names.add(k)));const out={};
    for(const name of names){let unit='';const pts=[];for(const sample of samples){const v=sample[bucket]?.[name];if(!v)continue;unit=unit||v.unit;pts.push({t:sample.t,value:v.value,ease:'linear'})}if(pts.length<2)continue;const first=pts[0].value;if(pts.some(p=>Math.abs(p.value-first)>tol))out[name]={unit,keyframes:simplifyScalar(pts,tol)}}
    return out;
}
function buildRichPartTracks(samples){
    const transforms=buildTracks(samples,{x:.12,y:.12,rotation:.10,scaleX:.0025,scaleY:.0025,opacity:.005});
    const styleTracks=buildNumericPropertyTracks(samples,'styles',.18);const customTracks=buildNumericPropertyTracks(samples,'custom',.005);
    const hasTransform=tracksVary(transforms);return{tracks:hasTransform?transforms:{},styleTracks,customTracks};
}
function richPartVaries(group){return tracksVary(group.tracks)||Object.keys(group.styleTracks||{}).length>0||Object.keys(group.customTracks||{}).length>0}

async function importFromHtml(fileName,sourceText,settings){
    if(state.dirty&&!confirm('Discard unsaved changes and import a new HTML movie?'))return;
    const pm=progressModal('Import HTML Movie');
    try{
        pm.set(2,'Loading HTML...',fileName);
        const frame=$('#importFrame');
        frame.src='about:blank';await nextFrame();frame.srcdoc=transformImportSource(sourceText);
        await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('The HTML importer timed out.')),30000);frame.onload=()=>{clearTimeout(timer);setTimeout(resolve,650)}});
        const win=frame.contentWindow,doc=frame.contentDocument;if(!doc)throw new Error('Could not access imported document.');
        const allSeq=[...doc.querySelectorAll('.sequence')];if(!allSeq.length)throw new Error('No .sequence scenes were found.');
        pm.set(5,`Found ${allSeq.length} scenes`,'Analyzing runtime animation registrations...');
        const registered=new Map();const reg=win.__editorSequences||[];for(const pair of reg){if(pair&&pair[0]&&typeof pair[1]==='function')registered.set(pair[0],pair[1])}
        const referenceAssets=await loadReferenceAssetRegistry(sourceText);
        const project=emptyProject(fileName.replace(/\.html?$/i,''));project.meta.viewport={width:frame.clientWidth||1280,height:frame.clientHeight||720};
        project.meta.source={fileName,importedAt:new Date().toISOString(),note:'Import metadata only. The original HTML source is not stored in this project.'};
        project.meta.importSettings=deepClone(settings);project.animationLibrary=extractKeyframeLibrary(doc);
        const dialogueTexts=allSeq.map(collectDialogueText),dialogueDurations=dialogueTexts.map(text=>estimateDialogueDuration(text,settings));
        const rawDurations=allSeq.map(seq=>deriveDuration(seq,win,settings.minSeconds,settings.maxSeconds));const durations=retimeDurations(rawDurations,settings,dialogueDurations);
        const assetHashMap=new Map(),assets={},scenes=[];const sampleCount=settings.samples||DEFAULT_IMPORT_SAMPLES;

        for(let si=0;si<allSeq.length;si++){
            const seq=allSeq[si],fn=registered.get(seq)||null,stage=seq.querySelector('.stage')||seq,camera=seq.querySelector('.camera')||stage,sceneId=seq.id||`scene-${si+1}`;
            const scene={id:sceneId,name:safeName(sceneId),duration:durations[si],layers:[],source:{index:si+1,scrollHeight:seq.offsetHeight,originalDerivedDuration:rawDurations[si],dialogueDerivedDuration:dialogueDurations[si],dialogueCharacterCount:dialogueTexts[si]?.length||0},background:win.getComputedStyle(stage).background,notes:''};
            const subtitleCues=subtitleCuesForScene(seq,scene.duration,settings);
            if(subtitleCues.length)scene.layers.push({id:`${sceneId}_subtitles`,type:'subtitles',name:'Subtitles',cues:subtitleCues,base:{x:0,y:0,width:project.meta.viewport.width,height:project.meta.viewport.height,z:100000,opacity:1},tracks:{},locked:false,hidden:false});
            pm.set(7+(si/allSeq.length)*88,`Importing scene ${si+1} of ${allSeq.length}`,`${scene.name} - ${sampleCount} motion samples`);
            if(fn){try{fn(0)}catch(e){console.warn('Scene init failed',sceneId,e)}}await nextFrame();
            const roots=[...camera.children].filter(el=>!el.matches('script,style')),rootInfos=[],stageRect=stage.getBoundingClientRect();

            for(let ri=0;ri<roots.length;ri++){
                const el=roots[ri],kind=classifyRoot(el),layerId=`${sceneId}_layer_${ri+1}`;
                if(ri&&ri%4===0)await idleTick();
                if(kind==='text'){
                    if(isSubtitleSourceElement(el)){rootInfos.push({el,kind,layerId,text:true,subtitleSource:true,parts:[]});continue}
                    const base=captureElementSample(win,el,stageRect),cs=styleObject(win,el);
                    scene.layers.push({id:layerId,type:'text',name:inferAssetName(el,'Text'),textKind:el.classList.contains('speech')?'speech':el.classList.contains('caption')?'caption':el.classList.contains('sound')?'sound':'text',text:(el.innerText||el.textContent||'').trim(),style:cs,base:{x:base.x,y:base.y,width:base.width,height:base.height,rotation:base.rotation,scaleX:base.scaleX,scaleY:base.scaleY,opacity:base.opacity,z:base.z},tracks:{},locked:false,hidden:false});
                    rootInfos.push({el,kind,layerId,text:true,parts:[]});continue;
                }
                const refAsset=findReferenceAssetForRoot(referenceAssets,sceneId,camera,el);
                const node=serializeNode(win,el,'0',true),normalized=normalizeAssetForHash(node),hash=simpleHash(JSON.stringify(normalized));let assetId=refAsset?`ref_${refAsset.id}`:assetHashMap.get(hash);
                if(!assetId){assetId=`asset_${hash}`;assetHashMap.set(hash,assetId)}
                if(!assets[assetId]){const animations=collectAssetAnimationClips(node);assets[assetId]={id:assetId,name:refAsset?.name||inferAssetName(el,kind),kind:refAsset?.kind||kind,subtype:refAsset?.subtype,node,animations,nativeAnimations:animations.map(a=>a.name),createdFrom:refAsset?'asset-reference':'html-import',tags:[...el.classList].slice(0,6)}}
                if(refAsset)applyReferenceAssetMetadata(assets[assetId],refAsset,project);
                const base=captureElementSample(win,el,stageRect);
                scene.layers.push({id:layerId,type:'asset',name:assets[assetId].name,assetId,kind,base:{x:base.x,y:base.y,width:base.width,height:base.height,rotation:base.rotation,scaleX:base.scaleX,scaleY:base.scaleY,opacity:base.opacity,z:base.z},clips:(assets[assetId].animations||[]).map(a=>({clipId:a.id,name:a.name,speed:1,offset:0,loop:true,enabled:true})),tracks:{},locked:false,hidden:false});
                const parts=collectPartDescriptors(win,el),animTargets=[{el,path:'0'},...parts.filter(p=>!p.pseudo).map(p=>({el:p.el,path:p.path}))];
                rootInfos.push({el,kind,layerId,assetId,refAsset,text:false,parts,animTargets,nativeByPath:new Map(),activeByClip:new Map()});
            }

            const cameraSamples=[],rumbleSamples=[],rootSamples=new Map(rootInfos.map(i=>[i.layerId,[]])),partSamples=new Map();
            for(const info of rootInfos)if(!info.text)for(const part of info.parts)partSamples.set(`${info.layerId}:${part.path}`,[]);

            for(let k=0;k<sampleCount;k++){
                const t=k/(sampleCount-1);if(fn){try{fn(t)}catch(e){if(k===0)console.warn('Animation sample failed',sceneId,e)}}
                const sr=stage.getBoundingClientRect(),ccs=win.getComputedStyle(camera),cm=parseMatrix(ccs.transform),rt=parseTranslate(ccs.translate);
                cameraSamples.push({t,x:cm.x,y:cm.y,scaleX:cm.scaleX,scaleY:cm.scaleY,rotation:cm.rotation,opacity:1,width:0,height:0});rumbleSamples.push({t,x:rt.x,y:rt.y,opacity:1,width:0,height:0,rotation:0,scaleX:1,scaleY:1});
                for(const info of rootInfos){
                    const sample=captureElementSample(win,info.el,sr);sample.t=t;rootSamples.get(info.layerId).push(sample);
                    if(!info.text){
                        for(const target of info.animTargets||[]){
                            const meta=nativeAnimationMeta(win,target.el);
                            if(meta){info.nativeByPath.set(target.path,mergeAnimationMeta(info.nativeByPath.get(target.path),meta));for(const name of meta.names){const clipName=animationClipNameFor(name);if(!info.activeByClip.has(clipName))info.activeByClip.set(clipName,[]);info.activeByClip.get(clipName).push({t,value:true})}}
                        }
                        for(const [name,samples] of info.activeByClip)if(!samples.length||Math.abs(samples[samples.length-1].t-t)>.0005)samples.push({t,value:false});
                        for(const part of info.parts){const ps=captureRichPartSample(win,part.el,part.pseudo);ps.t=t;partSamples.get(`${info.layerId}:${part.path}`).push(ps)}
                    }
                }
                if(k%5===0)await idleTick();
            }

            scene.layers.unshift({id:`${sceneId}_camera`,type:'camera',name:'Camera',base:{x:cameraSamples[0].x,y:cameraSamples[0].y,zoom:cameraSamples[0].scaleX,rotation:cameraSamples[0].rotation,opacity:1},tracks:cameraTracks(cameraSamples),locked:false,hidden:false});
            const rTracks={x:simplifyScalar(rumbleSamples.map(s=>({t:s.t,value:s.x,ease:'linear'})),.08),y:simplifyScalar(rumbleSamples.map(s=>({t:s.t,value:s.y,ease:'linear'})),.08)},hasRumble=rumbleSamples.some(s=>Math.abs(s.x)>.04||Math.abs(s.y)>.04);
            scene.layers.splice(1,0,{id:`${sceneId}_rumble`,type:'effect',effect:'camera-rumble',name:'Camera Rumble',targetLayerId:`${sceneId}_camera`,base:{x:0,y:0},tracks:hasRumble?rTracks:{},enabled:true,locked:false,hidden:!hasRumble});

            for(const info of rootInfos){
                if(info.text)continue;
                const asset=assets[info.assetId];if(!asset)continue;
                for(const [path,meta] of info.nativeByPath||[])mergeNativeAnimationMeta(asset.node,path,meta);
                const instanceAnimations=collectAnimationClipsFromPathMeta(info.nativeByPath);
                asset.animations=groupAssetAnimationList([...collectAssetAnimationClips(asset.node),...instanceAnimations]);asset.nativeAnimations=asset.animations.map(a=>a.name);
                if(info.refAsset)applyReferenceAssetMetadata(asset,info.refAsset,project);
                if(asset.animations.length||instanceAnimations.length){
                    const layer=scene.layers.find(l=>l.id===info.layerId);
                    const clips=normalizeSceneClipList(asset.animations.map(a=>{const samples=info.activeByClip?.get(a.name)||[];return{clipId:a.id,name:a.name,keyframeNames:a.keyframeNames,speed:1,offset:0,loop:true,enabled:true,activeKeyframes:samples.length?booleanSamplesToKeyframes(samples):[{t:0,value:a.source==='asset-reference'?false:true,ease:'hold'}]}}),asset);
                    if(layer){layer.clips=clips;layer.nativeAnimationsByPath=Object.fromEntries([...(info.nativeByPath||new Map()).entries()].map(([path,meta])=>[path,deepClone(meta)]))}
                    const clipLayerIndex=scene.layers.findIndex(l=>l.type==='animation'&&l.animationKind==='clip'&&l.targetLayerId===info.layerId);
                    if(clipLayerIndex>=0)scene.layers.splice(clipLayerIndex,1);
                }
            }

            for(const info of rootInfos){
                const layer=scene.layers.find(l=>l.id===info.layerId);if(!layer)continue;layer.tracks=buildTracks(rootSamples.get(info.layerId));if(info.text)continue;
                const animatedPaths=new Set(info.nativeByPath?.keys?.()||[]);
                const varyingParts={},partLabels={};
                for(const part of info.parts){
                    if(animatedPaths.has(part.path))continue;
                    const group=buildRichPartTracks(partSamples.get(`${info.layerId}:${part.path}`));
                    if(richPartVaries(group)){varyingParts[part.path]=group;partLabels[part.path]=part.label||part.path}
                }
                if(Object.keys(varyingParts).length){const insertAt=scene.layers.findIndex(l=>l.id===info.layerId)+1;scene.layers.splice(insertAt,0,{id:`${info.layerId}_motion`,type:'animation',animationKind:'keyframed',name:`${layer.name} - Scene Motion`,targetLayerId:info.layerId,tracks:{},partTracks:varyingParts,partLabels,locked:false,hidden:false})}
            }
            scenes.push(scene);await idleTick();
        }
        project.assets=assets;project.scenes=scenes;
        for(const scene of project.scenes)for(const layer of scene.layers)if(layer.type==='asset')ensureLayerHasAssetClips(layer,project.assets[layer.assetId]);
        project.meta.modifiedAt=new Date().toISOString();pm.set(98,'Finalizing project...',`${Object.keys(assets).length} reusable assets - ${scenes.length} scenes`);
        state.project=project;state.fileName='';state.filePath='';state.currentSceneIndex=0;state.selectedLayerId=project.scenes[0]?.layers[0]?.id||null;state.selectedAssetId=null;state.selectedKeyframe=null;state.selectedKeyframes=[];state.playhead=0;state.renderCache.clear();resetHistory(false);renderAll();
        pm.set(100,'Import complete','The HTML is no longer needed. Save the structured movie project JSON.');setTimeout(()=>pm.close(),500);toast(`Imported ${scenes.length} scenes and ${Object.keys(assets).length} assets.`);
    }catch(err){pm.close();console.error(err);alert(`Import failed:\n\n${err.message}`)}
}

function pathForElement(root,el){
    const indices=[];let cur=el;
    while(cur&&cur!==root){const p=cur.parentElement;if(!p)break;indices.unshift([...p.children].indexOf(cur));cur=p}
    return indices.join('.');
}
function cameraTracks(samples){
    return {
        x:simplifyScalar(samples.map(s=>({t:s.t,value:s.x,ease:'linear'})),.15),
        y:simplifyScalar(samples.map(s=>({t:s.t,value:s.y,ease:'linear'})),.15),
        zoom:simplifyScalar(samples.map(s=>({t:s.t,value:(s.scaleX+s.scaleY)/2,ease:'linear'})),.003),
        rotation:simplifyScalar(samples.map(s=>({t:s.t,value:s.rotation,ease:'linear'})),.1)
    };
}
function deriveDuration(seq,win,minSeconds=2.5,maxSeconds=20){
    const units=Math.max(1,(seq.offsetHeight-win.innerHeight)/Math.max(1,win.innerHeight));
    return Math.round(clamp(units*.42,minSeconds,maxSeconds)*100)/100;
}
function nextFrame(){return new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))}
function idleTick(){return new Promise(r=>(window.requestIdleCallback?requestIdleCallback(()=>r(),{timeout:40}):setTimeout(r,0)))}
async function sha256Text(text){
    const bytes=new TextEncoder().encode(text);const buf=await crypto.subtle.digest('SHA-256',bytes);return [...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');
}

function buildNode(node){
    const el=document.createElement(node.tag||'div');el.classList.add('editorNode');for(const c of node.classes||[])if(c)el.classList.add(c);el.dataset.nodePath=node.path||'';
    applyStyleMap(el,node.style||{});if(node.nativeAnimations?.names?.includes('rainFall'))el.style.transform='';
    if(node.svgMarkup)el.innerHTML=node.svgMarkup;
    if(node.text)el.appendChild(document.createTextNode(node.text));for(const ch of node.children||[]){const c=buildNode(ch);if(ch.pseudo)c.classList.add('editorPseudo');el.appendChild(c)}return el;
}
function applyStyleMap(el,style){for(const [k,v] of Object.entries(style||{})){try{el.style[k]=v}catch{}}}
function evalTrack(track,t,defaultValue=0){
    if(!track||!track.length)return defaultValue;if(t<=track[0].t)return track[0].value;if(t>=track[track.length-1].t)return track[track.length-1].value;
    for(let i=0;i<track.length-1;i++){const a=track[i],b=track[i+1];if(t>=a.t&&t<=b.t){let u=(t-a.t)/Math.max(1e-9,b.t-a.t);if((a.ease||'linear')==='hold')u=0;else if(a.ease==='ease-in')u=u*u;else if(a.ease==='ease-out')u=1-(1-u)*(1-u);else if(a.ease==='ease-in-out')u=u<.5?2*u*u:1-Math.pow(-2*u+2,2)/2;return lerp(+a.value,+b.value,u)}}return defaultValue;
}
function propAt(layer,prop,t,def){return evalTrack(layer.tracks?.[prop],t,layer.base?.[prop]??def)}
function boolTrackAt(track,t,defaultValue=true){
    if(!track||!track.length)return !!defaultValue;
    const sorted=[...track].sort((a,b)=>a.t-b.t);let value=sorted[0].value;
    for(const k of sorted){if(t+1e-6>=k.t)value=k.value;else break}
    return !!value;
}
function clipActiveAt(clip,t){return clip.enabled!==false&&boolTrackAt(clip.activeKeyframes,t,true)}
function attachedClipLayer(layer){
    const scene=currentScene();if(!scene||!layer)return null;
    if(layer.clips?.length)return layer;
    return scene.layers.find(l=>l.type==='animation'&&l.animationKind==='clip'&&l.targetLayerId===layer.id)||null;
}

function renderSceneInto(stage,camera,scene,cache,interactive=false){
    const project=state.project;camera.innerHTML='';cache.clear();
    if(!project||!scene)return false;
    const vp=project.meta.viewport||{width:1280,height:720};stage.style.width=`${vp.width}px`;stage.style.height=`${vp.height}px`;stage.style.background=scene.background||'#eee';
    for(const layer of scene.layers){
        if(layer.type==='camera'||layer.type==='effect'||layer.type==='animation')continue;
        const wrapper=document.createElement('div');wrapper.className='layerWrapper';wrapper.dataset.layerId=layer.id;wrapper.style.width=`${Math.max(1,layer.base?.width||100)}px`;wrapper.style.height=`${Math.max(1,layer.base?.height||100)}px`;if(interactive)wrapper.addEventListener('mousedown',onPreviewLayerDown);
        if(layer.type==='asset'){
            const asset=project.assets[layer.assetId];if(asset){const node=buildNode(asset.node);node.style.width='100%';node.style.height='100%';wrapper.appendChild(node)}
        }else if(layer.type==='text'){
            const el=document.createElement('div');el.className='editorNode';applyStyleMap(el,layer.style||{});el.style.position='relative';el.style.left='0';el.style.top='0';el.style.right='auto';el.style.bottom='auto';el.style.transform='none';el.style.opacity='1';el.style.width='100%';el.style.height='100%';el.textContent=layer.text||'';wrapper.appendChild(el);
        }else if(layer.type==='subtitles'){
            const overlay=document.createElement('div');overlay.className='subtitleOverlay';overlay.innerHTML='<div class="subtitleBox"></div>';wrapper.appendChild(overlay);
        }
        camera.appendChild(wrapper);cache.set(layer.id,wrapper);
    }
    return true;
}
function renderScene(){
    state.animationCache=new WeakMap();
    const ok=renderSceneInto($('#previewStage'),$('#previewCamera'),currentScene(),state.renderCache,true);
    $('#emptyPreview').classList.toggle('hidden',!!ok);
    if(ok){fitPreview();applyAtPlayhead()}
}
function applySceneAt(scene,t,camera,cache,animationCache,selectedLayerId=null){
    if(!scene)return;
    const camLayer=scene.layers.find(l=>l.type==='camera');const rumble=scene.layers.find(l=>l.type==='effect'&&l.effect==='camera-rumble');
    const cx=camLayer?propAt(camLayer,'x',t,0):0,cy=camLayer?propAt(camLayer,'y',t,0):0,zoom=camLayer?propAt(camLayer,'zoom',t,1):1,rot=camLayer?propAt(camLayer,'rotation',t,0):0;
    const rx=rumble&&!rumble.hidden&&rumble.enabled!==false?propAt(rumble,'x',t,0):0,ry=rumble&&!rumble.hidden&&rumble.enabled!==false?propAt(rumble,'y',t,0):0;
    camera.style.transform=`translate(${cx+rx}px,${cy+ry}px) scale(${zoom}) rotate(${rot}deg)`;
    for(const layer of scene.layers){
        if(layer.type!=='asset'&&layer.type!=='text'&&layer.type!=='subtitles')continue;const w=cache.get(layer.id);if(!w)continue;
        const x=propAt(layer,'x',t,layer.base?.x||0),y=propAt(layer,'y',t,layer.base?.y||0),r=propAt(layer,'rotation',t,layer.base?.rotation||0),sx=propAt(layer,'scaleX',t,layer.base?.scaleX||1),sy=propAt(layer,'scaleY',t,layer.base?.scaleY||1),op=propAt(layer,'opacity',t,layer.base?.opacity??1);
        w.style.transform=`translate(${x}px,${y}px) rotate(${r}deg) scale(${sx},${sy})`;w.style.opacity=layer.hidden?'0':String(op);w.style.zIndex=String(Math.round(propAt(layer,'z',t,layer.base?.z||0)));w.style.display=layer.hidden?'none':'block';w.classList.toggle('selected',layer.id===selectedLayerId);w.classList.toggle('locked',!!layer.locked);
        if(layer.type==='subtitles'){
            const cue=(layer.cues||[]).find(c=>t>=+c.start&&t<=+c.end),box=w.querySelector('.subtitleBox');
            if(box)box.textContent=cue&&!layer.hidden?cue.text||'':'';
        }
    }
    applyAnimationLayers(scene,t,cache,animationCache);
}
function applyAtPlayhead(){
    const scene=currentScene();if(!scene)return;const t=state.playhead;
    applySceneAt(scene,t,$('#previewCamera'),state.renderCache,state.animationCache,state.selectedLayerId);
    $('#timeSlider').value=Math.round(t*1000);$('#timeReadout').textContent=`${(t*scene.duration).toFixed(2)} / ${scene.duration.toFixed(2)} s`;$('#playheadHandle').style.left=`${t*100}%`;document.documentElement.style.setProperty('--playhead',`${t*100}%`);
    $('#sceneHud').textContent=`${state.currentSceneIndex+1}. ${scene.name}`;const l=currentLayer();$('#selectionHud').textContent=l?l.name:'Nothing selected';
}
function applyAnimationLayers(scene,t,cache=state.renderCache,animationCache=state.animationCache){
    for(const layer of scene.layers.filter(l=>(l.type==='asset'||l.type==='text')&&l.clips?.length&&!l.hidden)){
        const target=cache.get(layer.id);if(target)applyNativeClipLayer(target,layer,t,scene.duration,scene,animationCache);
    }
    for(const anim of scene.layers.filter(l=>l.type==='animation'&&!l.hidden)){
        const target=cache.get(anim.targetLayerId);if(!target)continue;
        if(anim.animationKind==='keyframed'){
            for(const [path,rawGroup] of Object.entries(anim.partTracks||{})){
                const el=[...target.querySelectorAll('[data-node-path]')].find(x=>x.dataset.nodePath===path);if(!el)continue;
                const group=rawGroup?.tracks||rawGroup||{},styleTracks=rawGroup?.styleTracks||{},customTracks=rawGroup?.customTracks||{};
                const hasTransform=Object.keys(group).some(k=>['x','y','rotation','scaleX','scaleY'].includes(k));
                if(hasTransform){const x=evalTrack(group.x,t,0),y=evalTrack(group.y,t,0),r=evalTrack(group.rotation,t,0),sx=evalTrack(group.scaleX,t,1),sy=evalTrack(group.scaleY,t,1);el.style.transform=`translate(${x}px,${y}px) rotate(${r}deg) scale(${sx},${sy})`}
                if(group.opacity)el.style.opacity=String(evalTrack(group.opacity,t,1));
                for(const [prop,trackDef] of Object.entries(styleTracks)){const keys=trackDef.keyframes||trackDef,unit=trackDef.unit||'';el.style[prop]=`${evalTrack(keys,t,parseFloat(el.style[prop])||0)}${unit}`}
                for(const [prop,trackDef] of Object.entries(customTracks)){const keys=trackDef.keyframes||trackDef,unit=trackDef.unit||'';el.style.setProperty(prop,`${evalTrack(keys,t,0)}${unit}`)}
            }
        }
        if(anim.animationKind==='clip')applyNativeClipLayer(target,anim,t,scene.duration,scene,animationCache);
    }
}
function keyTextToOffset(k){if(k==='from')return 0;if(k==='to')return 1;const n=parseFloat(k);return Number.isFinite(n)?n/100:0}
function applyNativeClipLayer(target,anim,t,sceneDuration,scene=currentScene(),animationCache=state.animationCache){
    const project=state.project,targetLayerId=anim.targetLayerId||anim.id;
    target.querySelectorAll('[data-node-path]').forEach(el=>{
        const path=el.dataset.nodePath,assetLayer=scene.layers.find(l=>l.id===targetLayerId),asset=project.assets[assetLayer?.assetId];if(!asset)return;
        const node=findAssetNode(asset.node,path),native=anim.nativeAnimationsByPath?.[path]||node?.nativeAnimations;if(!native?.names?.length)return;
        const cache=animationCache.get(el);
        if(cache){for(const [name,wa] of Object.entries(cache)){const cfg=(anim.clips||[]).find(c=>c.name===name||(c.keyframeNames||[c.name]).includes(name));if(!cfg||!clipActiveAt(cfg,t)){try{wa.cancel()}catch{}delete cache[name]}}}
        const clipCfg=(anim.clips||[]).find(c=>(c.keyframeNames||[c.name]).some(name=>native.names.includes(name))&&clipActiveAt(c,t));if(!clipCfg)return;
        const actualName=(clipCfg.keyframeNames||[clipCfg.name]).find(name=>native.names.includes(name));if(!actualName)return;
        const def=project.animationLibrary[actualName];if(!def)return;
        let activeCache=animationCache.get(el);if(!activeCache){activeCache={};animationCache.set(el,activeCache)}let wa=activeCache[clipCfg.name];
        const clipIndex=native.names.indexOf(actualName),durs=splitCssList(native.duration),dirs=splitCssList(native.direction),timings=splitCssList(native.timingFunction),duration=Math.max(20,timeToSeconds(durs[clipIndex]||durs[0],1)*1000);
        if(!wa){const frames=def.frames.map(fr=>({offset:keyTextToOffset(fr.offset),...cssStyleToJs(fr.style)}));wa=el.animate(frames,{duration,iterations:Infinity,fill:'both',direction:dirs[clipIndex]||dirs[0]||'normal',easing:timings[clipIndex]||timings[0]||'linear'});wa.pause();activeCache[clipCfg.name]=wa}
        const delays=splitCssList(native.delay),nodeDelay=timeToSeconds(delays[clipIndex]||delays[0],0)*1000;
        const speed=clipCfg.speed||1,raw=t*sceneDuration*1000*speed+(clipCfg.offset||0)*1000-nodeDelay;wa.currentTime=clipCfg.loop===false?clamp(raw,0,duration):((raw%duration)+duration)%duration;
    });
}
function cssStyleToJs(style){const o={};for(const[k,v]of Object.entries(style||{})){o[k.replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v}return o}
function findAssetNode(node,path){if(node.path===path)return node;for(const c of node.children||[]){const f=findAssetNode(c,path);if(f)return f}return null}

function fitPreview(){
    const wrap=$('#previewWrap'),stage=$('#previewStage'),project=state.project;if(!project)return;const vp=project.meta.viewport||{width:1280,height:720};const s=Math.min((wrap.clientWidth-30)/vp.width,(wrap.clientHeight-30)/vp.height);stage.style.transform=`scale(${Math.max(.1,s)})`;
}
function fitViewer(){
    const wrap=$('#viewerFrameWrap'),stage=$('#viewerStage'),project=state.project;if(!project||!state.viewer.open)return;const vp=project.meta.viewport||{width:1280,height:720};const s=Math.min((wrap.clientWidth-36)/vp.width,(wrap.clientHeight-36)/vp.height);stage.style.transform=`scale(${Math.max(.1,s)})`;
}
window.addEventListener('resize',()=>{fitPreview();fitViewer()});

function renderSceneStrip(){
    const box=$('#sceneBlocks');box.innerHTML='';const scenes=state.project?.scenes||[];$('#sceneCount').textContent=scenes.length;
    scenes.forEach((s,i)=>{const el=document.createElement('div');el.className='sceneBlock'+(i===state.currentSceneIndex?' active':'');el.style.width=`${Math.max(80,s.duration*18)}px`;el.innerHTML=`<div class="num">${i+1} - ${s.duration.toFixed(1)}s</div><div class="name">${escapeHtml(s.name)}</div>`;el.onclick=()=>selectScene(i);box.appendChild(el)});
}
function layerIcon(l){return l.type==='camera'?'Cam':l.type==='effect'?'Fx':l.type==='animation'?'*':l.type==='subtitles'?'CC':l.type==='text'?'T':l.kind==='character'?'Char':'Asset'}
function collectKeyframeTimes(value,set){
    if(Array.isArray(value)){if(value.length&&value.every(x=>x&&typeof x==='object'&&'t'in x)){value.forEach(k=>set.add(+k.t));return}value.forEach(v=>collectKeyframeTimes(v,set));return}
    if(value&&typeof value==='object'){if(Array.isArray(value.keyframes)){value.keyframes.forEach(k=>set.add(+k.t));return}Object.values(value).forEach(v=>collectKeyframeTimes(v,set))}
}
function keyframeTimes(layer){const set=new Set();collectKeyframeTimes(layer.tracks||{},set);collectKeyframeTimes(layer.partTracks||{},set);collectKeyframeTimes(layer.clips||{},set);const attached=attachedClipLayer(layer);if(attached&&attached!==layer)collectKeyframeTimes(attached.clips||{},set);return[...set].filter(Number.isFinite).sort((a,b)=>a-b)}
function sameKeyframe(a,b){return a&&b&&a.layerId===b.layerId&&Math.abs(+a.t-+b.t)<.0005}
function isSelectedKeyframe(layerId,t){return (state.selectedKeyframes||[]).some(k=>sameKeyframe(k,{layerId,t}))}
function selectKeyframe(layerId,t,add=false){
    const key={layerId,t};
    if(add){
        const exists=isSelectedKeyframe(layerId,t);
        state.selectedKeyframes=exists?state.selectedKeyframes.filter(k=>!sameKeyframe(k,key)):[...(state.selectedKeyframes||[]),key];
    }else state.selectedKeyframes=[key];
    state.selectedKeyframe=state.selectedKeyframes[state.selectedKeyframes.length-1]||null;
}
function timelineTypeClass(layer){return layer.type==='animation'?'animation':layer.type==='camera'?'camera':layer.type==='effect'?'effect':(layer.type==='text'||layer.type==='subtitles')?'text':'asset'}
function renderLayerDurationBar(lane,layer){
    const bar=document.createElement('div');bar.className=`timelineBar ${timelineTypeClass(layer)}${layer.id===state.selectedLayerId?' selected':''}${layer.hidden?' hiddenLayer':''}`;
    bar.title=`${layer.name} - full scene length`;
    bar.innerHTML=`<span class="timelineBarLabel">${escapeHtml(layer.name)}</span>`;
    lane.appendChild(bar);
}
function activeSegmentsForClip(clip){
    const keys=[...(clip.activeKeyframes||[])].filter(k=>Number.isFinite(+k.t)).sort((a,b)=>a.t-b.t);
    if(!keys.length)return[{start:0,end:1,keyed:false}];
    const segments=[];let cursor=0,value=keys[0].t>.0005?true:!!keys[0].value;
    for(const k of keys){const t=clamp(+k.t,0,1);if(t>cursor&&value)segments.push({start:cursor,end:t,keyed:true});value=!!k.value;cursor=t}
    if(cursor<1&&value)segments.push({start:cursor,end:1,keyed:true});
    return segments.filter(s=>s.end-s.start>.0005);
}
function renderClipBlocks(lane,layer,scene){
    const target=layer.type==='animation'?scene.layers.find(l=>l.id===layer.targetLayerId):layer,asset=target?state.project?.assets?.[target.assetId]:null,clips=layer.clips||[];
    if(!clips.length)return;
    clips.forEach((clip,ci)=>{
        const meta=asset?.animations?.find(a=>a.name===clip.name||a.id===clip.clipId),clipSeconds=Math.max(.05,(meta?.duration||1)/Math.max(.05,Math.abs(clip.speed||1)));
        const span=clamp((clipSeconds/Math.max(.05,scene.duration))*100,2,100),repeat=clip.loop!==false,segments=activeSegmentsForClip(clip);
        const addBlock=(left,width,looped=false,partial=false)=>{
            const block=document.createElement('div');block.className=`timelineClipBlock${layer.id===state.selectedLayerId?' selected':''}${clip.enabled===false?' disabled':''}${layer.hidden?' hiddenLayer':''}`;
            block.style.left=`${left}%`;block.style.width=`${width}%`;
            if(clips.length>1){block.style.top=`${4+(ci%2)*12}px`;block.style.height='14px'}
            block.title=`${clip.name} - ${fmt(clipSeconds)}s${looped?' looped':''}`;
            block.innerHTML=`${partial?'<span class="timelineFade in"></span>':''}<span class="timelineClipName">${escapeHtml(clip.name)}</span>${partial?'<span class="timelineFade out"></span>':''}`;
            lane.appendChild(block);
        };
        for(const seg of segments){
            const segLeft=seg.start*100,segWidth=(seg.end-seg.start)*100;
            if(seg.keyed){addBlock(segLeft,Math.max(1.5,segWidth),false,true);continue}
            const count=repeat?Math.min(80,Math.max(1,Math.ceil(segWidth/span))):1;
            for(let i=0;i<count;i++){const left=segLeft+i*span;if(left>=segLeft+segWidth)break;addBlock(left,Math.min(span,segLeft+segWidth-left),repeat,false);if(!repeat)break}
        }
    });
}
function renderTracks(){
    const content=$('#trackContent');content.innerHTML='';const scene=currentScene();if(!scene)return;
    for(const layer of scene.layers){
        const row=document.createElement('div');row.className='trackRow';
        const label=document.createElement('div');label.className='trackLabel'+(layer.id===state.selectedLayerId?' selected':'');label.innerHTML=`<span class="typeIcon">${layerIcon(layer)}</span><span class="name">${escapeHtml(layer.name)}</span><span class="muted">${layer.hidden?'hidden':''}</span><button class="trackDelete" title="Delete layer">x</button>`;label.onclick=e=>{if(e.target.closest('.trackDelete')){e.stopPropagation();deleteLayerById(layer.id);return}selectLayer(layer.id)};
        const lane=document.createElement('div');lane.className='trackLane';lane.dataset.layerId=layer.id;lane.onclick=e=>{const r=lane.getBoundingClientRect();state.playhead=clamp((e.clientX-r.left)/r.width,0,1);selectLayer(layer.id);applyAtPlayhead();renderInspector()};
        renderLayerDurationBar(lane,layer);if(layer.clips?.length||layer.type==='animation'&&layer.animationKind==='clip')renderClipBlocks(lane,layer,scene);
        for(const t of keyframeTimes(layer)){const d=document.createElement('div');d.className='kfDiamond'+(isSelectedKeyframe(layer.id,t)?' selected':'');d.style.left=`${t*100}%`;d.title=`${(t*scene.duration).toFixed(2)} s`;d.onclick=e=>{e.stopPropagation();state.playhead=t;selectKeyframe(layer.id,t,e.ctrlKey||e.metaKey||e.shiftKey);selectLayer(layer.id,false);applyAtPlayhead();renderInspector();renderTracks()};lane.appendChild(d)}
        row.append(label,lane);content.appendChild(row);
    }
}
function stopAssetPreviewAnimations(){for(const a of state.assetPreviewAnimations||[]){try{a.cancel()}catch{}}state.assetPreviewAnimations=[]}
function mountAssetPreview(asset,host,clipName=null,play=false){
    if(!asset||!host)return;host.innerHTML='';const root=buildNode(asset.node);root.classList.add('assetPreviewRoot');root.style.width=asset.node?.style?.width||'auto';root.style.height=asset.node?.style?.height||'auto';host.appendChild(root);
    requestAnimationFrame(()=>{const w=Math.max(1,root.getBoundingClientRect().width),h=Math.max(1,root.getBoundingClientRect().height),scale=Math.min((host.clientWidth-10)/w,(host.clientHeight-10)/h,1.4);root.style.transform=`translate(-50%,-50%) scale(${Math.max(.05,scale)})`});
    if(play&&clipName){
        stopAssetPreviewAnimations();const clip=(asset.animations||[]).find(c=>c.name===clipName);if(!clip)return;
        [root,...root.querySelectorAll('[data-node-path]')].forEach(el=>{const node=findAssetNode(asset.node,el.dataset.nodePath),names=clip.keyframeNames||[clip.name],actualName=names.find(n=>node?.nativeAnimations?.names?.includes(n));if(!actualName)return;const def=state.project?.animationLibrary?.[actualName];if(!def)return;const clipIndex=node.nativeAnimations.names.indexOf(actualName),durs=splitCssList(node.nativeAnimations.duration),dirs=splitCssList(node.nativeAnimations.direction),timings=splitCssList(node.nativeAnimations.timingFunction),frames=def.frames.map(fr=>({offset:keyTextToOffset(fr.offset),...cssStyleToJs(fr.style)}));const anim=el.animate(frames,{duration:Math.max(20,timeToSeconds(durs[clipIndex]||durs[0],clip?.duration||1)*1000),iterations:Infinity,fill:'both',direction:dirs[clipIndex]||dirs[0]||clip?.direction||'normal',easing:timings[clipIndex]||timings[0]||clip?.timing||'linear'});state.assetPreviewAnimations.push(anim)});
    }
}
function renderAssets(){
    stopAssetPreviewAnimations();const list=$('#assetList');list.innerHTML='';if(!state.project)return;const q=$('#assetSearch').value.trim().toLowerCase();
    for(const asset of Object.values(state.project.assets).sort((a,b)=>a.name.localeCompare(b.name))){
        const anims=asset.animations||[];if(q&&!`${asset.name} ${asset.kind} ${(asset.tags||[]).join(' ')} ${anims.map(a=>a.name).join(' ')}`.toLowerCase().includes(q))continue;
        const el=document.createElement('div');el.className='assetCard'+(asset.id===state.selectedAssetId?' selected':'');el.innerHTML=`<div class="assetThumb"></div><div><div class="assetName">${escapeHtml(asset.name)}</div><div class="assetMeta">${escapeHtml(asset.kind)}${anims.length?` - ${anims.length} clip${anims.length===1?'':'s'}`:''}</div></div><button class="icon addAsset" title="Add to scene">+</button>`;
        mountAssetPreview(asset,el.querySelector('.assetThumb'));el.onclick=e=>{if(e.target.closest('.addAsset')){addAssetToScene(asset.id);return}state.selectedAssetId=asset.id;state.selectedLayerId=null;renderAssets();renderInspector()};list.appendChild(el);
    }
}

function renderAll(){
    $('#projectName').textContent=state.project?.meta?.name||'No project';renderAssets();renderSceneStrip();renderTracks();renderScene();renderInspector();
}

function selectScene(i){if(!state.project)return;state.currentSceneIndex=clamp(i,0,state.project.scenes.length-1);state.playhead=0;state.selectedLayerId=currentScene()?.layers[0]?.id||null;state.selectedAssetId=null;state.selectedKeyframe=null;state.selectedKeyframes=[];renderSceneStrip();renderTracks();renderScene();renderInspector()}
function selectLayer(id,rerender=true){state.selectedLayerId=id;state.selectedAssetId=null;if(rerender){state.selectedKeyframe=null;state.selectedKeyframes=[];renderTracks();applyAtPlayhead();renderInspector()}}

function renderInspector(){
    const body=$('#inspectorBody');const layer=currentLayer();const asset=currentAsset();
    if(asset){body.innerHTML=assetInspector(asset);wireAssetInspector(asset);return}
    if(!layer){body.innerHTML='<div class="muted">Select a layer or asset.</div>';return}
    const scene=currentScene();let html=`<div><b>${escapeHtml(layer.name)}</b> <span class="badge">${escapeHtml(layer.type)}</span></div>`;
    html+=`<div class="sectionTitle">Layer</div><div class="propGrid"><label>Name</label><input id="iName" value="${escapeHtml(layer.name)}"><label>Visible</label><input id="iVisible" type="checkbox" ${!layer.hidden?'checked':''}><label>Locked</label><input id="iLocked" type="checkbox" ${layer.locked?'checked':''}></div>`;
    if(layer.type==='camera')html+=transformInspector(layer,['x','y','zoom','rotation']);
    else if(layer.type==='effect')html+=rumbleInspector(layer);
    else if(layer.type==='asset'||layer.type==='text'){html+=transformInspector(layer,['x','y','z','scaleX','scaleY','rotation','opacity']);if(layer.type==='asset')html+=animationStateInspector(layer)}
    else if(layer.type==='subtitles')html+=transformInspector(layer,['z','opacity'])+subtitleInspector(layer);
    else if(layer.type==='animation')html+=animationInspector(layer);
    if(layer.type==='text')html+=`<div class="sectionTitle">Text</div><textarea id="iText" rows="5" style="width:100%">${escapeHtml(layer.text||'')}</textarea>`;
    html+=keyframeInspector(layer,scene);
    body.innerHTML=html;wireLayerInspector(layer);
}
function transformInspector(layer,props){
    let s='<div class="sectionTitle">Transform at Playhead</div><div class="propGrid">';for(const p of props){const def=p==='zoom'||p==='scaleX'||p==='scaleY'||p==='opacity'?1:0,step=p==='z'?1:.01;s+=`<label>${p}</label><input class="propInput" data-prop="${p}" type="number" step="${step}" value="${fmt(propAt(layer,p,state.playhead,def))}">`}s+='</div><div style="display:flex;gap:6px;margin-top:8px"><button id="addKfBtn" class="primary">* Keyframe Current Values</button><button id="resetTransformBtn">Reset</button></div>';return s;
}
function rumbleInspector(layer){
    const x=propAt(layer,'x',state.playhead,0),y=propAt(layer,'y',state.playhead,0);
    return `<div class="sectionTitle">Camera Rumble Offset</div><div class="propGrid"><label>X</label><input class="propInput" data-prop="x" type="number" step="0.1" value="${fmt(x)}"><label>Y</label><input class="propInput" data-prop="y" type="number" step="0.1" value="${fmt(y)}"></div><div class="sectionTitle">Generate Rumble</div><div class="propGrid"><label>Amplitude</label><input id="rumbleAmp" type="number" value="4" step=".5"><label>Frequency</label><input id="rumbleFreq" type="number" value="14" step="1"></div><div style="display:flex;gap:6px;margin-top:8px"><button id="genRumbleBtn">Generate</button><button id="clearRumbleBtn">Clear</button></div>`;
}
function animationStateInspector(layer){
    const anim=attachedClipLayer(layer);if(!anim||!anim.clips?.length)return '';
    return `<div class="sectionTitle">Animation Active State</div><div class="animHelp">Toggle reusable animations on this ${escapeHtml(layer.kind||'object')} at the current playhead, then keyframe the active state.</div><div class="propGrid">${anim.clips.map((c,i)=>`<label>${escapeHtml(c.name)}</label><input class="clipActiveAtPlayhead" data-i="${i}" type="checkbox" ${clipActiveAt(c,state.playhead)?'checked':''}>`).join('')}</div><button id="clipKeyframeActiveBtn" class="primary" style="margin-top:8px">* Keyframe Active States</button>`;
}
function subtitleSpeakerOptions(layer){
    const scene=currentScene(),names=new Set(['Narrator']);
    for(const l of scene?.layers||[]){const asset=state.project?.assets?.[l.assetId];if(l.type==='asset'&&(l.kind==='character'||asset?.kind==='character')&&l.name)names.add(l.name)}
    for(const c of layer.cues||[])if(c.speaker)names.add(c.speaker);
    return [...names];
}
function subtitleInspector(layer){
    const speakers=subtitleSpeakerOptions(layer);
    const rows=(layer.cues||[]).map((cue,i)=>`<div class="subtitleCueRow" data-i="${i}">
        <div class="subtitleCueGrid">
            <label>Start<input class="subtitleCueField" data-field="start" data-i="${i}" type="number" min="0" max="1" step=".001" value="${fmt(+cue.start||0)}"></label>
            <label>End<input class="subtitleCueField" data-field="end" data-i="${i}" type="number" min="0" max="1" step=".001" value="${fmt(+cue.end||0)}"></label>
            <label>Kind<select class="subtitleCueField" data-field="kind" data-i="${i}">${['speech','caption','narrator','subtitle'].map(k=>`<option value="${k}" ${cue.kind===k?'selected':''}>${k}</option>`).join('')}</select></label>
            <label>Speaker<input class="subtitleCueField" data-field="speaker" data-i="${i}" list="subtitleSpeakerOptions" value="${escapeHtml(cue.speaker||'')}"></label>
        </div>
        <div class="subtitleCueGrid">
            <label>Side<select class="subtitleCueField" data-field="side" data-i="${i}"><option value="" ${!cue.side?'selected':''}>none</option><option value="left" ${cue.side==='left'?'selected':''}>left</option><option value="right" ${cue.side==='right'?'selected':''}>right</option></select></label>
            <label>Source<input class="subtitleCueField" data-field="sourceId" data-i="${i}" value="${escapeHtml(cue.sourceId||'')}"></label>
        </div>
        <textarea class="subtitleCueText subtitleCueField" data-field="text" data-i="${i}">${escapeHtml(cue.text||'')}</textarea>
    </div>`).join('');
    return `<div class="sectionTitle">Subtitle Cues</div><div class="animHelp">Edit subtitle text, timing, and speaker assignment here. Lip Sync uses Speaker first, then side/order as a fallback.</div><datalist id="subtitleSpeakerOptions">${speakers.map(s=>`<option value="${escapeHtml(s)}"></option>`).join('')}</datalist><div class="subtitleCueEditor">${rows||'<div class="muted">No subtitle cues.</div>'}</div><div style="display:flex;gap:6px;margin-top:8px"><button id="addSubtitleCueBtn">Add Cue</button><button id="sortSubtitleCuesBtn">Sort</button></div><div class="sectionTitle">Raw Cues JSON</div><textarea id="subtitleCueJson" rows="8" style="width:100%;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px">${escapeHtml(JSON.stringify(layer.cues||[],null,2))}</textarea>`;
}
function animationInspector(layer){
    if(layer.animationKind==='clip'){
        const target=currentScene()?.layers?.find(l=>l.id===layer.targetLayerId),asset=target?state.project?.assets?.[target.assetId]:null;
        return `<div class="sectionTitle">Asset Animation Clip (Reusable)</div><div class="animHelp">These clips belong to the asset itself (for example walking, arm swings, or a repeating bob). This layer chooses which reusable clips play on this specific scene instance. Scene-specific movement is kept in a separate <b>Scene Motion</b> layer.</div>${(layer.clips||[]).map((c,i)=>{const meta=asset?.animations?.find(a=>a.name===c.name);return`<div class="animClipCard"><div class="animClipHead"><b>${escapeHtml(c.name)}</b>${meta?`<span class="badge">${fmt(meta.duration)}s</span>`:''}</div><div class="propGrid"><label>Play</label><input class="clipEnabled" data-i="${i}" type="checkbox" ${c.enabled!==false?'checked':''}><label>Speed</label><input class="clipSpeed" data-i="${i}" type="number" step=".1" value="${c.speed||1}"><label>Time offset</label><input class="clipOffset" data-i="${i}" type="number" step=".05" value="${c.offset||0}"></div></div>`}).join('')||'<div class="muted">No reusable clips on this asset.</div>'}`;
    }
    const parts=Object.keys(layer.partTracks||{}),selected=parts.includes(state.selectedPartPath)?state.selectedPartPath:(parts[0]||'');state.selectedPartPath=selected;const group=layer.partTracks?.[selected]||{};
    const transformTracks=group.tracks||group||{},styleTracks=group.styleTracks||{},customTracks=group.customTracks||{};
    let channels='';
    for(const prop of ['x','y','rotation','scaleX','scaleY','opacity'])if(transformTracks[prop])channels+=`<label>${escapeHtml(prop)}</label><input class="partPropInput" data-kind="transform" data-prop="${prop}" type="number" step=".01" value="${fmt(evalTrack(transformTracks[prop],state.playhead,prop.startsWith('scale')||prop==='opacity'?1:0))}">`;
    for(const [prop,def] of Object.entries(styleTracks))channels+=`<label>${escapeHtml(prop)}</label><input class="partPropInput" data-kind="style" data-prop="${escapeHtml(prop)}" type="number" step=".1" value="${fmt(evalTrack(def.keyframes||def,state.playhead,0))}">`;
    for(const [prop,def] of Object.entries(customTracks))channels+=`<label>${escapeHtml(prop)}</label><input class="partPropInput" data-kind="custom" data-prop="${escapeHtml(prop)}" type="number" step=".01" value="${fmt(evalTrack(def.keyframes||def,state.playhead,0))}">`;
    return `<div class="sectionTitle">Scene Motion (Keyframes)</div><div class="animHelp">This is motion that happened in this scene only. Scene-specific mechanism movement such as a rising platform, moving rope, door, lever, or character pose appears here as editable keyframes.</div><div class="propGrid"><label>Animated part</label><select id="partSelect">${parts.map(p=>`<option value="${escapeHtml(p)}" ${p===selected?'selected':''}>${escapeHtml(layer.partLabels?.[p]||p)}</option>`).join('')}</select></div>${selected?`<div class="sectionTitle">Part Channels at Playhead</div><div class="propGrid">${channels||'<span class="muted">No numeric channels.</span>'}</div><button id="partKeyframeBtn" class="primary" style="margin-top:8px">* Keyframe These Values</button>`:'<div class="muted">No animated parts.</div>'}`;
}
function keyframeInspector(layer,scene){
    const times=keyframeTimes(layer);return `<div class="sectionTitle">Keyframes</div><div id="keyframeList">${times.map(t=>`<div class="kfRow"><button class="kfJump" data-t="${t}">${(t*scene.duration).toFixed(2)}s</button><span>${keyframePropsAt(layer,t).join(', ')||'parts'}</span><span>${Math.round(t*100)}%</span><button class="kfDelete danger" data-t="${t}">x</button></div>`).join('')||'<div class="muted">No keyframes.</div>'}</div>`;
}
function keyframePropsAt(layer,t){const result=[];for(const[p,a]of Object.entries(layer.tracks||{}))if(Array.isArray(a)&&a.some(k=>Math.abs(k.t-t)<1e-6))result.push(p);const clipHit=(layer.clips||[]).some(c=>(c.activeKeyframes||[]).some(k=>Math.abs(k.t-t)<1e-6));const attached=attachedClipLayer(layer),attachedHit=attached&&attached!==layer&&(attached.clips||[]).some(c=>(c.activeKeyframes||[]).some(k=>Math.abs(k.t-t)<1e-6));if(clipHit||attachedHit)result.push('animation active');if(!result.length&&layer.partTracks&&keyframeTimes({tracks:{},partTracks:layer.partTracks}).some(x=>Math.abs(x-t)<1e-6))result.push('part motion');return result}
function assetInspector(asset){
    const animations=asset.animations||[];
    return `<div><b>${escapeHtml(asset.name)}</b> <span class="badge">${escapeHtml(asset.kind)}</span></div><div id="assetBigPreview" class="assetBigPreview"></div><div class="sectionTitle">Asset</div><div class="propGrid"><label>Name</label><input id="assetName" value="${escapeHtml(asset.name)}"><label>Type</label><span>${escapeHtml(asset.kind)}</span></div><div class="sectionTitle">Asset Animation Clips</div><div class="animHelp">Animation clips live on the asset and can be reused in any scene. Edit the JSON structure to add multiple clips, frames, timings, and directions at once.</div>${animations.map((a,i)=>`<div class="animClipCard"><div class="animClipHead"><b>${escapeHtml(a.name)}</b><span class="badge">${fmt(a.duration||1)}s</span><button class="assetAnimPreview" data-i="${i}">Play Preview</button></div><div class="muted" style="font-size:11px">${escapeHtml(a.source||'animation clip')}</div></div>`).join('')||'<div class="muted">This asset has no reusable animation clips.</div>'}<div class="sectionTitle">Animations JSON</div><textarea id="assetAnimationCode">${escapeHtml(asset.animationCode||assetAnimationCode(asset))}</textarea><div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap"><button id="assetApplyAnimationCode" class="primary">Apply Animation Code</button><button id="assetResetAnimationCode">Regenerate From Clips</button></div><div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap"><button id="assetAddScene" class="primary">Add to Current Scene</button><button id="assetDuplicate">Duplicate Asset</button><button id="assetStopPreview">Stop Preview</button></div>`;
}
function wireAssetInspector(asset){
    mountAssetPreview(asset,$('#assetBigPreview'));
    $('#assetName').onchange=e=>{asset.name=e.target.value||asset.name;markDirty();renderAssets()};$('#assetAddScene').onclick=()=>addAssetToScene(asset.id);$('#assetDuplicate').onclick=()=>{const a=deepClone(asset);a.id=uid('asset');a.name+=' Copy';state.project.assets[a.id]=a;state.selectedAssetId=a.id;markDirty();renderAssets();renderInspector()};$('#assetStopPreview').onclick=()=>{stopAssetPreviewAnimations();mountAssetPreview(asset,$('#assetBigPreview'))};
    $('#assetApplyAnimationCode').onclick=()=>{try{applyAnimationCodeToAsset(asset,$('#assetAnimationCode').value);markDirty();renderAll();toast('Animation code applied.')}catch(err){alert(err.message)}};
    $('#assetResetAnimationCode').onclick=()=>{$('#assetAnimationCode').value=assetAnimationCode(asset)};
    $$('.assetAnimPreview').forEach(btn=>btn.onclick=()=>{const clip=asset.animations?.[+btn.dataset.i];if(clip)mountAssetPreview(asset,$('#assetBigPreview'),clip.name,true)});
}

function wireLayerInspector(layer){
    $('#iName').onchange=e=>{layer.name=e.target.value;markDirty();renderTracks()};$('#iVisible').onchange=e=>{layer.hidden=!e.target.checked;markDirty();applyAtPlayhead()};$('#iLocked').onchange=e=>{layer.locked=e.target.checked;markDirty();applyAtPlayhead()};
    $$('.propInput').forEach(inp=>inp.onchange=()=>setLayerPropertyAtPlayhead(layer,inp.dataset.prop,+inp.value));
    if($('#addKfBtn'))$('#addKfBtn').onclick=()=>{const props=$$('.propInput').map(i=>i.dataset.prop);beginHistoryBatch();for(const p of props)setKeyframe(layer,p,state.playhead,+document.querySelector(`.propInput[data-prop="${p}"]`).value,false);endHistoryBatch();renderTracks();renderInspector()};
    if($('#resetTransformBtn'))$('#resetTransformBtn').onclick=()=>{layer.tracks={};markDirty();renderTracks();applyAtPlayhead();renderInspector()};
    if($('#iText'))$('#iText').onchange=e=>{layer.text=e.target.value;markDirty();renderScene()};
    if($('#genRumbleBtn'))$('#genRumbleBtn').onclick=()=>generateRumble(layer,+$('#rumbleAmp').value,+$('#rumbleFreq').value);
    if($('#clearRumbleBtn'))$('#clearRumbleBtn').onclick=()=>{layer.tracks={};layer.hidden=false;markDirty();renderTracks();applyAtPlayhead();renderInspector()};
    $$('.subtitleCueField').forEach(inp=>inp.onchange=()=>{const cue=layer.cues?.[+inp.dataset.i];if(!cue)return;const field=inp.dataset.field;if(field==='start'||field==='end')cue[field]=clamp(+inp.value||0,0,1);else cue[field]=inp.value;if(cue.end<=cue.start)cue.end=clamp(cue.start+.03,0,1);markDirty();renderTracks();applyAtPlayhead();renderInspector()});
    if($('#addSubtitleCueBtn'))$('#addSubtitleCueBtn').onclick=()=>{layer.cues??=[];const t=state.playhead;layer.cues.push({start:t,end:clamp(t+.08,0,1),text:'New subtitle',kind:'speech',speaker:subtitleSpeakerOptions(layer).find(s=>s!=='Narrator')||'Narrator',side:'',sourceId:''});markDirty();renderTracks();applyAtPlayhead();renderInspector()};
    if($('#sortSubtitleCuesBtn'))$('#sortSubtitleCuesBtn').onclick=()=>{layer.cues=(layer.cues||[]).sort((a,b)=>(+a.start||0)-(+b.start||0));markDirty();renderTracks();applyAtPlayhead();renderInspector()};
    if($('#subtitleCueJson'))$('#subtitleCueJson').onchange=e=>{try{const cues=JSON.parse(e.target.value);if(!Array.isArray(cues))throw new Error('Subtitle cues must be an array.');layer.cues=cues.map(c=>({start:clamp(+c.start||0,0,1),end:clamp(+c.end||0,0,1),text:String(c.text||''),kind:c.kind||'subtitle',speaker:c.speaker||'',side:c.side||'',sourceId:c.sourceId||''})).filter(c=>c.text&&c.end>c.start).sort((a,b)=>a.start-b.start);markDirty();renderTracks();applyAtPlayhead();renderInspector()}catch(err){alert(err.message)}};
    $$('.clipEnabled').forEach(e=>e.onchange=()=>{layer.clips[+e.dataset.i].enabled=e.checked;markDirty();applyAtPlayhead()});$$('.clipSpeed').forEach(e=>e.onchange=()=>{layer.clips[+e.dataset.i].speed=+e.value;markDirty();applyAtPlayhead()});$$('.clipOffset').forEach(e=>e.onchange=()=>{layer.clips[+e.dataset.i].offset=+e.value;markDirty();applyAtPlayhead()});
    $$('.clipActiveAtPlayhead').forEach(e=>e.onchange=()=>{const anim=attachedClipLayer(layer);if(!anim)return;setClipActiveKeyframe(anim,+e.dataset.i,state.playhead,e.checked);renderTracks();applyAtPlayhead();renderInspector()});
    if($('#clipKeyframeActiveBtn'))$('#clipKeyframeActiveBtn').onclick=()=>{const anim=attachedClipLayer(layer);if(!anim)return;beginHistoryBatch();$$('.clipActiveAtPlayhead').forEach(e=>setClipActiveKeyframe(anim,+e.dataset.i,state.playhead,e.checked,false));endHistoryBatch();renderTracks();applyAtPlayhead();renderInspector()};
    if($('#partSelect'))$('#partSelect').onchange=e=>{state.selectedPartPath=e.target.value;renderInspector()};
    $$('.partPropInput').forEach(inp=>inp.onchange=()=>{setPartKeyframe(layer,state.selectedPartPath,inp.dataset.kind,inp.dataset.prop,state.playhead,+inp.value);renderTracks();applyAtPlayhead();renderInspector()});
    if($('#partKeyframeBtn'))$('#partKeyframeBtn').onclick=()=>{beginHistoryBatch();$$('.partPropInput').forEach(inp=>setPartKeyframe(layer,state.selectedPartPath,inp.dataset.kind,inp.dataset.prop,state.playhead,+inp.value,false));endHistoryBatch();renderTracks();applyAtPlayhead();renderInspector()};
    $$('.kfJump').forEach(b=>b.onclick=()=>{state.playhead=+b.dataset.t;applyAtPlayhead();renderInspector()});$$('.kfDelete').forEach(b=>b.onclick=()=>deleteKeyframesAt(layer,+b.dataset.t));
}
function setLayerPropertyAtPlayhead(layer,prop,value){
    if(state.autoKeyframe){setKeyframe(layer,prop,state.playhead,value,true);return}
    layer.base??={};layer.base[prop]=value;markDirty();renderTracks();applyAtPlayhead();renderInspector();
}
function setKeyframe(layer,prop,t,value,rerender=true){layer.tracks??={};layer.tracks[prop]??=[];const arr=layer.tracks[prop];const hit=arr.find(k=>Math.abs(k.t-t)<.0005);if(hit)hit.value=value;else arr.push({t,value,ease:'linear'});arr.sort((a,b)=>a.t-b.t);markDirty();if(rerender){renderTracks();applyAtPlayhead();renderInspector()}}
function setKeyframeArray(arr,t,value){const hit=arr.find(k=>Math.abs(k.t-t)<.0005);if(hit)hit.value=value;else arr.push({t,value,ease:'linear'});arr.sort((a,b)=>a.t-b.t)}
function setClipActiveKeyframe(anim,index,t,value,dirty=true){
    const clip=anim.clips?.[index];if(!clip)return;
    clip.activeKeyframes??=[];setKeyframeArray(clip.activeKeyframes,t,!!value);
    if(dirty)markDirty();
}
function setPartKeyframe(layer,path,kind,prop,t,value,dirty=true){
    const raw=layer.partTracks?.[path];if(!raw)return;const group=raw.tracks?raw:(layer.partTracks[path]={tracks:raw,styleTracks:{},customTracks:{}});
    if(kind==='transform'){group.tracks??={};group.tracks[prop]??=[];setKeyframeArray(group.tracks[prop],t,value)}
    else{const bucket=kind==='style'?'styleTracks':'customTracks';group[bucket]??={};group[bucket][prop]??={unit:'',keyframes:[]};if(Array.isArray(group[bucket][prop]))setKeyframeArray(group[bucket][prop],t,value);else{group[bucket][prop].keyframes??=[];setKeyframeArray(group[bucket][prop].keyframes,t,value)}}
    if(dirty)markDirty();
}
function removeKeyframesAt(value,t){
    if(Array.isArray(value)){if(value.length&&value.every(x=>x&&typeof x==='object'&&'t'in x)){for(let i=value.length-1;i>=0;i--)if(Math.abs(+value[i].t-t)<.0005)value.splice(i,1);return}value.forEach(v=>removeKeyframesAt(v,t));return}
    if(value&&typeof value==='object'){if(Array.isArray(value.keyframes)){removeKeyframesAt(value.keyframes,t);return}Object.values(value).forEach(v=>removeKeyframesAt(v,t))}
}
function copyKeyframesAt(value,t){
    if(Array.isArray(value)){
        if(value.length&&value.every(x=>x&&typeof x==='object'&&'t'in x)){
            const frames=value.filter(k=>Math.abs(+k.t-t)<.0005).map(k=>{const c=deepClone(k);delete c.t;return c});
            return frames.length?{__keyframes:frames}:null;
        }
        const arr=value.map(v=>copyKeyframesAt(v,t));return arr.some(Boolean)?arr:null;
    }
    if(value&&typeof value==='object'){
        const out={};for(const [k,v] of Object.entries(value)){const copied=copyKeyframesAt(v,t);if(copied)out[k]=copied}
        return Object.keys(out).length?out:null;
    }
    return null;
}
function pasteKeyframesInto(target,copied,t){
    if(!copied)return target;
    if(copied.__keyframes){const arr=Array.isArray(target)?target:[];for(let i=arr.length-1;i>=0;i--)if(Math.abs(+arr[i].t-t)<.0005)arr.splice(i,1);for(const frame of copied.__keyframes)arr.push({...deepClone(frame),t});arr.sort((a,b)=>a.t-b.t);return arr}
    if(Array.isArray(copied)){const arr=Array.isArray(target)?target:[];copied.forEach((child,i)=>{if(child)arr[i]=pasteKeyframesInto(arr[i],child,t)});return arr}
    const obj=target&&typeof target==='object'&&!Array.isArray(target)?target:{};
    for(const [k,v] of Object.entries(copied))obj[k]=pasteKeyframesInto(obj[k],v,t);
    return obj;
}
function deleteKeyframesAt(layer,t){beginHistoryBatch();removeKeyframesAt(layer.tracks||{},t);removeKeyframesAt(layer.partTracks||{},t);removeKeyframesAt(layer.clips||{},t);const attached=attachedClipLayer(layer);if(attached&&attached!==layer)removeKeyframesAt(attached.clips||{},t);endHistoryBatch();renderTracks();applyAtPlayhead();renderInspector()}
function deleteSelectedKeyframes(){
    const scene=currentScene(),keys=state.selectedKeyframes||[];if(!scene||!keys.length)return false;
    beginHistoryBatch();
    for(const key of keys){const layer=scene.layers.find(l=>l.id===key.layerId);if(layer){removeKeyframesAt(layer.tracks||{},key.t);removeKeyframesAt(layer.partTracks||{},key.t);removeKeyframesAt(layer.clips||{},key.t);const attached=attachedClipLayer(layer);if(attached&&attached!==layer)removeKeyframesAt(attached.clips||{},key.t)}}
    endHistoryBatch();state.selectedKeyframe=null;state.selectedKeyframes=[];renderTracks();applyAtPlayhead();renderInspector();return true;
}
function copySelectedKeyframes(){
    const scene=currentScene(),keys=state.selectedKeyframes||[];if(!scene||!keys.length)return false;
    state.keyframeClipboard=keys.map(key=>{
        const layer=scene.layers.find(l=>l.id===key.layerId);if(!layer)return null;
        const attached=attachedClipLayer(layer);
        return {layerId:key.layerId,t:key.t,tracks:copyKeyframesAt(layer.tracks||{},key.t),partTracks:copyKeyframesAt(layer.partTracks||{},key.t),clips:copyKeyframesAt(layer.clips||{},key.t),attachedLayerId:attached&&attached!==layer?attached.id:null,attachedClips:attached&&attached!==layer?copyKeyframesAt(attached.clips||{},key.t):null};
    }).filter(Boolean);
    if(state.keyframeClipboard.length)toast(`Copied ${state.keyframeClipboard.length} keyframe${state.keyframeClipboard.length===1?'':'s'}.`);
    return !!state.keyframeClipboard.length;
}
function pasteKeyframesAtPlayhead(){
    const scene=currentScene(),items=state.keyframeClipboard||[];if(!scene||!items.length)return false;
    const minT=Math.min(...items.map(i=>i.t)),newSelection=[];beginHistoryBatch();
    for(const item of items){
        const layer=scene.layers.find(l=>l.id===item.layerId);if(!layer)continue;
        const newT=clamp(state.playhead+(item.t-minT),0,1);
        if(item.tracks)layer.tracks=pasteKeyframesInto(layer.tracks||{},item.tracks,newT);
        if(item.partTracks)layer.partTracks=pasteKeyframesInto(layer.partTracks||{},item.partTracks,newT);
        if(item.clips)layer.clips=pasteKeyframesInto(layer.clips||[],item.clips,newT);
        const attached=item.attachedLayerId?scene.layers.find(l=>l.id===item.attachedLayerId):attachedClipLayer(layer);
        if(attached&&item.attachedClips)attached.clips=pasteKeyframesInto(attached.clips||[],item.attachedClips,newT);
        newSelection.push({layerId:layer.id,t:newT});
    }
    endHistoryBatch();state.selectedKeyframes=newSelection;state.selectedKeyframe=newSelection[newSelection.length-1]||null;renderTracks();applyAtPlayhead();renderInspector();return !!newSelection.length;
}
function generateRumble(layer,amp,freq){const ptsX=[],ptsY=[];const count=Math.max(24,Math.round(freq*5));for(let i=0;i<=count;i++){const t=i/count,envelope=Math.sin(Math.PI*t);ptsX.push({t,value:Math.sin(t*Math.PI*2*freq)*amp*envelope,ease:'linear'});ptsY.push({t,value:Math.cos(t*Math.PI*2*freq*1.37)*amp*.45*envelope,ease:'linear'})}layer.tracks={x:ptsX,y:ptsY};layer.hidden=false;markDirty();renderTracks();applyAtPlayhead();renderInspector()}

function findMouthPartPath(node){
    if(!node)return null;
    const classes=(node.classes||[]).map(c=>String(c).toLowerCase());
    if(classes.includes('mouth')||classes.includes('lip')||classes.some(c=>/mouth|lip/.test(c)))return node.path;
    for(const child of node.children||[]){const found=findMouthPartPath(child);if(found)return found}
    return null;
}
function lipSyncTargets(mode,scene=currentScene()){
    if(!scene)return[];
    const selected=currentLayer();
    let layers=mode==='selected'&&selected?.type==='asset'?[selected]:scene.layers.filter(l=>l.type==='asset'&&(l.kind==='character'||state.project.assets[l.assetId]?.kind==='character'));
    return layers.map(layer=>({layer,asset:state.project.assets[layer.assetId],mouthPath:findMouthPartPath(state.project.assets[layer.assetId]?.node)})).filter(t=>t.asset&&t.mouthPath);
}
function subtitleCueLayers(scene){return (scene.layers||[]).filter(l=>l.type==='subtitles'&&Array.isArray(l.cues))}
function normSpeakerName(value){return String(value||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()}
function targetSpeakerNames(target,index,total){
    const names=new Set([target.layer?.name,target.asset?.name,target.asset?.reference?.name,target.asset?.reference?.id,...(target.asset?.tags||[])].filter(Boolean).map(normSpeakerName));
    if(total>=2){
        if(index===0)names.add('edward');
        if(index===1||index===total-1)names.add('mabel');
    }
    return names;
}
function cuesForLipTarget(scene,target,index,total,includeNarrator=false){
    const cues=subtitleCueLayers(scene).flatMap(l=>l.cues||[]).filter(c=>c.text&&c.end>c.start);
    const targetNames=targetSpeakerNames(target,index,total);
    const speakerMatches=cue=>{const speaker=normSpeakerName(cue.speaker);return speaker&&[...targetNames].some(name=>name===speaker||name.includes(speaker)||speaker.includes(name))};
    if(cues.some(speakerMatches))return cues.filter(c=>speakerMatches(c)&&(includeNarrator||normSpeakerName(c.speaker)!=='narrator'));
    if(total<=1)return cues.filter(c=>includeNarrator||normSpeakerName(c.speaker)!=='narrator'&&c.kind!=='narrator');
    return cues.filter(c=>{
        if(normSpeakerName(c.speaker)==='narrator'||c.kind==='narrator')return includeNarrator&&index===0;
        if(c.side==='right')return index===1||index===total-1;
        if(c.side==='left')return index===0;
        return index===0;
    });
}
function mouthKeyframesFromCues(cues,intensity=1,rate=9){
    const pts=[{t:0,value:1,ease:'linear'}];
    for(const cue of cues){
        const start=clamp(+cue.start||0,0,1),end=clamp(+cue.end||0,0,1),dur=Math.max(.02,end-start);
        const words=String(cue.text||'').split(/\s+/).filter(Boolean).length;
        const pulses=clamp(Math.round(Math.max(1,words*.75,dur*rate*8)),1,36);
        pts.push({t:start,value:1,ease:'linear'});
        for(let i=0;i<pulses;i++){
            const a=start+dur*(i/pulses),mid=start+dur*((i+.45)/pulses),b=start+dur*((i+.82)/pulses);
            const text=String(cue.text||''),vowelBoost=/[aeiouy]/i.test(text[i%Math.max(1,text.length)]||'') ? .18 : 0;
            pts.push({t:clamp(a,0,1),value:1,ease:'linear'},{t:clamp(mid,0,1),value:1+(.75+vowelBoost)*intensity,ease:'linear'},{t:clamp(b,0,1),value:1.05,ease:'linear'});
        }
        pts.push({t:end,value:1,ease:'linear'});
    }
    return simplifyScalar(pts.sort((a,b)=>a.t-b.t),.015);
}
async function mouthKeyframesFromAudioFile(file,scene,intensity=1){
    const ctx=new (window.AudioContext||window.webkitAudioContext)(),buffer=await ctx.decodeAudioData(await file.arrayBuffer()),data=buffer.getChannelData(0);
    const windows=90,step=Math.max(1,Math.floor(data.length/windows)),rms=[];
    for(let i=0;i<windows;i++){let sum=0,count=0;for(let j=i*step;j<Math.min(data.length,(i+1)*step);j++){sum+=data[j]*data[j];count++}rms.push(Math.sqrt(sum/Math.max(1,count)))}
    try{await ctx.close()}catch{}
    const max=Math.max(.0001,...rms),pts=[{t:0,value:1,ease:'linear'}];
    rms.forEach((v,i)=>{const t=clamp(i/(windows-1),0,1),open=1+clamp((v/max-.16)*1.6,0,1.1)*intensity;pts.push({t,value:open,ease:'linear'})});
    pts.push({t:1,value:1,ease:'linear'});
    return simplifyScalar(pts,.025);
}
function applyLipSyncToTarget(scene,target,scaleYFrames){
    const existing=scene.layers.findIndex(l=>l.type==='animation'&&l.animationKind==='keyframed'&&l.lipSync&&l.targetLayerId===target.layer.id);
    const layer={id:`${target.layer.id}_lipsync`,type:'animation',animationKind:'keyframed',lipSync:true,name:`${target.layer.name} - Lip Sync`,targetLayerId:target.layer.id,tracks:{},partTracks:{[target.mouthPath]:{tracks:{scaleY:scaleYFrames,scaleX:[{t:0,value:1,ease:'linear'}]},styleTracks:{},customTracks:{}}},partLabels:{[target.mouthPath]:'Mouth'},locked:false,hidden:false};
    if(existing>=0)scene.layers.splice(existing,1,layer);else{const at=scene.layers.findIndex(l=>l.id===target.layer.id);scene.layers.splice(Math.max(0,at+1),0,layer)}
    return layer;
}
function ensureSceneSubtitleLipSync(scene,{includeNarrator=false,intensity=1,rate=9}={}){
    const targets=lipSyncTargets('all',scene);let made=0;
    targets.forEach((target,i)=>{
        const cues=cuesForLipTarget(scene,target,i,targets.length,includeNarrator);
        if(!cues.length)return;
        applyLipSyncToTarget(scene,target,mouthKeyframesFromCues(cues,intensity,rate));
        made++;
    });
    return made;
}
function ensureProjectSubtitleLipSync(){
    if(!state.project?.scenes?.length)return 0;
    let made=0;beginHistoryBatch();
    for(const scene of state.project.scenes)made+=ensureSceneSubtitleLipSync(scene);
    endHistoryBatch();
    return made;
}
function pickAudioFile(){
    return new Promise(resolve=>{
        const input=$('#audioFileInput');if(!input){resolve(null);return}
        input.onchange=e=>{const f=e.target.files?.[0]||null;e.target.value='';resolve(f)};
        input.click();
    });
}
async function autoLipSync(){
    const scene=currentScene();if(!scene){toast('Open or import a project first.');return}
    const selected=currentLayer()?.type==='asset';
    const body=`<div class="propGrid"><label>Source</label><select id="lipSource"><option value="subtitles">Subtitles track</option><option value="audio">Audio file amplitude</option></select><label>Targets</label><select id="lipTargets"><option value="${selected?'selected':'all'}">${selected?'Selected character/object':'All character layers'}</option><option value="all">All character layers</option></select><label>Intensity</label><input id="lipIntensity" type="number" min=".1" max="3" step=".1" value="1"><label>Subtitle rate</label><input id="lipRate" type="number" min="2" max="20" step="1" value="9"><label>Narrator</label><input id="lipNarrator" type="checkbox"></div><div class="animHelp">Subtitle mode uses imported cue timing. Audio mode maps loudness over the whole current scene and works best on one selected speaking character.</div>`;
    const result=await showModal('Auto Lip Sync',body,[{label:'Cancel',value:null},{label:'Generate',primary:true,keep:true,onClick:(back,res)=>{res({source:back.querySelector('#lipSource').value,targets:back.querySelector('#lipTargets').value,intensity:+back.querySelector('#lipIntensity').value||1,rate:+back.querySelector('#lipRate').value||9,includeNarrator:back.querySelector('#lipNarrator').checked});back.remove()}}]);
    if(!result)return;
    const targets=lipSyncTargets(result.targets);if(!targets.length){alert('No target with a .mouth/.lip part was found. Select an imported character asset or import assets with a mouth element.');return}
    let made=0;beginHistoryBatch();
    try{
        if(result.source==='audio'){
            const file=await pickAudioFile();if(!file){endHistoryBatch();return}
            const frames=await mouthKeyframesFromAudioFile(file,scene,result.intensity);
            for(const target of targets){applyLipSyncToTarget(scene,target,frames);made++}
        }else{
            targets.forEach((target,i)=>{const cues=cuesForLipTarget(scene,target,i,targets.length,result.includeNarrator);if(!cues.length)return;applyLipSyncToTarget(scene,target,mouthKeyframesFromCues(cues,result.intensity,result.rate));made++});
        }
    }catch(err){endHistoryBatch();alert(`Lip sync failed:\n${err.message}`);return}
    endHistoryBatch();if(!made){alert('No usable subtitle/audio lip-sync data was found for the selected target settings.');return}
    state.selectedLayerId=scene.layers.find(l=>l.lipSync)?.id||state.selectedLayerId;renderAll();toast(`Generated lip sync for ${made} target${made===1?'':'s'}.`);
}

function deleteLayerById(id){
    const scene=currentScene();if(!scene)return;const layer=scene.layers.find(l=>l.id===id);if(!layer)return;
    beginHistoryBatch();const remove=new Set([id]);for(const other of scene.layers)if(other.targetLayerId===id)remove.add(other.id);scene.layers=scene.layers.filter(l=>!remove.has(l.id));endHistoryBatch();
    if(state.selectedLayerId&&remove.has(state.selectedLayerId))state.selectedLayerId=scene.layers[0]?.id||null;state.selectedKeyframe=null;state.selectedKeyframes=[];state.selectedPartPath=null;toast(`Deleted ${layer.name}${remove.size>1?` and ${remove.size-1} attached track${remove.size===2?'':'s'}`:''}.`);renderAll();
}
function deleteSelectedLayer(){if(state.selectedLayerId)deleteLayerById(state.selectedLayerId);else toast('Select a layer first.')}

function addAssetToScene(assetId){
    const scene=currentScene(),asset=state.project?.assets?.[assetId];if(!scene||!asset)return;const id=uid('layer');
    const animations=asset.animations||[];
    scene.layers.push({id,type:'asset',name:asset.name,assetId,kind:asset.kind,base:{x:100,y:100,width:parseFloat(asset.node?.style?.width)||150,height:parseFloat(asset.node?.style?.height)||150,rotation:0,scaleX:1,scaleY:1,opacity:1,z:0},clips:animations.map(a=>({clipId:a.id,name:a.name,speed:1,offset:0,loop:true,enabled:true})),tracks:{},locked:false,hidden:false});
    state.selectedLayerId=id;state.selectedAssetId=null;markDirty();renderAll();
}

function onPreviewLayerDown(e){
    const id=e.currentTarget.dataset.layerId,layer=currentScene()?.layers.find(l=>l.id===id);if(!layer||layer.locked)return;e.preventDefault();e.stopPropagation();selectLayer(id);
    const stageRect=$('#previewStage').getBoundingClientRect(),scale=stageRect.width/(state.project.meta.viewport.width||1280),startX=e.clientX,startY=e.clientY,ox=propAt(layer,'x',state.playhead,layer.base?.x||0),oy=propAt(layer,'y',state.playhead,layer.base?.y||0);beginHistoryBatch();state.drag={layer,startX,startY,ox,oy,scale};window.addEventListener('mousemove',onPreviewMove);window.addEventListener('mouseup',onPreviewUp,{once:true});
}
function onPreviewMove(e){if(!state.drag)return;const d=state.drag,x=d.ox+(e.clientX-d.startX)/d.scale,y=d.oy+(e.clientY-d.startY)/d.scale;if(state.autoKeyframe){setKeyframe(d.layer,'x',state.playhead,x,false);setKeyframe(d.layer,'y',state.playhead,y,false)}else{d.layer.base??={};d.layer.base.x=x;d.layer.base.y=y;markDirty()}applyAtPlayhead()}
function onPreviewUp(){window.removeEventListener('mousemove',onPreviewMove);if(state.drag){endHistoryBatch();renderTracks();renderInspector()}state.drag=null}
function onPreviewBackgroundDown(e){
    if(e.target!==$('#previewStage')&&e.target!==$('#previewCamera'))return;const layer=currentLayer();if(!layer||layer.type!=='camera'||layer.locked)return;e.preventDefault();
    const stageRect=$('#previewStage').getBoundingClientRect(),scale=stageRect.width/(state.project.meta.viewport.width||1280),startX=e.clientX,startY=e.clientY,ox=propAt(layer,'x',state.playhead,0),oy=propAt(layer,'y',state.playhead,0);beginHistoryBatch();state.drag={layer,startX,startY,ox,oy,scale};window.addEventListener('mousemove',onPreviewMove);window.addEventListener('mouseup',onPreviewUp,{once:true});
}

function addScene(){if(!state.project)return;const n=state.project.scenes.length+1,scene=defaultScene(uid('scene'),`Scene ${n}`);state.project.scenes.push(scene);state.currentSceneIndex=state.project.scenes.length-1;state.selectedLayerId=scene.layers[0].id;state.playhead=0;markDirty();renderAll()}
function deleteScene(){if(!state.project||!currentScene())return;if(!confirm(`Delete "${currentScene().name}"?`))return;state.project.scenes.splice(state.currentSceneIndex,1);state.currentSceneIndex=clamp(state.currentSceneIndex,0,Math.max(0,state.project.scenes.length-1));state.selectedLayerId=currentScene()?.layers[0]?.id||null;state.playhead=0;markDirty();renderAll()}

function newProject(){
    if(state.dirty&&!confirm('Discard unsaved changes?'))return;
    const body=`<div class="propGrid"><label>Name</label><input id="newProjectName" value="Untitled Movie"><label>Width</label><input id="newProjectW" type="number" value="1280"><label>Height</label><input id="newProjectH" type="number" value="720"><label>First scene</label><input id="newProjectScene" value="Scene 1"></div>`;
    showModal('New Project',body,[{label:'Cancel',value:null},{label:'Create',primary:true,keep:true,onClick:(back,res)=>{const name=back.querySelector('#newProjectName').value||'Untitled Movie',w=Math.max(160,+back.querySelector('#newProjectW').value||1280),h=Math.max(90,+back.querySelector('#newProjectH').value||720),sceneName=back.querySelector('#newProjectScene').value||'Scene 1';const project=emptyProject(name);project.meta.viewport={width:w,height:h};project.scenes=[defaultScene(uid('scene'),sceneName)];state.project=project;state.fileName='';state.filePath='';state.currentSceneIndex=0;state.selectedLayerId=project.scenes[0].layers[0].id;state.selectedAssetId=null;state.selectedKeyframe=null;state.selectedKeyframes=[];state.playhead=0;state.renderCache.clear();resetHistory(false);back.remove();res(project);renderAll();toast(`Created ${name}`)}}]);
}

function projectDuration(){return (state.project?.scenes||[]).reduce((sum,s)=>sum+Math.max(.01,s.duration||0),0)}
function sceneTimeFromProjectTime(time){
    const scenes=state.project?.scenes||[];let cursor=0;
    for(let i=0;i<scenes.length;i++){const dur=Math.max(.01,scenes[i].duration||0);if(time<=cursor+dur||i===scenes.length-1)return{scene:scenes[i],index:i,local:(time-cursor)/dur,offset:cursor,duration:dur};cursor+=dur}
    return{scene:null,index:0,local:0,offset:0,duration:1};
}
function renderViewerFrame(){
    const total=projectDuration(),v=state.viewer,info=sceneTimeFromProjectTime(clamp(v.time,0,total));
    if(!info.scene)return;
    if(v.sceneIndex!==info.index||!v.renderCache.size){v.sceneIndex=info.index;v.animationCache=new WeakMap();renderSceneInto($('#viewerStage'),$('#viewerCamera'),info.scene,v.renderCache,false);fitViewer()}
    applySceneAt(info.scene,clamp(info.local,0,1),$('#viewerCamera'),v.renderCache,v.animationCache,null);
    $('#viewerTitle').textContent=state.project?.meta?.name||'Project Viewer';$('#viewerSceneName').textContent=`${info.index+1}. ${info.scene.name}`;$('#viewerProgress').value=total?Math.round((v.time/total)*1000):0;$('#viewerTime').textContent=`${fmt(v.time)} / ${fmt(total)} s`;
}
function openProjectViewer(){
    if(!state.project||!state.project.scenes?.length){toast('Create or open a project first.');return}
    const lipSyncCount=ensureProjectSubtitleLipSync();
    state.viewer.open=true;state.viewer.playing=false;state.viewer.time=0;state.viewer.sceneIndex=-1;state.viewer.renderCache.clear();state.viewer.animationCache=new WeakMap();$('#projectViewer').classList.remove('hidden');$('#viewerPlayBtn').textContent='Play';renderViewerFrame();
    if(lipSyncCount)toast(`Auto-applied subtitle lip sync to ${lipSyncCount} target${lipSyncCount===1?'':'s'}.`,3200);
}
function closeProjectViewer(){state.viewer.open=false;state.viewer.playing=false;$('#projectViewer').classList.add('hidden')}
function viewerPlayToggle(){state.viewer.playing=!state.viewer.playing;$('#viewerPlayBtn').textContent=state.viewer.playing?'Pause':'Play';state.viewer.lastFrameTime=performance.now();if(state.viewer.playing)requestAnimationFrame(viewerPlayLoop)}
function viewerPlayLoop(now){
    const v=state.viewer;if(!v.open||!v.playing)return;const total=projectDuration(),dt=(now-v.lastFrameTime)/1000;v.lastFrameTime=now;v.time=clamp(v.time+dt,0,total);renderViewerFrame();if(v.time>=total){v.playing=false;$('#viewerPlayBtn').textContent='Play';return}requestAnimationFrame(viewerPlayLoop);
}

function sanitizeSvgMarkup(svg){
    const doc=new DOMParser().parseFromString(String(svg||''),'image/svg+xml'),root=doc.documentElement;
    if(root.nodeName.toLowerCase()==='parsererror')throw new Error('Invalid SVG markup.');
    root.querySelectorAll('script,foreignObject').forEach(n=>n.remove());
    root.querySelectorAll('*').forEach(el=>{for(const attr of [...el.attributes])if(/^on/i.test(attr.name)||/javascript:/i.test(attr.value))el.removeAttribute(attr.name)});
    if(root.nodeName.toLowerCase()!=='svg')throw new Error('Markup must start with an <svg> element.');
    root.setAttribute('width','100%');root.setAttribute('height','100%');root.setAttribute('preserveAspectRatio',root.getAttribute('preserveAspectRatio')||'xMidYMid meet');
    return new XMLSerializer().serializeToString(root);
}
function animationCodeTemplate(){
    return JSON.stringify([
        {name:'Idle',duration:1.2,easing:'ease-in-out',iterations:'infinite',direction:'normal',frames:[
            {offset:'0%',style:{transform:'translateY(0px) scale(1)'}},
            {offset:'50%',style:{transform:'translateY(-10px) scale(1.04)'}},
            {offset:'100%',style:{transform:'translateY(0px) scale(1)'}}
        ]},
        {name:'Pulse',duration:.8,easing:'ease-in-out',iterations:'infinite',direction:'normal',frames:[
            {offset:'0%',style:{transform:'scale(.96)',opacity:'.78'}},
            {offset:'50%',style:{transform:'scale(1.06)',opacity:'1'}},
            {offset:'100%',style:{transform:'scale(.96)',opacity:'.78'}}
        ]}
    ],null,2);
}
function assetAnimationCode(asset){
    return JSON.stringify((asset.animations||[]).map(clip=>{
        const animName=(clip.keyframeNames||[])[0]||clip.name,def=state.project?.animationLibrary?.[animName]||{};
        return{name:clip.name,duration:clip.duration||1,easing:clip.timing||'linear',iterations:clip.iterations||'infinite',direction:clip.direction||'normal',frames:def.frames||[]};
    }),null,2);
}
function applyAnimationCodeToAsset(asset,code){
    const defs=JSON.parse(code);if(!Array.isArray(defs))throw new Error('Animation code must be a JSON array.');
    const names=[],durations=[],delays=[],iters=[],dirs=[],timings=[],clips=[];
    asset.node.nativeAnimations={names,duration:'',delay:'',iterationCount:'',direction:'',timingFunction:''};
    defs.forEach((def,i)=>{
        if(!def||typeof def!=='object')throw new Error(`Animation ${i+1} must be an object.`);
        const name=String(def.name||`Animation ${i+1}`).trim(),duration=Math.max(.01,+def.duration||1),frames=def.frames;
        if(!Array.isArray(frames)||!frames.length)throw new Error(`${name} needs a non-empty frames array.`);
        const animId=`asset_${simpleHash(`${asset.id}:${name}`)}`;
        state.project.animationLibrary[animId]={name:animId,frames:frames.map(frame=>({offset:String(frame.offset??'0%'),style:frame.style&&typeof frame.style==='object'?frame.style:{}}))};
        names.push(animId);durations.push(`${duration}s`);delays.push(`${+def.delay||0}s`);iters.push(def.iterations||'infinite');dirs.push(def.direction||'normal');timings.push(def.easing||def.timing||'linear');
        clips.push({id:`clip_${simpleHash(name)}`,name,keyframeNames:[animId],duration,delay:+def.delay||0,iterations:def.iterations||'infinite',direction:def.direction||'normal',timing:def.easing||def.timing||'linear',source:'code'});
    });
    asset.node.nativeAnimations.duration=durations.join(', ');asset.node.nativeAnimations.delay=delays.join(', ');asset.node.nativeAnimations.iterationCount=iters.join(', ');asset.node.nativeAnimations.direction=dirs.join(', ');asset.node.nativeAnimations.timingFunction=timings.join(', ');
    asset.animations=clips;asset.nativeAnimations=clips.map(c=>c.name);asset.animationCode=code;
    for(const scene of state.project.scenes||[])for(const layer of scene.layers||[])if(layer.assetId===asset.id)ensureLayerHasAssetClips(layer,asset);
}
function newAsset(){
    if(!state.project){toast('Load or create a project first.');return}
    const sample='<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg"><circle cx="60" cy="60" r="42" fill="#8fb8ff" stroke="#1b2230" stroke-width="6"/><circle cx="46" cy="52" r="5" fill="#111"/><circle cx="74" cy="52" r="5" fill="#111"/><path d="M42 76 Q60 88 78 76" fill="none" stroke="#111" stroke-width="5" stroke-linecap="round"/></svg>';
    const body=`<div class="propGrid"><label>Name</label><input id="newAssetName" value="SVG Animated Asset"><label>Type</label><select id="newAssetType"><option value="asset">Object</option><option value="character">Character</option></select><label>Width</label><input id="newAssetW" type="number" value="160"><label>Height</label><input id="newAssetH" type="number" value="160"></div><div class="sectionTitle">SVG Markup</div><textarea id="newAssetSvg">${escapeHtml(sample)}</textarea><div class="sectionTitle">Animations JSON</div><textarea id="newAssetAnimations">${escapeHtml(animationCodeTemplate())}</textarea>`;
    showModal('New SVG Animation Asset',body,[{label:'Cancel',value:null},{label:'Create',primary:true,keep:true,onClick:(back,res)=>{try{const name=back.querySelector('#newAssetName').value||'SVG Animated Asset',kind=back.querySelector('#newAssetType').value,w=Math.max(1,+back.querySelector('#newAssetW').value||160),h=Math.max(1,+back.querySelector('#newAssetH').value||160),svgMarkup=sanitizeSvgMarkup(back.querySelector('#newAssetSvg').value),id=uid('asset'),asset={id,name,kind,node:{tag:'div',path:'0',classes:['custom-svg-asset'],style:{position:'relative',width:`${w}px`,height:`${h}px`,display:'block',transformOrigin:'50% 50%'},svgMarkup,children:[]},animations:[],nativeAnimations:[],createdFrom:'editor-svg',tags:['custom','svg','animated']};state.project.assets[id]=asset;applyAnimationCodeToAsset(asset,back.querySelector('#newAssetAnimations').value);state.selectedAssetId=id;state.selectedLayerId=null;markDirty();back.remove();res(id);renderAssets();renderInspector();toast(`Created ${name}`)}catch(err){alert(err.message)}}}]);
}

async function saveProject(asNew=false){
    if(!state.project)return;const suggested=(state.fileName||(state.project.meta.name||'movie').replace(/[^a-z0-9_-]+/gi,'_')+'.movie.json').replace(/\.json\.json$/i,'.json');state.project.meta.modifiedAt=new Date().toISOString();
    try{
        if(window.pywebview?.api?.save_project){const result=await window.pywebview.api.save_project(JSON.stringify(state.project),suggested,state.filePath||'',!!asNew);if(result?.cancelled)return;if(!result?.ok)throw new Error(result?.error||'Native save failed');state.fileName=result.name;state.filePath=result.path||'';resetHistory(true);toast(`Saved ${result.name}`);return}
        const blob=new Blob([JSON.stringify(state.project,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=suggested;a.click();URL.revokeObjectURL(a.href);state.fileName=suggested;resetHistory(true);toast(`Saved ${suggested}`);
    }catch(e){alert(`Save failed:\n${e.message}`)}
}
function migrateProject(project){
    project.assets??={};project.animationLibrary??={};project.scenes??=[];
    for(const asset of Object.values(project.assets)){if(!asset.animations)asset.animations=(asset.nativeAnimations||[]).map(name=>({id:`clip_${simpleHash(name)}`,name,duration:1,delay:0,iterations:'infinite',direction:'normal',timing:'linear',source:'legacy-import'}));asset.animations=groupAssetAnimationList(asset.animations);asset.nativeAnimations=asset.animations.map(a=>a.name)}
    for(const scene of project.scenes){
        scene.layers??=[];
        for(const layer of scene.layers)if(layer.clips?.length){const asset=project.assets[layer.assetId];layer.clips=normalizeSceneClipList(layer.clips,asset);for(const clip of layer.clips)clip.loop??=true}
        const mergedClipLayers=new Set();
        for(const layer of scene.layers)if(layer.type==='animation'&&layer.animationKind==='clip'){
            layer.clips??=[];
            const target=scene.layers.find(l=>l.id===layer.targetLayerId),asset=target?project.assets[target.assetId]:null;
            layer.clips=normalizeSceneClipList(layer.clips,asset);for(const clip of layer.clips)clip.loop??=true;
            if(target){target.clips=normalizeSceneClipList([...(target.clips||[]),...layer.clips],asset);mergedClipLayers.add(layer.id)}
        }
        if(mergedClipLayers.size)scene.layers=scene.layers.filter(l=>!mergedClipLayers.has(l.id));
        for(const layer of scene.layers)if(layer.type==='asset')ensureLayerHasAssetClips(layer,project.assets[layer.assetId]);
    }
    return project;
}
function loadProjectObject(project,name='',path=''){
    if(project?.format!==FORMAT)throw new Error('This is not an Unlim8ted Movie Project JSON file.');migrateProject(project);state.project=project;state.fileName=name;state.filePath=path;state.currentSceneIndex=0;state.selectedLayerId=project.scenes?.[0]?.layers?.[0]?.id||null;state.selectedAssetId=null;state.selectedKeyframe=null;state.selectedKeyframes=[];state.selectedPartPath=null;state.playhead=0;state.renderCache.clear();resetHistory(true);renderAll();toast(`Opened ${project.meta?.name||name}`);
}

function playToggle(){state.playing=!state.playing;$('#playBtn').textContent=state.playing?'Pause':'Play';state.lastFrameTime=performance.now();if(state.playing)requestAnimationFrame(playLoop)}
function playLoop(now){if(!state.playing)return;const scene=currentScene();if(!scene){state.playing=false;return}const speed=+$('#playSpeed').value||1;const dt=(now-state.lastFrameTime)/1000;state.lastFrameTime=now;state.playhead+=dt*speed/Math.max(.01,scene.duration);if(state.playhead>=1){state.playhead=1;state.playing=false;$('#playBtn').textContent='Play'}applyAtPlayhead();if(state.playing)requestAnimationFrame(playLoop)}

$('#newProjectBtn').onclick=newProject;
$('#loadHtmlBtn').onclick=()=>$('#htmlFileInput').click();
$('#mergeReferenceBtn').onclick=mergeReferenceAnimations;
$('#loadProjectBtn').onclick=()=>$('#projectFileInput').click();
$('#autoKeyframeToggle').onchange=e=>{state.autoKeyframe=e.target.checked;toast(`Auto keyframe ${state.autoKeyframe?'on':'off'}.`)};
$('#saveBtn').onclick=()=>saveProject(false);$('#saveAsBtn').onclick=()=>saveProject(true);$('#undoBtn').onclick=undo;$('#redoBtn').onclick=redo;$('#lipSyncBtn').onclick=autoLipSync;$('#projectViewerBtn').onclick=openProjectViewer;$('#addSceneBtn').onclick=addScene;$('#deleteLayerBtn').onclick=deleteSelectedLayer;$('#deleteSceneBtn').onclick=deleteScene;$('#newAssetBtn').onclick=newAsset;$('#assetSearch').oninput=renderAssets;
$('#playBtn').onclick=playToggle;$('#jumpStartBtn').onclick=()=>{state.playhead=0;applyAtPlayhead();renderInspector()};$('#jumpEndBtn').onclick=()=>{state.playhead=1;applyAtPlayhead();renderInspector()};$('#timeSlider').oninput=e=>{state.playhead=+e.target.value/1000;applyAtPlayhead();renderInspector()};
$('#viewerCloseBtn').onclick=closeProjectViewer;$('#viewerPlayBtn').onclick=viewerPlayToggle;$('#viewerJumpStartBtn').onclick=()=>{state.viewer.time=0;state.viewer.sceneIndex=-1;state.viewer.animationCache=new WeakMap();renderViewerFrame()};$('#viewerProgress').oninput=e=>{state.viewer.time=(+e.target.value/1000)*projectDuration();state.viewer.sceneIndex=-1;state.viewer.animationCache=new WeakMap();renderViewerFrame()};
$('#previewStage').addEventListener('mousedown',onPreviewBackgroundDown);
$('#htmlFileInput').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;const settings=await requestImportSettings(f.name);if(!settings)return;try{await importFromHtml(f.name,await f.text(),settings)}catch(err){alert(err.message)}};
$('#projectFileInput').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;if(state.dirty&&!confirm('Discard unsaved changes?'))return;try{loadProjectObject(JSON.parse(await f.text()),f.name,'')}catch(err){alert(err.message)}};
window.addEventListener('keydown',e=>{
    const key=e.key.toLowerCase(),editing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName);
    if(e.key==='Escape'&&state.viewer.open){e.preventDefault();closeProjectViewer();return}
    if(e.code==='Space'){e.preventDefault();state.viewer.open?viewerPlayToggle():playToggle();return}
    if((e.ctrlKey||e.metaKey)&&key==='c'&&!editing&&state.selectedKeyframes?.length){e.preventDefault();copySelectedKeyframes();return}
    if((e.ctrlKey||e.metaKey)&&key==='v'&&!editing&&state.keyframeClipboard?.length){e.preventDefault();pasteKeyframesAtPlayhead();return}
    if((e.ctrlKey||e.metaKey)&&key==='z'){e.preventDefault();e.shiftKey?redo():undo();return}
    if((e.ctrlKey||e.metaKey)&&key==='y'){e.preventDefault();redo();return}
    if((e.ctrlKey||e.metaKey)&&key==='s'){e.preventDefault();saveProject(e.shiftKey);return}
    if((e.key==='Delete'||e.key==='Backspace')&&!editing){e.preventDefault();if(deleteSelectedKeyframes())return;if(state.selectedLayerId)deleteSelectedLayer();return}
    if(e.key==='ArrowLeft'&&!editing){state.playhead=clamp(state.playhead-.01,0,1);applyAtPlayhead();renderInspector()}else if(e.key==='ArrowRight'&&!editing){state.playhead=clamp(state.playhead+.01,0,1);applyAtPlayhead();renderInspector()}
});
window.addEventListener('beforeunload',e=>{if(state.dirty){e.preventDefault();e.returnValue=''}});

renderAll();
setTimeout(()=>toast('Movie Editor v1.3.0 - desktop build with layer deletion, live asset previews, undo/redo, import retiming, and expanded motion import.'),250);
</script>
</body>
</html>"""


def _safe_file(name: str, allowed_suffixes: tuple[str, ...] | None = None) -> Path:
    """Resolve a filename only within the script directory."""
    name = Path(unquote(name)).name
    if not name:
        raise ValueError("Missing filename")
    path = (ROOT / name).resolve()
    if path.parent != ROOT.resolve():
        raise ValueError("Invalid path")
    if allowed_suffixes and not any(name.lower().endswith(s) for s in allowed_suffixes):
        raise ValueError("Unsupported file type")
    return path


def _transform_import_html(text: str) -> str:
    """Prepare an HTML movie for one-time structured import.

    This transformed copy is served only to the hidden importer iframe. It is
    never written to disk and never stored in project JSON.
    """
    # External/module application integrations are irrelevant to the importer
    # and can fail on localhost, so remove only module scripts.
    text = re.sub(
        r"<script\b[^>]*\btype\s*=\s*(['\"])module\1[^>]*>.*?</script\s*>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<script\b[^>]*\btype\s*=\s*(['\"])module\1[^>]*/\s*>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Expose the movie's existing sequence registry without changing the source
    # file. This lets the importer evaluate animation functions at arbitrary
    # normalized progress values instead of slowly scrolling through the film.
    text, count = re.subn(
        r"\bconst\s+sequences\s*=\s*\[",
        "const sequences = window.__editorSequences = [",
        text,
        count=1,
    )
    if not count:
        text = text.replace(
            "<head>",
            "<head><script>window.__editorSequences=[];</script>",
            1,
        )

    freeze_css = """
<style id="__movie_editor_import_freeze">
html { scroll-behavior:auto !important; }
*, *::before, *::after {
    animation-play-state: paused !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
}
site-navbar, .mobile-landscape { display:none !important; }
</style>
<script>window.__MOVIE_EDITOR_IMPORT__ = true;</script>
"""
    if "</head>" in text.lower():
        idx = text.lower().rfind("</head>")
        text = text[:idx] + freeze_css + text[idx:]
    else:
        text = freeze_css + text
    return text


class Handler(BaseHTTPRequestHandler):
    server_version = "Unlim8tedMovieEditor/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # Keep the terminal useful without printing every asset/source request.
        if self.path.startswith("/api/") and not self.path.startswith("/api/files"):
            sys.stdout.write("[editor] " + (fmt % args) + "\n")

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(body, "application/json; charset=utf-8", status)

    def _error(self, message: str, status: int = 400) -> None:
        self._send(message.encode("utf-8"), "text/plain; charset=utf-8", status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self._send(EDITOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return

            if parsed.path == "/app-icon.svg":
                self._send(APP_ICON_SVG.encode("utf-8"), "image/svg+xml; charset=utf-8")
                return

            if parsed.path == "/api/files":
                kind = q.get("kind", ["html"])[0]
                files = []
                for p in ROOT.iterdir():
                    if not p.is_file():
                        continue
                    if kind == "html":
                        ok = p.suffix.lower() in {".html", ".htm"}
                    else:
                        ok = p.suffix.lower() == ".json"
                        if ok:
                            try:
                                with p.open("r", encoding="utf-8") as f:
                                    prefix = f.read(4096)
                                ok = PROJECT_FORMAT in prefix
                            except OSError:
                                ok = False
                    if ok:
                        st = p.stat()
                        files.append(
                            {
                                "name": p.name,
                                "size": st.st_size,
                                "modified": time.strftime(
                                    "%Y-%m-%d %H:%M", time.localtime(st.st_mtime)
                                ),
                            }
                        )
                files.sort(key=lambda x: x["name"].lower())
                self._json({"files": files})
                return

            if parsed.path == "/api/import-source":
                path = _safe_file(q.get("name", [""])[0], (".html", ".htm"))
                if not path.exists():
                    self._error("HTML file not found", 404)
                    return
                text = path.read_text(encoding="utf-8", errors="replace")
                transformed = _transform_import_html(text)
                self._send(transformed.encode("utf-8"), "text/html; charset=utf-8")
                return

            if parsed.path == "/api/raw":
                path = _safe_file(q.get("name", [""])[0], (".html", ".htm"))
                if not path.exists():
                    self._error("File not found", 404)
                    return
                self._send(path.read_bytes(), "text/html; charset=utf-8")
                return

            if parsed.path == "/api/project":
                path = _safe_file(q.get("name", [""])[0], (".json",))
                if not path.exists():
                    self._error("Project file not found", 404)
                    return
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("format") != PROJECT_FORMAT:
                    self._error("Not an Unlim8ted Movie Project", 400)
                    return
                self._json(data)
                return

            self._error("Not found", 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(str(exc), 400)
        except Exception as exc:  # pragma: no cover - server guard
            self._error(f"Server error: {exc}", 500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 200 * 1024 * 1024:
                self._error("Request too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            payload = (
                json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            )

            if parsed.path == "/api/save":
                name = payload.get("name", "")
                project = payload.get("project")
                if (
                    not isinstance(project, dict)
                    or project.get("format") != PROJECT_FORMAT
                ):
                    self._error("Invalid project data", 400)
                    return
                path = _safe_file(name, (".json",))
                if not path.name.lower().endswith(".json"):
                    path = path.with_suffix(".json")
                project.setdefault("meta", {})["modifiedAt"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%S%z"
                )

                # Explicitly reject accidental raw-HTML embedding at the top
                # level. Structured asset node trees are expected; source HTML
                # strings are not.
                for forbidden in ("html", "sourceHtml", "rawHtml", "documentHtml"):
                    if forbidden in project:
                        self._error(
                            f"Project contains forbidden raw HTML field: {forbidden}"
                        )
                        return

                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_text(
                    json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                os.replace(tmp, path)
                self._json({"ok": True, "name": path.name, "size": path.stat().st_size})
                return

            self._error("Not found", 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(str(exc), 400)
        except Exception as exc:  # pragma: no cover - server guard
            self._error(f"Server error: {exc}", 500)


def _ensure_pywebview(auto_install: bool = True):
    """Import pywebview, optionally installing it for this Python environment."""
    try:
        import webview  # type: ignore

        return webview
    except ImportError:
        if not auto_install:
            raise RuntimeError(
                "pywebview is required for the desktop editor. Install it with: "
                f"{sys.executable} -m pip install pywebview"
            )
        print("pywebview is not installed. Installing it now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pywebview"])
        import webview  # type: ignore

        return webview


def _start_editor_server() -> tuple[ThreadingHTTPServer, str]:
    """Serve the editor from localhost instead of injecting a huge HTML string.

    Some pywebview backends can become unresponsive while loading a very large
    inline HTML payload. A local threaded server lets the webview stream the
    document normally and also keeps the existing API endpoints available.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, name="editor-http", daemon=True
    )
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/"


def _ensure_app_icon() -> Path:
    APP_ICON.write_text(APP_ICON_SVG, encoding="utf-8")
    return APP_ICON


class DesktopApi:
    """Small native bridge used only for desktop file saving.

    HTML and JSON loading are handled by normal file inputs inside the webview,
    which invoke the operating system's file picker. No source movie HTML is compiled into this Python file.
    """

    def __init__(self, webview_module):
        self.webview = webview_module
        self.window = None

    def attach(self, window) -> None:
        self.window = window

    def save_project(
        self,
        project_text: str,
        suggested_name: str,
        current_path: str = "",
        save_as: bool = False,
    ) -> dict:
        if self.window is None:
            return {"ok": False, "error": "Editor window is not ready."}

        path: Path | None = None
        if current_path and not save_as:
            candidate = Path(current_path).expanduser()
            if candidate.suffix.lower() == ".json":
                path = candidate

        if path is None:
            dialog_type = getattr(
                getattr(self.webview, "FileDialog", object),
                "SAVE",
                getattr(self.webview, "SAVE_DIALOG", 30),
            )
            result = self.window.create_file_dialog(
                dialog_type,
                directory=str(ROOT),
                save_filename=suggested_name,
                file_types=("Movie project (*.movie.json;*.json)", "JSON (*.json)"),
            )
            if not result:
                return {"ok": False, "cancelled": True}
            selected = result[0] if isinstance(result, (tuple, list)) else result
            path = Path(selected)

        if not path.name.lower().endswith(".json"):
            path = path.with_suffix(
                path.suffix + ".json" if path.suffix else ".movie.json"
            )

        # Validate before writing, including a recursive guard against accidentally
        # stuffing the original HTML source into a JSON project.
        project = json.loads(project_text)
        if project.get("format") != PROJECT_FORMAT:
            return {"ok": False, "error": "Invalid movie project format."}
        forbidden = {"html", "sourcehtml", "rawhtml", "documenthtml"}
        stack = [project]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, child in value.items():
                    if str(key).lower() in forbidden:
                        return {
                            "ok": False,
                            "error": f"Forbidden raw HTML field: {key}",
                        }
                    stack.append(child)
            elif isinstance(value, list):
                stack.extend(value)

        project.setdefault("meta", {})["modifiedAt"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, path)
        return {
            "ok": True,
            "path": str(path),
            "name": path.name,
            "size": path.stat().st_size,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unlim8ted desktop movie timeline editor"
    )
    parser.add_argument(
        "--no-auto-install",
        action="store_true",
        help="Do not automatically install pywebview if it is missing",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable pywebview debug tools"
    )
    args = parser.parse_args()

    try:
        webview = _ensure_pywebview(auto_install=not args.no_auto_install)
    except Exception as exc:
        print(f"Could not start the desktop editor: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    api = DesktopApi(webview)
    server, url = _start_editor_server()
    icon_path = _ensure_app_icon()
    window_options = {
        "url": url,
        "js_api": api,
        "width": 1500,
        "height": 940,
        "min_size": (1080, 700),
        "text_select": True,
        "icon": str(icon_path),
    }
    try:
        try:
            window = webview.create_window(f"Unlim8ted Movie Editor {APP_VERSION}", **window_options)
        except TypeError:
            window_options.pop("icon", None)
            window = webview.create_window(f"Unlim8ted Movie Editor {APP_VERSION}", **window_options)
    except Exception:
        server.shutdown()
        server.server_close()
        raise
    api.attach(window)

    print(f"Unlim8ted Movie Editor {APP_VERSION}")
    print(f"Desktop window mode at {url}")
    print("Source HTML is loaded only when you choose it in the editor.")
    try:
        webview.start(debug=args.debug)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
