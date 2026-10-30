package app.impasto.wallpapers;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.app.WallpaperManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Optional auto-change: every minute the next wallpaper in the list is set, starting over after the last.
 * An alarm drives it, so it keeps going with the app closed. While the screen is off it skips the change.
 */
public class Rotation extends BroadcastReceiver {
    static final String ACTION = "app.impasto.wallpapers.ROTATE";
    static final long EVERY = 60_000L;
    static final long MAX_BYTES = 120L * 1024 * 1024;
    static final byte[] PNG = {(byte) 0x89, 'P', 'N', 'G', 0x0d, 0x0a, 0x1a, 0x0a};

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("rotation", Context.MODE_PRIVATE); }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!ACTION.equals(intent.getAction())) return;
        final Context app = context.getApplicationContext();
        final PendingResult done = goAsync();
        new Thread(new Runnable() { public void run() { try { tick(app, false); } finally { done.finish(); } } }).start();
    }

    /** Re-arms the alarm after a restart or an app update, which both clear it. */
    public static class Boot extends BroadcastReceiver {
        @Override
        public void onReceive(Context c, Intent i) {
            String a = i.getAction();
            if ((Intent.ACTION_BOOT_COMPLETED.equals(a) || "android.intent.action.MY_PACKAGE_REPLACED".equals(a))
                    && prefs(c).getBoolean("enabled", false)) schedule(c.getApplicationContext());
        }
    }

    /** Sets the next wallpaper (unless the screen is off), then books the next minute. */
    static void tick(Context c, boolean force) {
        SharedPreferences p = prefs(c);
        if (!p.getBoolean("enabled", false)) return;
        try {
            PowerManager pm = (PowerManager) c.getSystemService(Context.POWER_SERVICE);
            JSONArray list = new JSONArray(p.getString("list", "[]"));
            int n = list.length();
            if (n > 0 && (force || pm.isInteractive())) {
                int i = p.getInt("index", -1);
                for (int tries = 0; tries < Math.min(n, 3); tries++) {
                    i = (i + 1) % n; // round robin: after the last one, back to the first
                    try {
                        apply(c, list.getJSONObject(i).getString("url"), p.getString("which", "home"));
                        p.edit().putInt("index", i).apply();
                        break;
                    } catch (Exception e) { /* offline or missing: try the next one */ }
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (p.getBoolean("enabled", false)) schedule(c);
        }
    }

    static void schedule(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        long at = System.currentTimeMillis() + EVERY;
        PendingIntent pi = pending(c);
        // RTC, not RTC_WAKEUP: a sleeping phone isn't woken just to change a wallpaper nobody can see
        try {
            if (exactAllowed(c)) am.setExact(AlarmManager.RTC, at, pi); else am.set(AlarmManager.RTC, at, pi);
        } catch (SecurityException e) {
            am.set(AlarmManager.RTC, at, pi);
        }
        prefs(c).edit().putLong("next", at).apply();
    }

    static void set(final Context c, boolean on, String which) {
        prefs(c).edit().putBoolean("enabled", on).putString("which", which).apply();
        if (on) {
            new Thread(new Runnable() { public void run() { tick(c, true); } }).start(); // first change right away
        } else {
            ((AlarmManager) c.getSystemService(Context.ALARM_SERVICE)).cancel(pending(c));
        }
    }

    static String status(Context c) {
        SharedPreferences p = prefs(c);
        try {
            JSONArray list = new JSONArray(p.getString("list", "[]"));
            int i = p.getInt("index", -1);
            JSONObject o = new JSONObject()
                    .put("enabled", p.getBoolean("enabled", false))
                    .put("which", p.getString("which", "home"))
                    .put("index", i)
                    .put("total", list.length())
                    .put("next", p.getLong("next", 0))
                    .put("exact", exactAllowed(c));
            if (i >= 0 && i < list.length()) o.put("title", list.getJSONObject(i).optString("title"));
            return o.toString();
        } catch (Exception e) {
            return "{}";
        }
    }

    static boolean exactAllowed(Context c) {
        if (Build.VERSION.SDK_INT < 31) return true;
        try {
            AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
            return (Boolean) AlarmManager.class.getMethod("canScheduleExactAlarms").invoke(am); // API 31
        } catch (Exception e) {
            return false;
        }
    }

    private static PendingIntent pending(Context c) {
        Intent i = new Intent(c, Rotation.class).setAction(ACTION);
        return PendingIntent.getBroadcast(c, 1, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** which: home, lock or both. */
    static void apply(Context c, String url, String which) throws Exception {
        int flags = "home".equals(which) ? 1 : "lock".equals(which) ? 2 : 3; // FLAG_SYSTEM, FLAG_LOCK
        WallpaperManager wm = WallpaperManager.getInstance(c);
        // setStream(InputStream, Rect, boolean, int) is API 24; we compile against API 23.
        Method m = WallpaperManager.class.getMethod("setStream", InputStream.class, Rect.class, boolean.class, int.class);
        InputStream in = open(c, url);
        try { m.invoke(wm, in, null, true, flags); } finally { in.close(); }
    }

    /** Opens a wallpaper file: bundled asset or remote https PNG, validated before use. */
    static InputStream open(Context ctx, String url) throws IOException {
        Uri u = Uri.parse(url);
        if (!"https".equals(u.getScheme())) throw new IOException("Only https sources are allowed");
        InputStream in;
        if (MainActivity.HOST.equals(u.getHost())) {
            String p = u.getPath();
            if (p == null || p.contains("..")) throw new IOException("Bad path");
            in = ctx.getAssets().open("www" + p);
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
}
