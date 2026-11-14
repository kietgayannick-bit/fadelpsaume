package hev.htproxy;

/** Pont JNI vers hev-socks5-tunnel (compilé par le workflow GitHub). */
public class TProxyService {
    static {
        System.loadLibrary("hev-socks5-tunnel");
    }

    public static native void TProxyStartService(String configPath, int fd);

    public static native void TProxyStopService();

    public static native long[] TProxyGetStats();
}
