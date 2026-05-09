/**
 * Capacitor configuration for Facette mobile app.
 * Detaylı kurulum: /app/CAPACITOR_DEPLOYMENT_GUIDE.md
 *
 * Bu dosya `npx cap init` ile yeniden oluşturulabilir; aşağıdaki defaults
 * Facette için optimize edilmiştir. Kullanıcının değiştirmesi gerekenler
 * `appId` (bundle id) ve store URL'leri (release sırasında).
 */
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.facette.app',
  appName: 'Facette',
  webDir: 'build',
  bundledWebRuntime: false,
  server: {
    cleartext: false,
    androidScheme: 'https',
    // Live reload için development'ta:
    //   url: 'http://192.168.1.10:3000',
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#000000',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER_CROP',
      showSpinner: true,
      spinnerColor: '#ffffff',
      splashFullScreen: true,
      splashImmersive: true,
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#000000',
      overlaysWebView: false,
    },
    Preferences: {
      group: 'com.facette.app',
    },
  },
  ios: {
    contentInset: 'always',
    backgroundColor: '#000000',
    scheme: 'Facette',
  },
  android: {
    allowMixedContent: false,
    captureInput: true,
    webContentsDebuggingEnabled: false,
    backgroundColor: '#000000',
  },
};

export default config;
