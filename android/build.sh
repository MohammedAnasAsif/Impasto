#!/usr/bin/env bash
# Builds a signed APK with no Gradle and no Android Studio: aapt + javac + dx + zipalign + apksigner.
# On Ubuntu/Debian: sudo apt-get install aapt zipalign apksigner dalvik-exchange android-sdk-platform-23 openjdk-17-jdk nodejs
#
# Signing: set KEYSTORE, KEYSTORE_PASS, KEY_ALIAS to use your release key.
# Without them a local key is created in android/keystore/ (keep it: updates must be signed with the same key).
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(cd .. && pwd)
SDK=${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}
VERSION=$(grep -o 'versionName="[^"]*"' AndroidManifest.xml | cut -d'"' -f2)
OUT=$ROOT/dist
B=$ROOT/build/android
rm -rf "$B" && mkdir -p "$B/classes" "$B/assets" "$OUT"

echo "› staging the store UI and phone wallpapers"
node "$ROOT/tools/stage.mjs" "$B/assets/www" phone
cp -r www/. "$B/assets/www/"   # Android keeps its own layout: styles.css and its fonts

echo "› compiling Java"
javac -nowarn -source 8 -target 8 -bootclasspath "$SDK" -classpath "$SDK" -d "$B/classes" $(find src -name '*.java') 2>&1 | grep -v "bootstrap class path\|^warning\|^1 warning\|source value 8\|target value 8\|To suppress" || true
test -f "$B/classes/app/impasto/wallpapers/MainActivity.class"

echo "› dexing"
"${DX:-$(command -v dx || command -v dalvik-exchange)}" --dex --min-sdk-version=26 --output="$B/classes.dex" "$B/classes"

echo "› packaging"
# -0 png/webp: already compressed, store as-is so the PNGs stay byte-identical and fast to read
aapt package -f -M AndroidManifest.xml -S res -A "$B/assets" -I "$SDK" -0 png -0 webp -0 woff2 -F "$B/unsigned.apk"
(cd "$B" && aapt add -f unsigned.apk classes.dex >/dev/null)
zipalign -f -p 4 "$B/unsigned.apk" "$B/aligned.apk"

echo "› signing"
if [ -z "${KEYSTORE:-}" ]; then
  KEYSTORE=keystore/impasto-local.jks KEYSTORE_PASS=${KEYSTORE_PASS:-impasto-local} KEY_ALIAS=impasto
  if [ ! -f "$KEYSTORE" ]; then
    mkdir -p keystore
    keytool -genkeypair -keystore "$KEYSTORE" -storepass "$KEYSTORE_PASS" -keypass "$KEYSTORE_PASS" -alias "$KEY_ALIAS" \
      -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Impasto, O=Impasto open source" >/dev/null 2>&1
  fi
fi
APK=$OUT/Impasto-$VERSION.apk
apksigner sign --ks "$KEYSTORE" --ks-pass "pass:$KEYSTORE_PASS" --ks-key-alias "$KEY_ALIAS" --key-pass "pass:$KEYSTORE_PASS" \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --out "$APK" "$B/aligned.apk"
apksigner verify "$APK"
echo "✓ $APK ($(du -h "$APK" | cut -f1))"
