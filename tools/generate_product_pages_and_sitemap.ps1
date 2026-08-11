param(
  [string]$FrontendDir = "frontend"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$SiteOrigin = "https://unlim8ted.com"
$ProductsJson = Join-Path $Root "assets/data/products.json"
$TemplateFile = Join-Path $Root "frontend/products/product/template.html"
$FrontendPath = [System.IO.Path]::GetFullPath((Join-Path $Root $FrontendDir))
$ProductIndexDir = Join-Path $FrontendPath "products/product"
$SitemapFile = Join-Path $FrontendPath "sitemap.xml"

function First-Text {
  foreach ($Value in $args) {
    if ($null -ne $Value) {
      $Text = [string]$Value
      if ($Text.Trim()) { return $Text.Trim() }
    }
  }
  return ""
}

function Html-Escape([string]$Value) {
  return [System.Net.WebUtility]::HtmlEncode($Value)
}

function Json-String([string]$Value) {
  return ($Value | ConvertTo-Json -Compress)
}

function Json-Object($Value) {
  return ($Value | ConvertTo-Json -Depth 40 -Compress)
}

function Product-Json($Product) {
  $Copy = [ordered]@{}
  foreach ($Property in $Product.PSObject.Properties) {
    if ($Property.Name -like "_generated_*") { continue }
    $Copy[$Property.Name] = $Property.Value
  }
  return Json-Object $Copy
}

function Slugify([string]$Value) {
  $Normalized = $Value.Normalize([Text.NormalizationForm]::FormD)
  $Builder = [System.Text.StringBuilder]::new()
  foreach ($Char in $Normalized.ToCharArray()) {
    if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($Char) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
      [void]$Builder.Append($Char)
    }
  }
  $Slug = $Builder.ToString().ToLowerInvariant()
  $Slug = $Slug -replace "&", " and "
  $Slug = $Slug -replace "[^a-z0-9]+", "-"
  $Slug = $Slug -replace "-{2,}", "-"
  $Slug = $Slug.Trim("-")
  if ($Slug) { return $Slug }
  return "product"
}

function Product-Date($Product, [string]$FallbackDate) {
  foreach ($Key in @("lastmod", "lastModified", "updated", "updatedAt", "updated_at", "modified", "modifiedAt", "dateModified")) {
    if ($Product.PSObject.Properties.Name -contains $Key) {
      $Raw = First-Text $Product.$Key
      if ($Raw -match "\d{4}-\d{2}-\d{2}") { return $Matches[0] }
      try {
        return ([DateTimeOffset]::Parse($Raw)).UtcDateTime.ToString("yyyy-MM-dd")
      } catch {}
    }
  }
  return $FallbackDate
}

function Product-Type($Product) {
  $Value = ""
  if ($Product.PSObject.Properties.Name -contains "product-type") { $Value = $Product."product-type" }
  elseif ($Product.PSObject.Properties.Name -contains "productType") { $Value = $Product.productType }
  elseif ($Product.PSObject.Properties.Name -contains "type") { $Value = $Product.type }
  return (First-Text $Value).ToLowerInvariant()
}

function Product-Route($Product) {
  switch (Product-Type $Product) {
    "image" { return "/products/images/" }
    "music" { return "/products/music/" }
    "book" { return "/products/books/" }
    "film" { return "/products/films/" }
    "software" { return "/products/software/" }
    "video-game" { return "/products/games/" }
    "card-game" { return "/products/games/" }
    "physical" { return "/products/physical-items/" }
    "instant" { return "/products/physical-items/" }
    "ai" { return "/products/ai/" }
    default { return "/products/product/" }
  }
}

function Should-Generate-ProductPage($Product) {
  $Type = Product-Type $Product
  return $Type -ne "music" -and $Type -ne "podcast" -and $Type -ne "podcasts"
}

function Product-Sources($Product) {
  $Sources = @()
  if (First-Text $Product.image) {
    $Sources += [pscustomobject]@{ Type = "img"; Src = (First-Text $Product.image) }
  }
  if ((Product-Type $Product) -eq "image" -and (First-Text $Product.file)) {
    $Sources += [pscustomobject]@{ Type = "img"; Src = (First-Text $Product.file) }
  }
  foreach ($Image in @($Product.images)) {
    if (First-Text $Image) { $Sources += [pscustomobject]@{ Type = "img"; Src = (First-Text $Image) } }
  }
  foreach ($Image in @($Product.additional_images)) {
    if (First-Text $Image) { $Sources += [pscustomobject]@{ Type = "img"; Src = (First-Text $Image) } }
  }
  if (First-Text $Product.video) {
    $Sources += [pscustomobject]@{ Type = "video"; Src = (First-Text $Product.video) }
  }
  foreach ($Video in @($Product.additional_videos)) {
    if (First-Text $Video) { $Sources += [pscustomobject]@{ Type = "video"; Src = (First-Text $Video) } }
  }
  return @($Sources | Where-Object { $_.Src } | Select-Object -First 12)
}

function To-Money($Value) {
  $Number = 0
  if ([double]::TryParse(([string]$Value), [ref]$Number)) {
    return "$" + $Number.ToString("N2")
  }
  return "$0.00"
}

function Product-Price($Product) {
  $Variants = @($Product.varients)
  if (!$Variants.Count) { $Variants = @($Product.variants) }
  $Prices = @()
  foreach ($Variant in $Variants) {
    $Number = 0
    if ($null -ne $Variant.price -and [double]::TryParse(([string]$Variant.price), [ref]$Number)) {
      $Prices += $Number
    }
  }

  if ($Prices.Count) {
    $Min = ($Prices | Measure-Object -Minimum).Minimum
    $Max = ($Prices | Measure-Object -Maximum).Maximum
    if ($Min -eq $Max) { return To-Money $Min }
    return "$(To-Money $Min) - $(To-Money $Max)"
  }

  return To-Money $Product.price
}

function Product-Hero($Product) {
  $Name = First-Text $Product.name $Product.title $Product.id
  $Sources = @(Product-Sources $Product)
  if (!$Sources.Count) {
    return '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:rgba(255,255,255,.55);">No media</div>'
  }

  $First = $Sources[0]
  $Src = Html-Escape $First.Src
  $Alt = Html-Escape $Name
  if ($First.Type -eq "img") {
    return "<img src=""$Src"" alt=""$Alt"" loading=""eager"" decoding=""async"">"
  }

  if ($First.Src -match "youtu\.be/([^?&/]+)|youtube\.com/watch\?v=([^?&]+)") {
    $Id = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
    return "<iframe src=""https://www.youtube.com/embed/$(Html-Escape $Id)"" title=""$Alt"" allow=""accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"" allowfullscreen></iframe>"
  }

  return "<video controls src=""$Src""></video>"
}

function Product-Thumbs($Product) {
  $Name = First-Text $Product.name $Product.title $Product.id
  $Sources = @(Product-Sources $Product)
  $Thumbs = @()
  foreach ($Source in $Sources) {
    if ($Source.Type -eq "img") {
      $Thumbs += "<div class=""thumb""><img src=""$(Html-Escape $Source.Src)"" alt=""$(Html-Escape $Name)"" loading=""lazy"" decoding=""async""></div>"
    } else {
      $Thumbs += '<div class="thumb"><div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.75);font-weight:800;">&#9654;</div></div>'
    }
  }
  return $Thumbs -join "`n"
}

function Render-Template($Template, $Product) {
  if ($null -eq $Product) {
    $Title = "Unlim8ted - Product"
    $Description = "Unlim8ted Product page. Powered by Unlim8ted Studio Productions"
    $Canonical = "$SiteOrigin/products/product/"
    $Bootstrap = ""
    $ProductName = "Product"
    $ProductDescription = ""
    $ProductPrice = "$—"
    $ProductHero = ""
    $ProductThumbs = ""
    $BuyHref = "#"
  } else {
    $ProductId = [string]$Product.id
    $TitleName = First-Text $Product.name $Product.title $ProductId
    $Title = "$TitleName - Unlim8ted"
    $Description = First-Text $Product.description $Product.desc "$TitleName by Unlim8ted Studio Productions"
    if ($Description.Length -gt 300) { $Description = $Description.Substring(0, 300) }
    $Canonical = "$SiteOrigin$($Product._generated_route)$($Product._generated_slug)/"
    $Bootstrap = "<script>window.UNLIM8TED_PRODUCT_ID = $(Json-String $ProductId); window.UNLIM8TED_PRODUCT = $(Product-Json $Product);</script>"
    $ProductName = $TitleName
    $ProductDescription = First-Text $Product.description $Product.desc
    $ProductPrice = Product-Price $Product
    $ProductHero = Product-Hero $Product
    $ProductThumbs = Product-Thumbs $Product
    $BuyHref = "/cart?source=buy&product=$([uri]::EscapeDataString($ProductId))"
  }

  return $Template.
    Replace("{{TITLE}}", (Html-Escape $Title)).
    Replace("{{DESCRIPTION}}", (Html-Escape $Description)).
    Replace("{{CANONICAL_URL}}", (Html-Escape $Canonical)).
    Replace("{{PRODUCT_BOOTSTRAP}}", $Bootstrap).
    Replace("{{PRODUCT_NAME}}", (Html-Escape $ProductName)).
    Replace("{{PRODUCT_DESCRIPTION}}", (Html-Escape $ProductDescription)).
    Replace("{{PRODUCT_PRICE}}", (Html-Escape $ProductPrice)).
    Replace("{{PRODUCT_HERO}}", $ProductHero).
    Replace("{{PRODUCT_THUMBS}}", $ProductThumbs).
    Replace("{{BUY_HREF}}", (Html-Escape $BuyHref))
}

function Sitemap-Url([string]$Loc, [string]$LastMod) {
  return @"
  <url>
    <loc>$(Html-Escape $Loc)</loc>
    <lastmod>$(Html-Escape $LastMod)</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.80</priority>
  </url>
"@
}

if (!(Test-Path $FrontendPath)) { throw "FrontendDir not found: $FrontendPath" }
if (!(Test-Path $SitemapFile)) { throw "sitemap.xml not found: $SitemapFile" }

$Raw = Get-Content -Raw -Path $ProductsJson | ConvertFrom-Json
$Products = if ($Raw -is [array]) { $Raw } else { $Raw.products }
if ($null -eq $Products) { throw "products.json must be an array or an object with a products array" }

$Products = @($Products | Where-Object { $null -ne $_ -and $_.id })
$Seen = @{}
foreach ($Product in $Products) {
  $Route = Product-Route $Product
  $Product | Add-Member -NotePropertyName "_generated_route" -NotePropertyValue $Route -Force

  $Base = Slugify (First-Text $Product.slug $Product.handle $Product.id $Product.name)
  $SeenKey = "$Route|$Base"
  $Count = if ($Seen.ContainsKey($SeenKey)) { $Seen[$SeenKey] } else { 0 }
  $Seen[$SeenKey] = $Count + 1
  $Slug = if ($Count -eq 0) { $Base } else { "$Base-$(Slugify ([string]$Product.id))" }
  $Product | Add-Member -NotePropertyName "_generated_slug" -NotePropertyValue $Slug -Force
}

$Template = Get-Content -Raw -Path $TemplateFile
$FallbackDate = (Get-Item $ProductsJson).LastWriteTimeUtc.ToString("yyyy-MM-dd")

New-Item -ItemType Directory -Force -Path $ProductIndexDir | Out-Null
Set-Content -Path (Join-Path $ProductIndexDir "index.html") -Value (Render-Template $Template $null) -Encoding UTF8

$SitemapParts = @()
$GeneratedCount = 0
foreach ($Product in $Products) {
  if (!(Should-Generate-ProductPage $Product)) { continue }
  $RoutePath = $Product._generated_route.Trim("/")
  $OutDir = Join-Path $FrontendPath (Join-Path $RoutePath $Product._generated_slug)
  $IndexFile = Join-Path $OutDir "index.html"
  if (!(Test-Path $IndexFile)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    Set-Content -Path $IndexFile -Value (Render-Template $Template $Product) -Encoding UTF8
  }
  $SitemapParts += Sitemap-Url "$SiteOrigin$($Product._generated_route)$($Product._generated_slug)/" (Product-Date $Product $FallbackDate)
  $GeneratedCount++
}

$CopiedTemplateFile = Join-Path $FrontendPath "products/product/template.html"
if ($FrontendPath -ne [System.IO.Path]::GetFullPath((Join-Path $Root "frontend")) -and (Test-Path $CopiedTemplateFile)) {
  Remove-Item -LiteralPath $CopiedTemplateFile -Force
}

$Sitemap = Get-Content -Raw -Path $SitemapFile
$Append = ($SitemapParts -join "`n")
if ($Sitemap -notmatch "</urlset>\s*$") {
  throw "sitemap.xml does not end with </urlset>"
}

$Sitemap = $Sitemap -replace "</urlset>\s*$", "$Append`n</urlset>`n"
Set-Content -Path $SitemapFile -Value $Sitemap -Encoding UTF8
Write-Output "Generated $GeneratedCount product pages in $FrontendDir and appended them to sitemap.xml"
