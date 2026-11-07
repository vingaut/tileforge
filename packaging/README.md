# Compiler TileForge

Trois cibles sont préparées : **Linux**, **Windows** et **Android**.

| Cible | Outil | Sortie | Script |
|---|---|---|---|
| Linux | PyInstaller | `dist/TileForge/TileForge` | `packaging/build_linux.sh` |
| Windows | PyInstaller | `dist\TileForge\TileForge.exe` | `packaging\build_windows.bat` |
| Android | pyside6-android-deploy | `.apk` | `packaging/android/build_android.sh` |

---

## 1. Linux

```bash
./packaging/build_linux.sh
./dist/TileForge/TileForge
```

Le script crée un environnement de compilation séparé (`.venv-build`), y
installe PyInstaller, puis produit un dossier autonome de ~240 Mo (PySide6 en
représente la moitié).

Options :

```bash
TILEFORGE_ONEFILE=1 ./packaging/build_linux.sh   # exécutable unique
TILEFORGE_CONSOLE=1 ./packaging/build_linux.sh   # garde une console (débogage)
```

Installation « système » :

```bash
sudo mkdir -p /opt/tileforge
sudo cp -r dist/TileForge/* /opt/tileforge/
sudo cp packaging/icon.png /opt/tileforge/packaging/
sudo cp packaging/tileforge.desktop /usr/share/applications/
```

Vérification rapide après compilation :

```bash
./dist/TileForge/TileForge --selftest
```

## 2. Windows

Dans un terminal Windows, depuis la racine du projet :

```bat
packaging\build_windows.bat
dist\TileForge\TileForge.exe
```

Le script utilise `py -3` (Python 3.10+ requis). Le résultat est un dossier :
compressez-le pour le distribuer, ou créez un installeur avec
[Inno Setup](https://jrsoftware.org/isinfo.php) en pointant sur
`TileForge.exe`.

L'icône `packaging/icon.ico` est intégrée à l'exécutable.

## 3. Android

La voie officielle est **`pyside6-android-deploy`**, livré avec PySide6.

### Prérequis

1. **JDK 17** (`java -version` doit l'indiquer).
2. **Android SDK** — par exemple via Android Studio, puis
   `export ANDROID_SDK_ROOT=$HOME/Android/Sdk`.
3. **Android NDK r28c** — `export ANDROID_NDK_ROOT=$HOME/Android/Sdk/ndk/28.0.…`.
4. **Roues PySide6 et shiboken6 pour Android**, téléchargées depuis la page
   « Qt for Python » (paquets `…-android_aarch64.whl`). Placez-les dans
   `packaging/android/wheels/` ou passez-les en argument.
5. Un appareil en mode développeur, ou un émulateur, pour `adb install`.

### Compilation

```bash
./packaging/android/build_android.sh \
    --pyside-wheel   packaging/android/wheels/PySide6-6.12.0-…-android_aarch64.whl \
    --shiboken-wheel packaging/android/wheels/shiboken6-6.12.0-…-android_aarch64.whl
```

Le script :

* vérifie Java, le SDK, le NDK et les roues ;
* prépare un dossier `.stage/` contenant `main.py` et le paquet `tileforge/` ;
* lance `pyside6-android-deploy`.

L'APK apparaît dans `packaging/android/.stage/dist/`. Installation :

```bash
adb install -r packaging/android/.stage/dist/*.apk
```

### Ce qui a été adapté pour Android

* **Mode tactile** automatique (`is_android()`) : grandes cibles, panneaux
  latéraux repliables, pose des tuiles en deux temps (tuile puis case).
* **Pincement pour zoomer** sur les deux canevas, outil « Déplacer la vue »
  pour le glissement à un doigt.
* **Chemins** : les dialogues d'ouverture et d'enregistrement utilisent le
  dossier de données de l'application au lieu des chemins du poste de travail.
* **Réglages** stockés dans le dossier privé de l'application.

### Limites connues

* L'écran est petit : l'atelier reste utilisable mais le confort d'un écran
  d'ordinateur n'est pas atteint.
* Le glisser-déposer souris n'existe pas au doigt : utilisez la pose en deux
  temps.
* Les très grosses banques (plusieurs milliers de tuiles) demandent de la
  mémoire : sur un appareil modeste, découpez la banque en plusieurs projets.

---

## 4. Publier une mise à jour

TileForge sait se mettre à jour depuis un manifeste JSON (voir
`tileforge/core/updates.py`).

```bash
python tools/make_update.py --version 1.2.0 \
    --notes "Nouvelles machines, corrections" \
    --url-base https://exemple.org/tileforge
```

Produit `dist/updates/tileforge-1.2.0.zip` et `dist/updates/manifest.json`.
Déposez les deux fichiers sur le serveur (ou une clé USB), puis dans
l'application : **Aide ▸ Mises à jour ▸ Manifeste**.

Seul le paquet `tileforge/` est remplacé ; une sauvegarde de la version
précédente permet un retour arrière immédiat.

> Pour une application **compilée** (PyInstaller), l'installation automatique
> est désactivée : l'archive est téléchargée et il faut remplacer le dossier de
> l'application. C'est volontaire — remplacer des binaires en cours d'exécution
> n'est pas fiable selon les systèmes.

---

## 5. Vérifications après compilation

```bash
# Linux / Windows
./dist/TileForge/TileForge --selftest

# interface
./dist/TileForge/TileForge
```

`--selftest` vérifie les dépendances, charge le cœur (76 machines, 6 détecteurs,
22 formats) et construit la fenêtre principale hors écran. C'est le test le plus
rapide pour valider un paquet.
