package app.impasto.wallpapers;

import android.app.Activity;
import android.app.WallpaperManager;
import android.content.ClipData;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.view.View;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** A WebView shell around the shared store UI, plus the few things only the OS can do. */
public class MainActivity extends Activity {
    static final String HOST = "app.impasto.local";
    static final String HOME = "https://" + HOST + "/index.html";
    static final long MAX_BYTES = 120L * 1024 * 1024;
    static final byte[] PNG = {(byte) 0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a};

    private WebView web;
    private final ExecutorService io = Executors.newSingleThreadExecutor();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setSupportZoom(false);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (!HOST.equals(u.getHost())) return null;
                return asset(u.getPath());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Uri u = Uri.parse(url);
                if (HOST.equals(u.getHost())) return false;
                openExternalUri(u);
                return true;
            }
        });
        web.addJavascriptInterface(new Bridge(), "ImpastoAndroid");
        if (state != null) web.restoreState(state);
        if (web.getUrl() == null) web.loadUrl(HOME);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    // ---------- local files: https://app.impasto.local/<path> -> assets/www/<path> ----------
    private WebResourceResponse asset(String path) {
        if (path == null || path.equals("/")) path = "/index.html";
        if (path.contains("..")) return notFound();
        try {
            InputStream in = getAssets().open("www" + path);
            Map<String, String> h = new HashMap<>();
            h.put("Cache-Control", "no-cache");
            return new WebResourceResponse(mime(path), null, 200, "OK", h, in);
        } catch (IOException e) {
            return notFound();
        }
    }

    private static WebResourceResponse notFound() {
        return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", new HashMap<String, String>(), null);
    }

    private static String mime(String p) {
        if (p.endsWith(".html")) return "text/html";
        if (p.endsWith(".js")) return "text/javascript";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".json")) return "application/json";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".webp")) return "image/webp";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".woff2")) return "font/woff2";
        return "application/octet-stream";
    }

    /** Opens a wallpaper file: bundled asset or remote https PNG, validated before use. */
    private InputStream open(String url) throws IOException {
        Uri u = Uri.parse(url);
        if (!"https".equals(u.getScheme())) throw new IOException("Only https sources are allowed");
        InputStream in;
        if (HOST.equals(u.getHost())) {
            String p = u.getPath();
            if (p == null || p.contains("..")) throw new IOException("Bad path");
            in = getAssets().open("www" + p);
        } else {
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(15000);
            c.setReadTimeout(30000);
            c.setInstanceFollowRedirects(true);
            if (c.getResponseCode() != 200) throw new IOException("Download failed (" + c.getResponseCode() + ")");
            long len = c.getContentLength();
            if (len > MAX_BYTES) throw new IOException("File is too large");
            in = c.getInputStream();
        }
        in = new BufferedInputStream(in, 1 << 16);
        in.mark(16);
        byte[] head = new byte[8];
        int n = 0;
        while (n < 8) { int r = in.read(head, n, 8 - n); if (r < 0) break; n += r; }
        in.reset();
        for (int i = 0; i < 8; i++) if (n < 8 || head[i] != PNG[i]) { in.close(); throw new IOException("That file isn't a PNG"); }
        return in;
    }

    private static long copy(InputStream in, OutputStream out) throws IOException {
        byte[] buf = new byte[1 << 16];
        long total = 0;
        int r;
        try {
            while ((r = in.read(buf)) > 0) {
                total += r;
                if (total > MAX_BYTES) throw new IOException("File is too large");
                out.write(buf, 0, r);
            }
        } finally {
            in.close();
            out.close();
        }
        return total;
    }

    private static String safeName(String name) {
        String n = name == null ? "" : name.replaceAll("[^A-Za-z0-9._-]", "_");
        if (!n.endsWith(".png")) n += ".png";
        return n.length() > 120 ? n.substring(n.length() - 120) : n;
    }

    private void openExternalUri(Uri u) {
        if (!"https".equals(u.getScheme())) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
    }

    private void reply(final String id, final boolean ok, final String json) {
        final String js = "window.__impastoNative&&window.__impastoNative.done(" + JSONObject.quote(id) + "," + ok + "," + JSONObject.quote(json) + ")";
        web.post(new Runnable() { public void run() { web.evaluateJavascript(js, null); } });
    }

    private void fail(String id, Exception e) {
        try { reply(id, false, new JSONObject().put("error", e.getMessage() == null ? "Something went wrong" : e.getMessage()).toString()); }
        catch (Exception ignored) { reply(id, false, "{}"); }
    }

    private abstract class Job implements Runnable {
        final String id;
        Job(String id) { this.id = id; }
        abstract String work() throws Exception;
        public void run() {
            try { reply(id, true, work()); } catch (Exception e) { fail(id, e); }
        }
    }

    // ---------- the JS bridge ----------
    class Bridge {
        @JavascriptInterface
        public void save(String id, final String url, final String filename) {
            io.execute(new Job(id) {
                String work() throws Exception {
                    ContentResolver cr = getContentResolver();
                    ContentValues v = new ContentValues();
                    v.put(MediaStore.MediaColumns.DISPLAY_NAME, safeName(filename));
                    v.put(MediaStore.MediaColumns.MIME_TYPE, "image/png");
                    v.put("relative_path", "Pictures/Impasto");
                    v.put("is_pending", 1);
                    Uri dest = cr.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v);
                    if (dest == null) throw new IOException("Couldn't create the file in Pictures");
                    try {
                        OutputStream out = cr.openOutputStream(dest);
                        if (out == null) throw new IOException("Couldn't write to Pictures");
                        copy(open(url), out);
                    } catch (Exception e) {
                        cr.delete(dest, null, null); // no half-written files left in the gallery
                        throw e;
                    }
                    ContentValues done = new ContentValues();
                    done.put("is_pending", 0);
                    cr.update(dest, done, null, null);
                    return new JSONObject().put("location", "Pictures/Impasto").put("uri", dest.toString()).toString();
                }
            });
        }

        @JavascriptInterface
        public void setWallpaper(String id, final String url, String filename, final String which) {
            io.execute(new Job(id) {
                String work() throws Exception {
                    int flags = "home".equals(which) ? 1 : "lock".equals(which) ? 2 : 3; // FLAG_SYSTEM, FLAG_LOCK
                    WallpaperManager wm = WallpaperManager.getInstance(MainActivity.this);
                    // setStream(InputStream, Rect, boolean, int) is API 24; we compile against API 23.
                    Method m = WallpaperManager.class.getMethod("setStream", InputStream.class, Rect.class, boolean.class, int.class);
                    InputStream in = open(url);
                    try { m.invoke(wm, in, null, true, flags); } finally { in.close(); }
                    return "{}";
                }
            });
        }

        @JavascriptInterface
        public void share(String id, final String url, final String filename, final String title) {
            io.execute(new Job(id) {
                String work() throws Exception {
                    File dir = new File(getCacheDir(), "share");
                    if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("No space to prepare the file");
                    File[] old = dir.listFiles();
                    if (old != null) for (File f : old) f.delete();
                    String name = safeName(filename);
                    copy(open(url), new FileOutputStream(new File(dir, name)));
                    final Uri uri = Uri.parse("content://" + ShareProvider.AUTHORITY + "/" + Uri.encode(name));
                    final Intent send = new Intent(Intent.ACTION_SEND);
                    send.setType("image/png");
                    send.putExtra(Intent.EXTRA_STREAM, uri);
                    send.putExtra(Intent.EXTRA_TITLE, title);
                    send.setClipData(ClipData.newRawUri(title, uri));
                    send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    runOnUiThread(new Runnable() { public void run() { startActivity(Intent.createChooser(send, "Share " + title)); } });
                    return "{}";
                }
            });
        }

        @JavascriptInterface
        public void openExternal(String url) {
            final Uri u = Uri.parse(url);
            runOnUiThread(new Runnable() { public void run() { openExternalUri(u); } });
        }

        @JavascriptInterface
        public void setChrome(final String css, final boolean light) {
            Matcher m = Pattern.compile("(\\d+)\\D+(\\d+)\\D+(\\d+)").matcher(css == null ? "" : css);
            if (!m.find()) return;
            final int color = Color.rgb(Integer.parseInt(m.group(1)), Integer.parseInt(m.group(2)), Integer.parseInt(m.group(3)));
            runOnUiThread(new Runnable() {
                public void run() {
                    Window w = getWindow();
                    w.setStatusBarColor(color);
                    w.setNavigationBarColor(color);
                    int f = w.getDecorView().getSystemUiVisibility();
                    int bits = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | 0x10; // 0x10 = LIGHT_NAVIGATION_BAR (API 26)
                    w.getDecorView().setSystemUiVisibility(light ? (f | bits) : (f & ~bits));
                }
            });
        }
    }
}
