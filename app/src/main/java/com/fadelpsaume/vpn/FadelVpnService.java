package com.fadelpsaume.vpn;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.VpnService;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

import hev.htproxy.TProxyService;

/**
 * Service VPN de Fadelpsaume.
 *
 * Le moteur Xray (lancé par la partie Python) ouvre un proxy SOCKS5 local. Ce service crée l'interface
 * VPN d'Android (TUN) et la relie à ce proxy grâce à hev-socks5-tunnel : tout le téléphone passe donc
 * par le serveur choisi. L'application elle-même est exclue du tunnel (sinon Xray tournerait en boucle).
 */
public class FadelVpnService extends VpnService {
    private static final String TAG = "FadelVpn";
    private static final String ACTION_START = "com.fadelpsaume.vpn.START";
    private static final String CHANNEL_ID = "fadelpsaume_vpn";
    private static final int NOTIF_ID = 1;

    private ParcelFileDescriptor tun;
    private boolean tunnelRunning = false;

    static volatile String lastStatus = "pas encore demarre";
    static volatile int lastSocks = 0;
    static volatile String lastDns = "";

    /** Etat lisible par Python (affiche dans le journal). */
    public static String status() {
        return lastStatus;
    }

    // ----------------------------------------------------------------- appelé depuis Python
    public static void startTunnel(Context ctx, int socksPort, String dns) {
        lastSocks = socksPort;
        lastDns = dns == null ? "" : dns;
        lastStatus = "demande en cours";
        Intent need = VpnService.prepare(ctx);
        if (need != null) {
            // l'autorisation VPN n'a pas ete accordee : on redemande depuis l'ecran principal
            lastStatus = "autorisation VPN manquante (une fenetre va s'ouvrir)";
            Intent a = new Intent(ctx, MainActivity.class);
            a.putExtra("ask_vpn", true);
            a.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            ctx.startActivity(a);
            return;
        }
        Intent i = new Intent(ctx, FadelVpnService.class);
        i.setAction(ACTION_START);
        i.putExtra("socks", socksPort);
        i.putExtra("dns", dns == null ? "" : dns);
        if (Build.VERSION.SDK_INT >= 26) {
            ctx.startForegroundService(i);
        } else {
            ctx.startService(i);
        }
    }

    public static void stopTunnel(Context ctx) {
        ctx.stopService(new Intent(ctx, FadelVpnService.class));
    }

    // ----------------------------------------------------------------- cycle de vie
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || !ACTION_START.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        startForeground(NOTIF_ID, buildNotification());
        int socks = intent.getIntExtra("socks", 20808);
        String dns = intent.getStringExtra("dns");
        if (!tunnelRunning) {
            startTun(socks, dns);
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onRevoke() {
        // l'utilisateur a coupé le VPN depuis les réglages d'Android
        stopTun();
        stopSelf();
    }

    @Override
    public void onDestroy() {
        stopTun();
        super.onDestroy();
    }

    // ----------------------------------------------------------------- tunnel
    private void startTun(int socksPort, String dnsCsv) {
        try {
            Builder b = new Builder();
            b.setSession("Fadelpsaume");
            b.setMtu(1500);
            b.addAddress("198.18.0.1", 30);
            b.addRoute("0.0.0.0", 0);
            b.addAddress("fc00::1", 126);
            b.addRoute("::", 0);

            boolean anyDns = false;
            if (dnsCsv != null) {
                for (String d : dnsCsv.split("[,\\s]+")) {
                    if (d.matches("[0-9.]+") || d.contains(":")) {
                        try {
                            b.addDnsServer(d);
                            anyDns = true;
                        } catch (Exception ignored) {
                            // adresse refusée : on passe à la suivante
                        }
                    }
                }
            }
            if (!anyDns) {
                b.addDnsServer("1.1.1.1");
            }
            try {
                // Xray et SSH (dans cette application) ne doivent pas repasser par le tunnel
                b.addDisallowedApplication(getPackageName());
            } catch (Exception e) {
                Log.w(TAG, "addDisallowedApplication : " + e);
            }

            tun = b.establish();
            if (tun == null) {
                Log.e(TAG, "Permission VPN non accordée");
                lastStatus = "ECHEC : permission VPN refusee";
                stopSelf();
                return;
            }

            String cfg = "tunnel:\n"
                    + "  mtu: 1500\n"
                    + "  ipv4: 198.18.0.1\n"
                    + "  ipv6: 'fc00::1'\n"
                    + "socks5:\n"
                    + "  port: " + socksPort + "\n"
                    + "  address: 127.0.0.1\n"
                    + "  udp: 'udp'\n"
                    + "misc:\n"
                    + "  task-stack-size: 24576\n"
                    + "  tcp-buffer-size: 65536\n"
                    + "  connect-timeout: 6000\n"
                    + "  tcp-read-write-timeout: 300000\n"
                    + "  udp-read-write-timeout: 60000\n"
                    + "  log-level: warn\n";
            File f = new File(getFilesDir(), "hev.yml");
            try (FileOutputStream out = new FileOutputStream(f)) {
                out.write(cfg.getBytes(StandardCharsets.UTF_8));
            }
            TProxyService.TProxyStartService(f.getAbsolutePath(), tun.getFd());
            tunnelRunning = true;
            lastStatus = "actif (SOCKS " + socksPort + ")";
            Log.i(TAG, "Tunnel VPN démarré (SOCKS " + socksPort + ")");
        } catch (Throwable t) {
            Log.e(TAG, "Échec du tunnel : " + t);
            lastStatus = "ECHEC : " + t;
            stopTun();
            stopSelf();
        }
    }

    private void stopTun() {
        if (tunnelRunning) {
            try {
                TProxyService.TProxyStopService();
            } catch (Throwable t) {
                Log.w(TAG, "TProxyStopService : " + t);
            }
            tunnelRunning = false;
        }
        if (tun != null) {
            try {
                tun.close();
            } catch (Exception ignored) {
                // déjà fermé
            }
            tun = null;
        }
        stopForeground(true);
    }

    // ----------------------------------------------------------------- notification
    private Notification buildNotification() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Connexion VPN", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            nm.createNotificationChannel(ch);
        }
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);

        Notification.Builder nb;
        if (Build.VERSION.SDK_INT >= 26) {
            nb = new Notification.Builder(this, CHANNEL_ID);
        } else {
            nb = new Notification.Builder(this);
        }
        nb.setSmallIcon(R.drawable.ic_notif)
                .setContentTitle("Fadelpsaume")
                .setContentText("VPN actif — touche pour ouvrir")
                .setContentIntent(pi)
                .setOngoing(true);
        return nb.build();
    }
}
