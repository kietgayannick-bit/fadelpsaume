package com.fadelpsaume.vpn;

import android.Manifest;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.net.VpnService;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.PowerManager;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Log;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import com.chaquo.python.Python;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Écran unique : une WebView qui affiche l'interface servie par le moteur Python interne. */
public class MainActivity extends Activity {
    private static final String TAG = "FadelMain";
    private static final int REQ_VPN = 1;
    private static final int REQ_FILE = 2;
    private static final int REQ_PERM = 3;

    private static volatile boolean serverStarted = false;
    private static volatile int serverPort = 0;

    private WebView web;
    private ValueCallback<Uri[]> filePathCallback;
    private boolean vpnAsked = false;

    // ================================================================ cycle de vie
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#151a1f"));
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#151a1f"));
        root.addView(web, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);

        setupWebView();
        startEngine();
        askPermissions();
    }

    @Override
    protected void onResume() {
        super.onResume();
        askVpnPermission();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        web.evaluateJavascript("(window.fdlpBack && window.fdlpBack()) ? 'true' : 'false'", new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String v) {
                if (v == null || !v.contains("true")) {
                    moveTaskToBack(true);   // on garde l'application (et le VPN) en vie
                }
            }
        });
    }

    // ================================================================ moteur Python
    private void startEngine() {
        if (!serverStarted) {
            serverStarted = true;
            try {
                copyAssets("web", new File(getFilesDir(), "fdlp/web"));
                ServerSocket ss = new ServerSocket(0, 1, java.net.InetAddress.getByName("127.0.0.1"));
                serverPort = ss.getLocalPort();
                ss.close();
            } catch (Exception e) {
                Log.e(TAG, "Préparation impossible : " + e);
                serverStarted = false;
                Toast.makeText(this, "Erreur de démarrage : " + e, Toast.LENGTH_LONG).show();
                return;
            }
            final String filesDir = getFilesDir().getAbsolutePath();
            final String nativeDir = getApplicationInfo().nativeLibraryDir;
            final int port = serverPort;
            Thread t = new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        Python.getInstance().getModule("fdlp_android").callAttr("start", filesDir, nativeDir, port);
                    } catch (Throwable e) {
                        Log.e(TAG, "Le moteur Python s'est arrêté : " + e);
                        serverStarted = false;
                    }
                }
            }, "fadelpsaume-python");
            t.setDaemon(true);
            t.start();
        }
        waitAndLoad();
    }

    private void waitAndLoad() {
        final int port = serverPort;
        Thread t = new Thread(new Runnable() {
            @Override
            public void run() {
                boolean up = false;
                for (int i = 0; i < 150 && !up; i++) {      // jusqu'à ~30 s
                    try (Socket s = new Socket()) {
                        s.connect(new InetSocketAddress("127.0.0.1", port), 300);
                        up = true;
                    } catch (Exception e) {
                        try {
                            Thread.sleep(200);
                        } catch (InterruptedException ie) {
                            return;
                        }
                    }
                }
                final boolean ok = up;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (web == null) {
                            return;
                        }
                        if (ok) {
                            web.loadUrl("http://127.0.0.1:" + port + "/");
                        } else {
                            Toast.makeText(MainActivity.this, "Le moteur interne n'a pas démarré.", Toast.LENGTH_LONG).show();
                        }
                    }
                });
            }
        }, "fadelpsaume-wait");
        t.setDaemon(true);
        t.start();
    }

    private void copyAssets(String assetDir, File target) throws Exception {
        String[] list = getAssets().list(assetDir);
        if (list == null || list.length == 0) {
            // c'est un fichier
            target.getParentFile().mkdirs();
            try (InputStream in = getAssets().open(assetDir); OutputStream out = new FileOutputStream(target)) {
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                }
            }
            return;
        }
        target.mkdirs();
        for (String name : list) {
            copyAssets(assetDir + "/" + name, new File(target, name));
        }
    }

    // ================================================================ WebView
    private void setupWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                // l'interface ne doit jamais ouvrir un autre site (le pont Java y serait exposé)
                return !"127.0.0.1".equals(u.getHost());
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                try {
                    startActivityForResult(Intent.createChooser(i, "Choisir un fichier .fdlp / .rmv"), REQ_FILE);
                } catch (Exception e) {
                    filePathCallback = null;
                    return false;
                }
                return true;
            }
        });
        web.addJavascriptInterface(new Bridge(), "FadelAndroid");
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_FILE) {
            if (filePathCallback != null) {
                Uri[] r = null;
                if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                    r = new Uri[]{data.getData()};
                }
                filePathCallback.onReceiveValue(r);
                filePathCallback = null;
            }
        } else if (requestCode == REQ_VPN) {
            if (resultCode != RESULT_OK) {
                Toast.makeText(this, "Sans l'autorisation VPN, seul le proxy local fonctionnera.", Toast.LENGTH_LONG).show();
            }
        }
    }

    // ================================================================ permissions
    private void askVpnPermission() {
        if (vpnAsked) {
            return;
        }
        vpnAsked = true;
        try {
            Intent i = VpnService.prepare(this);
            if (i != null) {
                startActivityForResult(i, REQ_VPN);
            }
        } catch (Exception e) {
            Log.w(TAG, "VpnService.prepare : " + e);
        }
    }

    private void askPermissions() {
        try {
            java.util.ArrayList<String> need = new java.util.ArrayList<String>();
            if (Build.VERSION.SDK_INT >= 33
                    && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                need.add(Manifest.permission.POST_NOTIFICATIONS);
            }
            if (Build.VERSION.SDK_INT < 29
                    && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                need.add(Manifest.permission.WRITE_EXTERNAL_STORAGE);
            }
            if (!need.isEmpty()) {
                requestPermissions(need.toArray(new String[0]), REQ_PERM);
            }
        } catch (Exception e) {
            Log.w(TAG, "permissions : " + e);
        }
        askBatteryOnce();
    }

    /** Demande une seule fois de ne pas optimiser la batterie (évite que le VPN soit tué en arrière-plan). */
    private void askBatteryOnce() {
        try {
            SharedPreferences sp = getSharedPreferences("fdlp", MODE_PRIVATE);
            if (sp.getBoolean("battery_asked", false) || Build.VERSION.SDK_INT < 23) {
                return;
            }
            sp.edit().putBoolean("battery_asked", true).apply();
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                i.setData(Uri.parse("package:" + getPackageName()));
                startActivity(i);
            }
        } catch (Exception e) {
            Log.w(TAG, "batterie : " + e);
        }
    }

    // ================================================================ pont JavaScript
    private class Bridge {
        @JavascriptInterface
        public boolean copy(final String text) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    cm.setPrimaryClip(ClipData.newPlainText("Fadelpsaume", text));
                }
            });
            return true;
        }

        @JavascriptInterface
        public String paste() {
            final AtomicReference<String> out = new AtomicReference<String>("");
            final CountDownLatch latch = new CountDownLatch(1);
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                        ClipData d = cm.getPrimaryClip();
                        if (d != null && d.getItemCount() > 0) {
                            CharSequence cs = d.getItemAt(0).coerceToText(MainActivity.this);
                            out.set(cs == null ? "" : cs.toString());
                        }
                    } catch (Exception ignored) {
                        // presse-papier inaccessible
                    } finally {
                        latch.countDown();
                    }
                }
            });
            try {
                latch.await(3, TimeUnit.SECONDS);
            } catch (InterruptedException ignored) {
                // abandon
            }
            return out.get();
        }

        /** Enregistre un fichier dans « Téléchargements ». Retourne un texte d'emplacement, ou "" en cas d'échec. */
        @JavascriptInterface
        public String saveFile(String name, String content) {
            try {
                byte[] data = content.getBytes(StandardCharsets.UTF_8);
                if (Build.VERSION.SDK_INT >= 29) {
                    ContentValues cv = new ContentValues();
                    cv.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                    cv.put(MediaStore.MediaColumns.MIME_TYPE, "application/octet-stream");
                    cv.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                    Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                    if (uri == null) {
                        return "";
                    }
                    try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                        os.write(data);
                    }
                } else {
                    File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                    dir.mkdirs();
                    try (OutputStream os = new FileOutputStream(new File(dir, name))) {
                        os.write(data);
                    }
                }
                return "Téléchargements";
            } catch (Exception e) {
                Log.e(TAG, "saveFile : " + e);
                return "";
            }
        }

        @JavascriptInterface
        public void shareFile(String name, String content) {
            try {
                File dir = new File(getCacheDir(), "share");
                dir.mkdirs();
                File f = new File(dir, name);
                try (OutputStream os = new FileOutputStream(f)) {
                    os.write(content.getBytes(StandardCharsets.UTF_8));
                }
                shareUri(f, "application/octet-stream");
            } catch (Exception e) {
                Log.e(TAG, "shareFile : " + e);
            }
        }

        @JavascriptInterface
        public void shareApp() {
            try {
                File dir = new File(getCacheDir(), "share");
                dir.mkdirs();
                File apk = new File(dir, "Fadelpsaume.apk");
                try (InputStream in = new java.io.FileInputStream(getApplicationInfo().sourceDir);
                     OutputStream os = new FileOutputStream(apk)) {
                    byte[] buf = new byte[65536];
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        os.write(buf, 0, n);
                    }
                }
                shareUri(apk, "application/vnd.android.package-archive");
            } catch (Exception e) {
                Log.e(TAG, "shareApp : " + e);
            }
        }
    }

    private void shareUri(final File f, final String mime) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    Uri uri = FileProvider.getUriForFile(MainActivity.this, getPackageName() + ".fileprovider", f);
                    Intent i = new Intent(Intent.ACTION_SEND);
                    i.setType(mime);
                    i.putExtra(Intent.EXTRA_STREAM, uri);
                    i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivity(Intent.createChooser(i, "Partager"));
                } catch (Exception e) {
                    Toast.makeText(MainActivity.this, "Partage impossible : " + e, Toast.LENGTH_LONG).show();
                }
            }
        });
    }
}
