param(
  [string]$FrontendDir = "frontend"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$SiteOrigin = "https://unlim8ted.com"
$ProductsJson = Join-Path $Root "assets/data/products.json"
$TemplateFile = Join-Path $Root "product-templates/default.html"
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

function Render-Template($Template, $Product) {
  if ($null -eq $Product) {
    $Title = "Unlim8ted - Product"
    $Description = "Unlim8ted Product page. Powered by Unlim8ted Studio Productions"
    $Canonical = "$SiteOrigin/products/product/"
    $Bootstrap = ""
  } else {
    $ProductId = [string]$Product.id
    $TitleName = First-Text $Product.name $Product.title $ProductId
    $Title = "$TitleName - Unlim8ted"
    $Description = First-Text $Product.description $Product.desc "$TitleName by Unlim8ted Studio Productions"
    if ($Description.Length -gt 300) { $Description = $Description.Substring(0, 300) }
    $Canonical = "$SiteOrigin$($Product._generated_route)$($Product._generated_slug)/"
    $Bootstrap = "<script>window.UNLIM8TED_PRODUCT_ID = $(Json-String $ProductId);</script>"
  }

  return $Template.
    Replace("{{TITLE}}", (Html-Escape $Title)).
    Replace("{{DESCRIPTION}}", (Html-Escape $Description)).
    Replace("{{CANONICAL_URL}}", (Html-Escape $Canonical)).
    Replace("{{PRODUCT_BOOTSTRAP}}", $Bootstrap)
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
foreach ($Product in $Products) {
  $RoutePath = $Product._generated_route.Trim("/")
  $OutDir = Join-Path $FrontendPath (Join-Path $RoutePath $Product._generated_slug)
  $IndexFile = Join-Path $OutDir "index.html"
  if (!(Test-Path $IndexFile)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    Set-Content -Path $IndexFile -Value (Render-Template $Template $Product) -Encoding UTF8
  }
  $SitemapParts += Sitemap-Url "$SiteOrigin$($Product._generated_route)$($Product._generated_slug)/" (Product-Date $Product $FallbackDate)
}

$Sitemap = Get-Content -Raw -Path $SitemapFile
$Append = ($SitemapParts -join "`n")
if ($Sitemap -notmatch "</urlset>\s*$") {
  throw "sitemap.xml does not end with </urlset>"
}

$Sitemap = $Sitemap -replace "</urlset>\s*$", "$Append`n</urlset>`n"
Set-Content -Path $SitemapFile -Value $Sitemap -Encoding UTF8
Write-Output "Generated $($Products.Count) product pages in $FrontendDir and appended them to sitemap.xml"
