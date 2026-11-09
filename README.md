# Sharp Subject Cutout PSD

ComfyUI nodes for a sharp subject cutout on very large photographs (about 10000×10000), saved as an editable Photoshop file.

The cut follows the **outline of the subject**. It does not draw a geometric circle. A separate mask node, such as RMBG, still has to say where the person is. This pack takes that soft mask, locks the contour to the full-resolution photo, and writes a PSD you can keep editing.

## What the PSD contains

One pixel layer and one layer mask:

- The layer is the **original photograph**. Pixels outside the subject are not deleted and are not painted over.
- The layer mask follows the outline. White shows the subject, black hides the background.
- There is no Background layer. In Photoshop, painting on the mask reveals the original pixels underneath.

The file is written **next to the source file**, with the same name and a `_(ComfyUI)` suffix:

`Hazetomika.jpg` → `Hazetomika_(ComfyUI).psd`

ComfyUI only knows the file it loaded. An image uploaded in the UI is stored in `ComfyUI/input`, so the PSD is created beside that copy.

## Install

These steps are for the Windows portable build. Close ComfyUI first. Run the commands from the portable folder, the one that contains `python_embeded` and `ComfyUI`.

Example root: `C:\ComfyUI_windows_portable`

### 1. Install this node

```bat
git clone https://github.com/PiRanha78/sharp_subject_cutout_PSD.git ComfyUI\custom_nodes\sharp_subject_cutout_PSD
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\sharp_subject_cutout_PSD\requirements.txt
```

That installs `psd-tools` (>= 1.9.0) into the Python that actually starts ComfyUI. A system `pip install` does not reach the portable runtime.

On a non-portable install, use that environment’s Python instead, for example `ComfyUI\venv\Scripts\python.exe -m pip install -r requirements.txt`, after cloning into `ComfyUI\custom_nodes`.

### 2. Install RMBG

The example workflow needs the separate [ComfyUI-RMBG](https://github.com/1038lab/ComfyUI-RMBG) node. This repository does not contain the segmentation model. Skip this step only if that node is already installed and the **RMBG** node appears in the menu.

```bat
git clone https://github.com/1038lab/ComfyUI-RMBG.git ComfyUI\custom_nodes\ComfyUI-RMBG
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-RMBG\requirements.txt
```

The first run of RMBG-2.0 downloads its weights. That needs a network connection and several GB of free disk space.

### 3. Restart ComfyUI

Start it only after both installs finish. A running session does not pick up a new custom node.

In the node search box, confirm that these three names exist:

- **Load Image (Source Path)**
- **Sharp Subject Cutout**
- **Save Cutout as PSD**

If they are missing, the clone is not inside `ComfyUI\custom_nodes`, or ComfyUI was not restarted.

### 4. Load the workflow

Download [Sharp_Subject_Cutout_PSD.json](Sharp_Subject_Cutout_PSD.json) (**Download raw file** on GitHub). Drag that file onto the ComfyUI canvas, or use **Workflow → Open**.

On **Load Image (Source Path)**, choose the photograph, then queue the prompt. The PSD is written next to that file:

`photo.jpg` → `photo_(ComfyUI).psd`

An image uploaded in the UI is stored in `ComfyUI\input`, so the PSD appears beside that copy, not beside a file that lives somewhere else on the disk.

## Workflow

```text
Load Image (Source Path)
        │  image ──────────────► Save Cutout as PSD   (original pixels)
        │  source_path ────────► Save Cutout as PSD
        └─ image ──► RMBG ── mask ──► Sharp Subject Cutout ── mask ──► Save Cutout as PSD
```

RMBG is not part of this pack. Any mask of the same width and height works. For RMBG, set **Mask Blur** to 0. **Processing Resolution** tops out at 2048 in that node, so a 10000 px photo gets an upscaled, soft mask. That upscale is what this pack cleans up.

Wire the **original image** from the loader into **Save Cutout as PSD**, not the preview image from the cutout. The preview may be cropped. The mask from **Sharp Subject Cutout** is always full frame and matches the original.

One image per PSD. A batch larger than 1 is rejected.

## Sharp Subject Cutout

Menu: **Sharp Subject Cutout**, category `image/crop`.

| Input | Default | What it does |
| --- | --- | --- |
| `image` | | Full-resolution photo. |
| `mask` | | Soft subject mask, ideally from RMBG. |
| `threshold` | 0.5 | Where the outline is cut after the edge is fitted. 0.5 is the middle of the silhouette. |
| `snap_radius` | 16 | How many pixels the soft mask may move to sit on a real edge in the photo. 0 keeps the threshold only. |
| `padding` | 8 | Extra pixels around the subject on the **preview** image only. |
| `background_color` | `#000000` | Unused. It is not written into the PSD. |
| `crop_to_subject` | true | Crops only the preview image around the subject. The mask output stays full size. |
| `edge_aa_pixels` | 1.5 | Smooths the blocky, upscaled contour. 0 is a hard, pixelated edge. 1.5 is a sharp edge about one pixel wide. 2–2.5 if hair still looks stepped when you zoom in. Above that the edge gets soft. |

Outputs:

- `image` — preview. RGBA, alpha is the cutout. Cropped only when `crop_to_subject` is on.
- `mask` — the outline at the **original** width and height. This is the mask to save.
- `crop_box` — preview rectangle as `x0, y0, x1, y1`. The full frame when the preview is not cropped.

The edge is built in three steps. A guided filter pulls the soft mask onto contrast in the full-resolution photo. A short blur rounds the staircase left by the low-resolution mask. That curve is turned into a coverage ramp only `edge_aa_pixels` wide, so the cut stays sharp instead of growing a wide gray halo.

## Save Cutout as PSD

Menu: **Save Cutout as PSD**, category `image/crop`.

| Input | Default | What it does |
| --- | --- | --- |
| `image` | | Original photo. The first three channels are stored. |
| `mask` | | Full-size outline. Must be the same width and height as `image`. |
| `source_path` | | Absolute path from **Load Image (Source Path)**. |
| `layer_name` | `Original` | Name of the pixel layer in Photoshop. |

Output: `saved_path`, the full path of the written `.psd`.

If the source name already ends with `_(ComfyUI)`, the suffix is not added twice.

## Load Image (Source Path)

Menu: **Load Image (Source Path)**, category `image`.

Same file list as ComfyUI **Load Image**, plus `source_path`: the absolute path of the loaded file. Connect that string to **Save Cutout as PSD**.

## Other nodes

These draw a geometric circle. They are not part of the subject-cutout workflow.

- **Precise Circle Mask (HQ)** — full-frame circular mask from center, radius, and an optional one-pixel edge.
- **Precise Circle Crop (HQ)** — square crop around that circle. Optional `fit_mask` fits the circle to an existing mask.
- **Precise Circle From Mask** — center and radius of a mask, from its centroid and area.

---

# Éles figura-kivágás PSD-be

ComfyUI node-ok nagyon nagy, körülbelül 10000×10000 pixeles fotók éles körbevágásához, szerkeszthető Photoshop-fájlba mentve.

A vágás a **figura saját körvonalát** követi. Nem rajzol mértani kört. Azt, hogy hol a személy, továbbra is egy külön maszk node adja meg, például az RMBG. Ez a csomag azt a lágy maszkot a teljes felbontású fotó élére húzza, és olyan PSD-t ír, amit utána még lehet módosítani.

## Mi van a PSD-ben

Egy pixelréteg és egy rétegmaszk:

- A réteg az **eredeti fotó**. A figura mögötti pixelek nincsenek letörölve, és nincsenek átszínezve.
- A rétegmaszk a körvonalat követi. A fehér mutatja a figurát, a fekete takarja a hátteret.
- Nincs háttérréteg. Photoshopban a maszk festésével az alatta lévő eredeti pixelek jönnek elő.

A fájl a **forrás mellé** kerül, ugyanazzal a névvel, `_(ComfyUI)` végződéssel:

`Hazetomika.jpg` → `Hazetomika_(ComfyUI).psd`

A ComfyUI csak azt a fájlt ismeri, amit betöltött. A felületen feltöltött kép a `ComfyUI/input` mappába kerül, ezért a PSD ennek a másolatnak a mellé íródik.

## Telepítés

A lépések a Windows portable változatra vannak írva. Először zárd be a ComfyUI-t. A parancsokat a portable mappából futtasd, abból, amelyben a `python_embeded` és a `ComfyUI` van.

Példa gyökér: `C:\ComfyUI_windows_portable`

### 1. Ennek a node-nak a telepítése

```bat
git clone https://github.com/PiRanha78/sharp_subject_cutout_PSD.git ComfyUI\custom_nodes\sharp_subject_cutout_PSD
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\sharp_subject_cutout_PSD\requirements.txt
```

Ez a `psd-tools` csomagot (>= 1.9.0) abba a Pythonba teszi, amelyik a ComfyUI-t indítja. A rendszer `pip install` parancsa a portable környezetet nem éri el.

Ha a ComfyUI nem portable, a saját környezet Pythonját használd, például `ComfyUI\venv\Scripts\python.exe -m pip install -r requirements.txt`, miután a repót a `ComfyUI\custom_nodes` mappába klónoztad.

### 2. Az RMBG telepítése

A mintaworkflow a külön [ComfyUI-RMBG](https://github.com/1038lab/ComfyUI-RMBG) node-ot használja. Ebben a repóban nincs szegmentáló modell. Ezt a lépést csak akkor hagyd ki, ha az a node már telepítve van, és az **RMBG** megjelenik a menüben.

```bat
git clone https://github.com/1038lab/ComfyUI-RMBG.git ComfyUI\custom_nodes\ComfyUI-RMBG
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-RMBG\requirements.txt
```

Az RMBG-2.0 első futtatása letölti a súlyokat. Ehhez hálózat kell, és több GB szabad lemez.

### 3. A ComfyUI újraindítása

Csak akkor indítsd el, ha mindkét telepítés lefutott. A már futó program az új custom node-ot nem veszi észre.

A node-keresőben ennek a három névnek kell megjelennie:

- **Load Image (Source Path)**
- **Sharp Subject Cutout**
- **Save Cutout as PSD**

Ha hiányoznak, a klón nem a `ComfyUI\custom_nodes` mappában van, vagy a ComfyUI nem indult újra.

### 4. A workflow betöltése

Töltsd le a [Sharp_Subject_Cutout_PSD.json](Sharp_Subject_Cutout_PSD.json) fájlt (GitHubon: **Download raw file**). Húzd a ComfyUI vásznára, vagy nyisd meg a **Workflow → Open** menüvel.

A **Load Image (Source Path)** node-on válaszd ki a fotót, majd indítsd a futtatást. A PSD a kép mellé kerül:

`foto.jpg` → `foto_(ComfyUI).psd`

A felületen feltöltött kép a `ComfyUI\input` mappába kerül, ezért a PSD ennek a másolatnak a mellé íródik, nem egy máshol lévő eredeti fájl mellé.

## Workflow

```text
Load Image (Source Path)
        │  image ──────────────► Save Cutout as PSD   (eredeti pixelek)
        │  source_path ────────► Save Cutout as PSD
        └─ image ──► RMBG ── mask ──► Sharp Subject Cutout ── mask ──► Save Cutout as PSD
```

Az RMBG nem része ennek a csomagnak. Bármilyen, a képpel azonos méretű maszk használható. RMBG-nél a **Mask Blur** legyen 0. A **Processing Resolution** abban a node-ban legfeljebb 2048, ezért egy 10000 px-es fotón a maszk felnagyított és lágy. Ezt a felnagyítást takarítja ki ez a csomag.

A **Save Cutout as PSD** `image` bemenetére a betöltő **eredeti képét** kösd, ne a kivágó előnézetét. Az előnézet lehet körbevágott. A **Sharp Subject Cutout** maszkja mindig teljes képkocka, és egyezik az eredetivel.

Egy PSD-be egy kép kerül. Egynél nagyobb batch esetén a mentés hibát ad.

## Sharp Subject Cutout

Menü: **Sharp Subject Cutout**, kategória: `image/crop`.

| Bemenet | Alapérték | Mit csinál |
| --- | --- | --- |
| `image` | | Teljes felbontású fotó. |
| `mask` | | Lágy figura-maszk, tipikusan az RMBG-ből. |
| `threshold` | 0,5 | Hol vágja a körvonalat, miután az él a helyére került. A 0,5 a sziluett közepe. |
| `snap_radius` | 16 | Hány pixelen belül húzhatja a lágy maszkot a fotó valódi élére. 0 = csak a küszöb. |
| `padding` | 8 | Ennyi plusz pixel a figura körül, **csak az előnézeti** képen. |
| `background_color` | `#000000` | Nincs használva. Nem kerül bele a PSD-be. |
| `crop_to_subject` | true | Csak az előnézeti képet vágja a figura köré. A kimenő maszk teljes méretű marad. |
| `edge_aa_pixels` | 1,5 | A felnagyított, kockás kontúr simítása. 0 = kemény, pixeles él. 1,5 = éles él, körülbelül egy pixel szélesen. 2–2,5, ha közelítve a haj széle még törik. Efölött az él lágyul. |

Kimenetek:

- `image` — előnézet. RGBA, az alpha a kivágás. Csak akkor van a figura köré vágva, ha a `crop_to_subject` be van kapcsolva.
- `mask` — a körvonal az **eredeti** szélességen és magasságon. Ezt kell menteni.
- `crop_box` — az előnézet téglalapja: `x0, y0, x1, y1`. Teljes kép, ha az előnézet nincs vágva.

Az él három lépésben készül. Egy guided filter a lágy maszkot a teljes felbontású fotó kontrasztjára húzza. Egy rövid elmosás lekerekíti a kis felbontású maszk lépcsőit. Ebből a görbéből csak `edge_aa_pixels` széles átmenet lesz, ezért a vágás éles marad, és nem nő köré széles szürke szegély.

## Save Cutout as PSD

Menü: **Save Cutout as PSD**, kategória: `image/crop`.

| Bemenet | Alapérték | Mit csinál |
| --- | --- | --- |
| `image` | | Az eredeti fotó. Az első három csatorna kerül a fájlba. |
| `mask` | | Teljes méretű körvonal. A szélessége és a magassága egyezzen az `image` méretével. |
| `source_path` | | A **Load Image (Source Path)** abszolút útvonala. |
| `layer_name` | `Original` | A pixelréteg neve Photoshopban. |

Kimenet: `saved_path`, a megírt `.psd` teljes útvonala.

Ha a forrás neve már `_(ComfyUI)`-ra végződik, a toldalék nem kerül fel még egyszer.

## Load Image (Source Path)

Menü: **Load Image (Source Path)**, kategória: `image`.

Ugyanaz a fájllista, mint a ComfyUI **Load Image** node-ján, plusz a `source_path`: a betöltött fájl abszolút útvonala. Ezt a szöveget kösd a **Save Cutout as PSD** node-ra.

## További node-ok

Ezek mértani kört rajzolnak. A figura-kivágás workflow-jához nem kellenek.

- **Precise Circle Mask (HQ)** — teljes képkockás kör-maszk középpontból és sugárból, opcionális egy pixeles éllel.
- **Precise Circle Crop (HQ)** — négyzetes kivágás a kör körül. A `fit_mask` egy meglévő maszkra illeszti a kört.
- **Precise Circle From Mask** — egy maszk középpontja és sugara, a súlypontjából és a területéből.
